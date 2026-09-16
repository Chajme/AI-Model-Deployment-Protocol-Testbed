"""
    LwM2M client (emulator): performs the device side of an OMA LwM2M
    firmware-update flow over CoAP.
    / used by docker-compose.yaml & docker-compose.automated.yaml

    Sequence driven by the benchmark harness (one --file per run):

      1. POST  coap://lwm2m-server/rd?ep=...        registration
      2. POST  coap://lwm2m-server/update?file=...  benchmark trigger
      3. (server PUTs the Package URI to our /5/0/1)
      4. GET   <package uri>                        blockwise model pull
      5. PUT   /rd/1/5/0/3 = "2"                    report: Downloaded
      6. (server POSTs our /5/0/2 -- Update Execute)
      7. PUT   /rd/1/5/0/3 = "1"                    report: Update success

    Metrics recorded client-side: registration RTT, download duration,
    goodput, integrity (SHA-256 of the pulled object).
"""
import argparse
import asyncio
import os
import sys
import time

import aiocoap
import aiocoap.resource as resource

from common.file_manager import save_file, get_file_path_input, output_directory_exists
from common.integrity_checker import sha256
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_lwm2m

SERVER = "lwm2m-server"


class DevicePackageUriResource(resource.Resource):
    """Object 5/0/1: server writes the firmware package URI here."""

    def __init__(self, state):
        super().__init__()
        self.state = state

    async def render_put(self, request):
        self.state["package_uri"] = request.payload.decode(errors="replace")
        self.state["package_uri_event"].set()
        print(f"[device] Package URI set: {self.state['package_uri']}")
        return aiocoap.Message(code=aiocoap.CHANGED)


class DeviceExecuteResource(resource.Resource):
    """Object 5/0/2: server executes the update."""

    def __init__(self, state):
        super().__init__()
        self.state = state

    async def render_post(self, request):
        self.state["execute_event"].set()
        print("[device] Update executed")
        return aiocoap.Message(code=aiocoap.CHANGED)


async def register(context, endpoint_name):
    message = aiocoap.Message(
        code=aiocoap.POST,
        uri=f"coap://{SERVER}/rd?ep={endpoint_name}&lt=86400",
        payload=b"</3/0>,</5/0>",
    )
    t0 = time.perf_counter()
    response = await context.request(message).response
    latency = time.perf_counter() - t0
    if response.code != aiocoap.CREATED:
        raise RuntimeError(f"registration failed: {response.code}")
    location = "/".join(response.opt.location_path or ("rd", "?"))
    print(f"[device] Registered ({location}) in {latency:.4f}s")
    return latency


async def trigger_update(context, filename, checksum):
    message = aiocoap.Message(
        code=aiocoap.POST,
        uri=f"coap://{SERVER}/update?file={filename}&checksum={checksum}",
    )
    response = await context.request(message).response
    if not response.code.is_successful():
        raise RuntimeError(f"update trigger failed: {response.code}")


async def wait_for_package_uri(state, timeout=30) -> str:
    await asyncio.wait_for(state["package_uri_event"].wait(), timeout=timeout)
    return state["package_uri"]


async def download(context, package_uri: str):
    t0 = time.perf_counter()
    response = await context.request(aiocoap.Message(code=aiocoap.GET,
                                                     uri=package_uri)).response
    duration = time.perf_counter() - t0
    if response.code != aiocoap.CONTENT:
        raise RuntimeError(f"download failed: {response.code}")
    return response.payload, duration


async def report_state(context, value: bytes):
    message = aiocoap.Message(
        code=aiocoap.PUT,
        uri=f"coap://{SERVER}/rd/1/5/0/3",
        payload=value,
    )
    response = await context.request(message).response
    if not response.code.is_successful():
        raise RuntimeError(f"state report failed: {response.code}")


async def run_flow(filename: str):
    endpoint_name = "lwm2m-edge"

    state = {
        "package_uri": None,
        "package_uri_event": asyncio.Event(),
        "execute_event": asyncio.Event(),
    }

    # One context serves our device objects AND issues outgoing requests,
    # so server-initiated writes arrive on our well-known port.
    site = resource.Site()
    site.add_resource(["5", "0", "1"], DevicePackageUriResource(state))
    site.add_resource(["5", "0", "2"], DeviceExecuteResource(state))
    context = await aiocoap.Context.create_server_context(
        site, bind=("0.0.0.0", 5683)
    )

    try:
        # 1. Register with the LwM2M server.
        reg_latency = await register(context, endpoint_name)

        # 2. Kick off the update flow for this file.
        filepath = get_file_path_input(filename)
        checksum = sha256_file(filepath)
        await trigger_update(context, filename, checksum)

        # 3-4. Receive Package URI, then pull the object blockwise.
        package_uri = await wait_for_package_uri(state)
        monitor = ResourceMonitor(sample_interval=0.01)
        monitor.start()
        payload, download_duration = await download(context, package_uri)
        resource_stats = monitor.stop()

        file_size_mb = len(payload) / (1024 * 1024)
        goodput_mbps = (len(payload) * 8) / (download_duration * 1_000_000)
        integrity_ok = sha256(payload) == checksum

        # 5. Report Downloaded (object 5/0/3 state 2).
        await report_state(context, b"2")

        # 6. Wait for the server's Update Execute on /5/0/2.
        await asyncio.wait_for(state["execute_event"].wait(), timeout=300)

        # 7. Report final result (object 5/0/3 result 1 = success).
        await report_state(context, b"1" if integrity_ok else b"5")

        print(f"\n--- LwM2M transfer done: {filename} "
              f"({file_size_mb:.2f} MB, integrity_ok={integrity_ok}) ---")

        write_to_file_lwm2m(
            [
                {
                    "protocol": "lwm2m",
                    "side": "client",
                    "file_size": f"{file_size_mb:.6f}",
                    "download_duration": f"{download_duration:.4f}",
                    "latency": f"{reg_latency:.4f}",
                    "goodput_mbps": f"{goodput_mbps:.3f}",
                    "integrity_ok": integrity_ok,
                    "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
                    "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
                    "energy_est": f"{resource_stats['energy_j']:.4f}",
                }
            ]
        )
    finally:
        await context.shutdown()


def sha256_file(filepath: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    output_directory_exists()

    if not os.path.isfile(get_file_path_input(args.file)):
        print(f"File {args.file} not found.")
        sys.exit(1)

    asyncio.run(run_flow(args.file))
