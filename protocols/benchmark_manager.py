"""
    Unified benchmark orchestrator driving transfers for MQTT / HTTP / CoAP.

    Assumes the docker-compose stack is already up (docker-compose.yaml for the
    manual flow, or docker-compose.automated.yaml for the automated runner).

    For each transfer it:
      1. starts tcpdump in the protocol's capture sidecar container
      2. executes a single-file transfer inside the protocol's client container
      3. stops tcpdump (clean pcap close)
      4. analyzes the pcap with tshark and appends a row to the active run's
         pcap_measurements.csv (output/runs/<run_id>/; see common/runs.py)
"""

import argparse
import os
import subprocess
import sys

# Allow running as a plain script too: `python protocols/benchmark_manager.py`
# otherwise puts `protocols/` (not the project root) on sys.path.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from common.file_manager import load_binary_files, get_file_path_input
from common.packet_capture import start_capture_run, stop_capture_run
from common.pcap_analyzer import analyze_pcap, print_result
from output.write_csv import write_to_file_pcap
import common.runs as runs

DATA_DIR = os.getenv("DATA_DIR", "./data")

# Host-side runs should still write CSVs next to the pcaps (./output),
# not to the in-container /app/output path.
os.environ.setdefault("OUTPUT_DIR", "./output")

# Protocol -> transfer runner config.
#   service:   docker compose service (client) to exec into
#   module:    python module with a --file argument to run inside the container
#   has_qos:   whether the protocol has QoS levels to sweep (MQTT)
RUNNERS = {
    "mqtt": {
        "service": "mqtt-client-a",
        "module": "protocols.MQTT.clients.client_a",
        "has_qos": True,
    },
    "http": {
        "service": "http-client",
        "module": "protocols.HTTP.client.http_client",
        "has_qos": False,
    },
    "coap": {
        "service": "coap-client",
        "module": "protocols.CoAP.client.coap_client",
        "has_qos": False,
    },
}

DEFAULT_MQTT_QOS = [1, 2]


def file_size_bytes(filename: str) -> int:
    return os.path.getsize(get_file_path_input(filename))


def run_transfer(protocol: str, filename: str, qos: int | None = None, analyze: bool = True) -> None:
    """Run one transfer for one protocol/file (optionally one QoS level), captured to its own pcap."""
    if protocol not in RUNNERS:
        raise ValueError(f"Unknown protocol {protocol!r}. Supported: {list(RUNNERS)}")

    runner = RUNNERS[protocol]
    if qos is not None and not runner["has_qos"]:
        raise ValueError(f"Protocol {protocol!r} does not support QoS levels.")

    label = f"{filename}_{qos}" if qos is not None else filename

    print(f"\n=== {protocol.upper()} | {filename} | qos={qos} ===")

    outfile = start_capture_run(label, protocol)
    print(f"  -> Capturing to {outfile}")

    try:
        command = [
            "docker", "compose", "exec", runner["service"],
            "python", "-m", runner["module"],
            "--file", filename,
        ]
        if qos is not None:
            command += ["--qos", str(qos)]

        subprocess.run(command, check=True)
    finally:
        stop_capture_run(protocol, outfile, runs.pcap_dir())

    print(f"  -> Capture stopped: {outfile}")

    if not analyze:
        return

    size = file_size_bytes(filename)
    pcap_path = os.path.join(runs.pcap_dir(), os.path.basename(outfile))

    try:
        result = analyze_pcap(
            pcap_path,
            size,
            protocol=protocol,
            filename=filename,
            qos_level=qos,
            label=label,
        )
    except Exception as e:
        print(f"  -> WARNING: pcap analysis failed: {e}")
        return

    print_result(result)
    write_to_file_pcap([result])


def run_protocol(protocol: str, files: list[str] | None = None, qos_levels: list[int] | None = None, analyze: bool = True) -> None:
    """Run all transfers for one protocol. MQTT sweeps QoS 1..2 unless overridden."""
    runner = RUNNERS.get(protocol)
    if runner is None:
        raise ValueError(f"Unknown protocol {protocol!r}. Supported: {list(RUNNERS)}")

    if files is None:
        files = load_binary_files()

    if not files:
        print(f"No .bin files found for {protocol}.")
        return

    # Record what this run actually covered in the manifest (useful for later
    # processing without re-reading the data directory).
    run_id = runs.active_run_id()
    if run_id:
        sizes = [os.path.getsize(get_file_path_input(f)) for f in files]
        runs.update_manifest(
            os.environ.get("OUTPUT_DIR", "./output"),
            run_id,
            {"file_sizes": sizes, "files": files},
        )

    if runner["has_qos"]:
        qos_levels = qos_levels or DEFAULT_MQTT_QOS
        if run_id:
            runs.update_manifest(
                os.environ.get("OUTPUT_DIR", "./output"),
                run_id,
                {"qos_levels": qos_levels},
            )
        for qos in qos_levels:
            for filename in files:
                run_transfer(protocol, filename, qos=qos, analyze=analyze)
    else:
        for filename in files:
            run_transfer(protocol, filename, qos=None, analyze=analyze)


def _ensure_run(protocols: list[str]) -> str | None:
    """Create a fresh run for a manual (non-runner) invocation.

    The automated runner already creates the run and sets RUN_ID; the manual
    CLI creates one (timestamp-based) so manual transfers still land in a
    self-contained run directory instead of the legacy flat output.
    """
    if runs.active_run_id():
        return None
    output_dir = os.environ.get("OUTPUT_DIR", "./output")
    rid = runs.new_run(
        output_dir,
        protocols[0],
        profile=os.getenv("NETWORK_PROFILE"),
        meta={"flow": "manual"},
    )
    os.environ["RUN_ID"] = rid
    runs.write_marker(output_dir, rid)
    print(f"  -> Run: {rid}")
    return rid


def main():
    parser = argparse.ArgumentParser(description="Run pcap-captured protocol benchmarks.")
    parser.add_argument(
        "--protocol",
        nargs="+",
        choices=list(RUNNERS),
        default=list(RUNNERS),
        help="Protocols to benchmark (default: all).",
    )
    parser.add_argument(
        "--file",
        required=False,
        help="Transfer a single file (name in ./data). Defaults to all .bin files.",
    )
    parser.add_argument(
        "--qos",
        nargs="+",
        type=int,
        default=None,
        help="MQTT QoS levels to sweep (default: 1 2).",
    )
    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Capture pcaps but skip tshark analysis.",
    )
    args = parser.parse_args()

    files = [args.file] if args.file else None

    _ensure_run(args.protocol)

    for protocol in args.protocol:
        run_protocol(protocol, files=files, qos_levels=args.qos, analyze=not args.no_analyze)


if __name__ == "__main__":
    main()