import os
import subprocess
import time

# Protocol -> sidecar capture container that shares the server's network
# namespace (mqtt-client <-> broker, http-client <-> server, coap-client <-> server).
CAPTURE_SERVICES = {
    "mqtt": "mqtt-capture",
    "http": "http-capture",
    "coap": "coap-capture",
}

DEFAULT_IFACE = "eth0"

# tcpdump kernel capture buffer in KiB. The default (~1 MiB) overflows and
# drops frames during fast large-file bursts. 8 MiB gives tcpdump headroom
# to absorb the burst while it drains to disk.
TCPDUMP_BUFFER_KB = 8192

# Client containers that originate protocol traffic and must have their NIC
# segmentation offloads (TSO/GSO) disabled so the capture shows real
# MTU-sized frames. Otherwise the veth pair delivers multi-MB GSO super-frames
# to the server and the per-segment header overhead never appears in the pcap.
# The server/broker side is handled by the capture container (it shares that
# network namespace). CoAP runs over UDP (no TSO/GSO), so nothing to disable.
OFFLOAD_CONTAINERS = {
    "mqtt": ["mqtt-client-a", "mqtt-client-b"],
    "http": ["http-client"],
    "coap": [],
}

OFFLOAD_SETTINGS = ["gro", "gso", "tso"]


def _offload_args():
    """ethtool -K <iface> gro off gso off tso off as separate argv tokens."""
    args = []
    for setting in OFFLOAD_SETTINGS:
        args.extend([setting, "off"])
    return args


def start_capture_run(
    label: str,
    protocol: str = "mqtt",
    iface: str = DEFAULT_IFACE,
) -> str:
    """Start tcpdump inside the (already-running) capture container for one run.

    The pcap is written to a fast container-local path (/tmp) and copied out
    by stop_capture_run() -- the per-run volume bind mount is too slow for the
    high packet rate of large MTU-sized captures and causes kernel-buffer drops.
    """
    service = _resolve_service(protocol)
    # Container-local path: fast overlay FS, avoids the slow volume mount.
    outfile = f"/tmp/{protocol}_{label}.pcap"
    # Remove any pcap left over from a previous identical run so that
    # each run starts from a clean capture.
    subprocess.run(
        ["docker", "compose", "exec", service, "rm", "-f", outfile],
        check=False,
    )
    # Disable segmentation offloads so the pcap shows real wire frames.
    _disable_offloads(protocol)
    # NOTE: -U is intentionally NOT used here. Packet-buffered mode issues a
    # write(2) per frame straight to the filesystem and the kernel capture
    # buffer overflows -> dropped frames. Default buffered mode drains the
    # kernel ring quickly and flushes to disk in large chunks.
    subprocess.run(
        [
            "docker", "compose", "exec", "-d", service,
            "tcpdump", "-B", str(TCPDUMP_BUFFER_KB),
            "-i", iface, "-s", "0", "-w", outfile,
        ],
        check=True,
    )
    _wait_until_ready(service)
    return outfile


def _disable_offloads(protocol: str) -> None:
    """Turn off GRO/GSO/TSO on every container whose traffic crosses the pcap.

    Idempotent. Failures are logged as warnings, not raised: a missed disable
    only under-reports header overhead, whereas a hard error here would block
    the whole benchmark.
    """
    targets = [CAPTURE_SERVICES[protocol]] + OFFLOAD_CONTAINERS.get(protocol, [])
    for service in targets:
        try:
            result = subprocess.run(
                [
                    "docker", "compose", "exec", service, "ethtool", "-K",
                    DEFAULT_IFACE, *_offload_args(),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(
                    f"  WARNING: could not disable offloads on {service}: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
        except Exception as e:
            print(f"  WARNING: could not disable offloads on {service}: {e}")


def _wait_until_ready(service: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "compose", "exec", service, "pgrep", "-x", "tcpdump"],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(0.1)
    raise RuntimeError(f"tcpdump never started inside {service}")


def stop_capture_run(
    protocol: str = "mqtt",
    container_pcap_path: str | None = None,
    host_pcap_dir: str | None = None,
    timeout: float = 5.0,
) -> None:
    """Stop tcpdump, wait for it to exit, then copy the pcap to the host.

    SIGTERM makes tcpdump flush its buffered frames and close the pcap cleanly;
    waiting for the process to actually exit guarantees the file is complete
    before it is copied out. When host_pcap_dir is given, the pcap is copied
    from the container-local path to the host directory and removed from the
    container.
    """
    service = _resolve_service(protocol)
    subprocess.run(
        ["docker", "compose", "exec", service, "pkill", "-TERM", "tcpdump"],
        check=True,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "compose", "exec", service, "pgrep", "-x", "tcpdump"],
            capture_output=True,
        )
        if result.returncode != 0:
            break
        time.sleep(0.1)
    else:
        print(f"  WARNING: tcpdump did not exit within {timeout}s in {service}")

    if container_pcap_path and host_pcap_dir:
        if not os.path.isdir(host_pcap_dir):
            os.makedirs(host_pcap_dir, exist_ok=True)
        copy = subprocess.run(
            [
                "docker", "compose", "cp",
                f"{service}:{container_pcap_path}", host_pcap_dir + os.sep,
            ],
            capture_output=True,
            text=True,
        )
        if copy.returncode != 0:
            print(
                f"  WARNING: could not copy {container_pcap_path} from {service}: "
                f"{copy.stderr.strip() or copy.stdout.strip()}"
            )
        else:
            subprocess.run(
                ["docker", "compose", "exec", service, "rm", "-f", container_pcap_path],
                check=False,
            )


def _resolve_service(protocol: str) -> str:
    if protocol not in CAPTURE_SERVICES:
        raise ValueError(
            f"Unknown protocol {protocol!r}. Supported: {list(CAPTURE_SERVICES)}"
        )
    return CAPTURE_SERVICES[protocol]


if __name__ == "__main__":
    start_capture_run("5mb_run1")
    # ... send the 5MB file here ...
    stop_capture_run()

    start_capture_run("50mb_run1", protocol="http")
    # ... send the 50MB file here ...
    stop_capture_run(protocol="http")
