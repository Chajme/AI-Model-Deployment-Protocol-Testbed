"""
    LwM2M server (emulator): implements the essential OMA LwM2M firmware-update
    message patterns over CoAP (RFC 7252 + blockwise RFC 7959).
    / used by docker-compose.yaml & docker-compose.automated.yaml

    This is a flow-level emulation built on aiocoap -- it reproduces the wire
    patterns of a real LwM2M server without the full OMA object model:

      1. POST /rd?ep=...            -> client registration (201 + /rd/1)
      2. POST /update?file=...      -> benchmark trigger; server then acts as
                                       the management server would:
         a. PUT  coap://<client>/5/0/1     (Package URI write)
         b. waits for the Downloaded state report (PUT /rd/1/5/0/3 = 2)
         c. POST coap://<client>/5/0/2     (Update Execute)
      3. GET  /fw/<filename>        -> blockwise firmware/model pull (the
                                       actual data-plane transfer)

    Simplifications: single-device registry (fixed /rd/1 location), no DTLS,
    no serialization of the OMA TLV/CBOR object model.
"""
import asyncio
import os

import aiocoap
import aiocoap.resource as resource

from common.file_manager import get_file_path_input

CLIENT_REG_LOCATION = "/rd/1"


class RegistrationResource(resource.Resource):
    """LwM2M registration interface (simplified /rd)."""

    def __init__(self, registry):
        super().__init__()
        self.registry = registry

    async def render_post(self, request):
        ep_name = "unknown"
        for query in request.opt.uri_query:
            if query.startswith("ep="):
                ep_name = query.split("=", 1)[1]

        # Remember where the client lives so we can initiate requests to it
        # (Package URI write, Update Execute).
        self.registry["endpoint"] = ep_name
        self.registry["remote"] = request.remote.hostinfo

        print(f"[LwM2M] Registered '{ep_name}' at {request.remote.hostinfo}")

        response = aiocoap.Message(code=aiocoap.CREATED)
        response.opt.location_path = ("rd", "1")
        return response


class FirmwareResource(resource.Resource):
    """Firmware/model repository served over CoAP blockwise (GET /fw).

    The object is addressed by query parameter (?name=<filename>) rather
    than a path segment: aiocoap's Site dispatches unknown child paths to
    4.04 before the resource ever sees them.
    """

    async def render_get(self, request):
        filename = None
        for query in request.opt.uri_query:
            if query.startswith("name="):
                filename = query.split("=", 1)[1]

        filepath = get_file_path_input(filename) if filename else ""
        if not filename or not os.path.isfile(filepath):
            print(f"[LwM2M] Firmware request for unknown object: {filename}")
            return aiocoap.Message(code=aiocoap.NOT_FOUND)

        # aiocoap splits large payloads into Block2 transfers automatically.
        with open(filepath, "rb") as f:
            payload = f.read()

        print(f"[LwM2M] Serving firmware '{filename}' ({len(payload)} bytes)")
        return aiocoap.Message(code=aiocoap.CONTENT, payload=payload)


class StateReportResource(resource.Resource):
    """Receives Firmware Update state/result writes (object 5/0/3)."""

    def __init__(self, registry):
        super().__init__()
        self.registry = registry

    async def render_put(self, request):
        state = request.payload.decode(errors="replace").strip()
        self.registry["last_state"] = state
        if state == "2":
            self.registry["downloaded_event"].set()
        elif state == "1":
            self.registry["updated_event"].set()
        print(f"[LwM2M] State report from device: {state}")
        return aiocoap.Message(code=aiocoap.CHANGED)


class UpdateTriggerResource(resource.Resource):
    """Benchmark entry point: POST /update?file=X&checksum=Y starts the
    server-initiated firmware-update flow toward the registered device."""

    def __init__(self, registry, context):
        super().__init__()
        self.registry = registry
        self.context = context

    async def render_post(self, request):
        filename = "unknown.bin"
        checksum = ""
        for query in request.opt.uri_query:
            if query.startswith("file="):
                filename = query.split("=", 1)[1]
            elif query.startswith("checksum="):
                checksum = query.split("=", 1)[1]

        remote = self.registry.get("remote")
        if not remote:
            return aiocoap.Message(code=aiocoap.SERVICE_UNAVAILABLE,
                                   payload=b"no registered client")

        asyncio.get_running_loop().create_task(
            self._run_update_flow(remote, filename, checksum)
        )
        return aiocoap.Message(code=aiocoap.CHANGED)

    async def _run_update_flow(self, remote, filename, checksum):
        try:
            # a. Package URI write (server -> device, object 5/0/1)
            package_uri = (
                f"coap://lwm2m-server/fw?name={filename}&checksum={checksum}"
            )
            put = aiocoap.Message(
                code=aiocoap.PUT,
                payload=package_uri.encode(),
                uri=f"coap://{remote}/5/0/1",
            )
            await self.context.request(put).response
            print(f"[LwM2M] Package URI written: {package_uri}")

            # b. Wait until the device reports Downloaded (state 2)
            await asyncio.wait_for(
                self.registry["downloaded_event"].wait(), timeout=3600
            )

            # c. Trigger the install (object 5/0/2 Execute == CoAP POST)
            exe = aiocoap.Message(
                code=aiocoap.POST, uri=f"coap://{remote}/5/0/2"
            )
            await self.context.request(exe).response
            print("[LwM2M] Update executed")

            # Wait for the final success report before considering it done.
            await asyncio.wait_for(
                self.registry["updated_event"].wait(), timeout=300
            )
            print(f"[LwM2M] Update flow complete for {filename}")
        except Exception as e:
            print(f"[LwM2M] Update flow failed: {e}")


class ExecuteResource(resource.Resource):
    """Object 5/0/2 Update Execute target on the DEVICE side."""

    def __init__(self, registry):
        super().__init__()
        self.registry = registry

    async def render_post(self, request):
        self.registry["execute_event"].set()
        return aiocoap.Message(code=aiocoap.CHANGED)


class PackageUriResource(resource.Resource):
    """Object 5/0/1 Package URI write target on the DEVICE side."""

    def __init__(self, registry):
        super().__init__()
        self.registry = registry

    async def render_put(self, request):
        self.registry["package_uri"] = request.payload.decode(errors="replace")
        self.registry["package_uri_event"].set()
        return aiocoap.Message(code=aiocoap.CHANGED)


async def main():
    # Shared state between the device-facing resources and the update flow.
    registry = {
        "package_uri": None,
        "package_uri_event": asyncio.Event(),
        "downloaded_event": asyncio.Event(),
        "updated_event": asyncio.Event(),
        "execute_event": asyncio.Event(),
    }

    update_resource = UpdateTriggerResource(registry, None)

    root = resource.Site()
    root.add_resource(["rd"], RegistrationResource(registry))
    root.add_resource(["rd", "1", "5", "0", "3"], StateReportResource(registry))
    root.add_resource(["fw"], FirmwareResource())
    root.add_resource(["update"], update_resource)

    context = await aiocoap.Context.create_server_context(
        root, bind=("0.0.0.0", 5683)
    )
    # The update flow needs the bound context to originate requests.
    update_resource.context = context

    print("LwM2M Server starting on UDP 5683...")
    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
