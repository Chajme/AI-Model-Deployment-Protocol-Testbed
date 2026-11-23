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
import time

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
#   args:      extra arguments passed to the module (optional)
RUNNERS = {
    "mqtt": {
        "service": "mqtt-client-a",
        "module": "protocols.MQTT.clients.client_a",
        "has_qos": True,
    },
    # Same client with up to 20 chunks in flight (see client_a.send_chunks).
    "mqtt-windowed": {
        "service": "mqtt-client-a",
        "module": "protocols.MQTT.clients.client_a",
        "has_qos": True,
        "args": ["--window", "20"],
    },
    "http": {
        "service": "http-client",
        "module": "protocols.HTTP.client.http_client",
        "has_qos": False,
    },
    # Device-style download of the payload (GET with Range resume).
    "http-get": {
        "service": "http-client",
        "module": "protocols.HTTP.client.http_client",
        "has_qos": False,
        "args": ["--mode", "get"],
    },
    "coap": {
        "service": "coap-client",
        "module": "protocols.CoAP.client.coap_client",
        "has_qos": False,
    },
    "amqp": {
        "service": "amqp-client-a",
        "module": "protocols.AMQP.client.amqp_client",
        "has_qos": False,
    },
    "grpc": {
        "service": "grpc-client",
        "module": "protocols.GRPC.client.grpc_client",
        "has_qos": False,
    },
    "lwm2m": {
        "service": "lwm2m-client",
        "module": "protocols.LWM2M.client.lwm2m_client",
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

    transfer_failed = False
    receivers_before = _receiver_row_count(protocol)
    try:
        command = [
            "docker", "compose", "exec", runner["service"],
            "python", "-m", runner["module"],
            "--file", filename,
            *runner.get("args", []),
        ]
        if qos is not None:
            command += ["--qos", str(qos)]

        subprocess.run(command, check=True)

        # Broker protocols: the sender only hands the file to the broker over
        # the clean server-side link. Delivery to the device over the
        # constrained link continues after the sender exits, so keep the
        # capture (and the stack) up until the receiver has verified the file.
        if receivers_before is not None and not _wait_for_receiver(
                protocol, receivers_before, file_size_bytes(filename)):
            transfer_failed = True
            exit_code = "receiver-timeout"
            print("  -> WARNING: the receiver did not report the file before the timeout")
    except subprocess.CalledProcessError as e:
        # One failed transfer must not abort the rest of the sweep; the client
        # has already logged a failure row for this file.
        transfer_failed = True
        exit_code = e.returncode
        print(f"  -> WARNING: transfer process exited with code {e.returncode}")
    finally:
        stop_capture_run(protocol, outfile, runs.pcap_dir())

    print(f"  -> Capture stopped: {outfile}")

    if transfer_failed:
        _log_transfer_failure(protocol, filename, qos, exit_code)
        return

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


# Broker protocols whose transfer is complete only when the receiver (the
# device, client-b) has written its row; value = CSV schema the receiver writes.
RECEIVER_CSV = {"mqtt": "mqtt", "mqtt-windowed": "mqtt", "amqp": "amqp"}
RECEIVER_SERVICE = {"mqtt": "mqtt-client-b", "mqtt-windowed": "mqtt-client-b",
                    "amqp": "amqp-client-b"}
# Slowest delivery rate the wait has to allow for (NB-IoT is ~25 kbit/s).
RECEIVER_MIN_BPS = int(os.getenv("RECEIVER_MIN_BPS", "16000"))
RECEIVER_BASE_TIMEOUT_S = 120


def _receiver_row_count(protocol: str) -> int | None:
    """Receiver rows already in the active run's CSV (None = not applicable)."""
    kind = RECEIVER_CSV.get(protocol)
    run_id = runs.active_run_id()
    if kind is None or not run_id:
        return None
    import csv

    path = os.path.join(runs.run_dir(os.environ.get("OUTPUT_DIR", "./output"), run_id),
                        f"{kind}_measurements.csv")
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return sum(1 for row in csv.DictReader(fh) if row.get("side") == "receiver")
    except OSError:
        return 0


def _wait_for_receiver(protocol: str, before: int, size_bytes: int) -> bool:
    """Block until the receiver writes a new row; False on timeout."""
    timeout = RECEIVER_BASE_TIMEOUT_S + size_bytes * 8 / RECEIVER_MIN_BPS
    deadline = time.time() + timeout
    next_note = time.time() + 30
    next_check = time.time() + 10
    while time.time() < deadline:
        if (_receiver_row_count(protocol) or 0) > before:
            return True
        if time.time() >= next_check:
            # Fail fast when the receiver process died (its container exits):
            # otherwise a crash costs the whole size-scaled timeout.
            if not _service_running(RECEIVER_SERVICE[protocol]):
                print(f"  -> ERROR: receiver {RECEIVER_SERVICE[protocol]} is no longer running")
                return False
            next_check += 10
        if time.time() >= next_note:
            print("  -> waiting for the device (receiver) to finish ...")
            next_note += 30
        time.sleep(1)
    return False


def _service_running(service: str) -> bool:
    """True if the compose service has a running container."""
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--status", "running", "--services"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return True          # unknown: keep waiting rather than abort
    if out.returncode != 0:
        return True
    return service in out.stdout.split()


def _log_transfer_failure(protocol: str, filename: str, qos, returncode) -> None:
    """Append a harness-level failure record to <run>/transfer_failures.csv.

    The export derives success rates from attempts (run.json) vs. verified
    rows, so a crashed transfer is never silently dropped; this file records
    why an attempt produced no row.
    """
    import csv

    run_id = runs.active_run_id()
    if not run_id:
        return
    path = os.path.join(runs.run_dir(os.environ.get("OUTPUT_DIR", "./output"), run_id),
                        "transfer_failures.csv")
    new = not os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(["protocol", "filename", "qos", "exit_code"])
        writer.writerow([protocol, filename, "" if qos is None else qos, returncode])


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