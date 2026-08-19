import csv
import json
import os
from datetime import datetime, timezone

# Importing from ../common keeps the module importable from inside containers
# (the project root is on sys.path there) and from the host harness.
try:
    import common.runs as runs
except ImportError:  # pragma: no cover - fallback when run outside the project
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import common.runs as runs


# Columns appended to every measurement row so each CSV is self-describing
# even if concatenated across runs.
META_FIELDS = ["run_id", "timestamp", "network_profile"]


def _measurement_dir() -> str:
    """Directory that holds the {kind}_measurements.csv files for the active run.

    When a run is active (RUN_ID env or .active_run marker) writes go to
    <OUTPUT_DIR>/runs/<run_id>/; otherwise they fall back to the legacy flat
    <OUTPUT_DIR> (e.g. a manual transfer driven without the run-aware CLI).
    """
    output_dir = os.getenv("OUTPUT_DIR", "/app/output")
    run_id = runs.active_run_id()
    if run_id:
        return runs.run_dir(output_dir, run_id)
    return output_dir


def _measurement_file(protocol: str) -> str:
    base = _measurement_dir()
    return f"{base}/{protocol}_measurements.csv"


def _meta_row() -> dict:
    run_id = runs.active_run_id() or ""
    return {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network_profile": os.getenv("NETWORK_PROFILE", ""),
    }


def _existing_header(path: str) -> list[str] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return next(csv.reader(fh))
    except (OSError, StopIteration):
        return None


def write_to_csv(output_path: str, fieldnames: list, data: list[dict]):
    """Append rows, prepending run metadata columns where the file supports them.

    Files created under the run layout always get the metadata columns. Preexisting
    legacy files (without them) are appended to unchanged so old data stays valid.
    """
    if not data:
        return

    header = _existing_header(output_path)
    use_meta = header is None or header[: len(META_FIELDS)] == META_FIELDS

    meta = _meta_row()
    rows = []
    for row in data:
        record = {k: v for k, v in row.items() if k not in META_FIELDS}
        if use_meta:
            record = {**meta, **record}
        rows.append(record)

    if use_meta:
        all_fields = META_FIELDS + [f for f in fieldnames if f not in META_FIELDS]
    else:
        all_fields = [f for f in fieldnames if f not in META_FIELDS]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=all_fields)

        if header is None:
            writer.writeheader()

        writer.writerows(rows)
        print(f"Writing to {output_path}")

# Protocol/overhead metrics come from pcap analysis (write_to_file_pcap);
# the per-transfer CSVs below log client-side runtime metrics only.
def write_to_file_http(data: list[dict]):
    output_path = _measurement_file("http")
    fieldnames = [
        'protocol',
        'file_size',
        'time_to_transfer',
        'latency_tcp_rtt',
        'latency_ttfb',
        'goodput_mbps',
        'integrity_ok',
        'avg_cpu_usage',
        'peak_ram_usage',
        'energy_est',
    ]
    write_to_csv(output_path, fieldnames, data)

def write_to_file_mqtt(data: list[dict]):
    output_path = _measurement_file("mqtt")
    fieldnames = [
        'protocol',
        'qos',
        'side',
        'file_size',
        'sender_duration',
        'receiver_duration',
        'latency',
        'goodput_mbps',
        'integrity_ok',
        'avg_cpu_usage',
        'peak_ram_usage',
        'energy_est',
    ]
    write_to_csv(output_path, fieldnames, data)

def write_to_file_coap(data: list[dict]):
    output_path = _measurement_file("coap")
    fieldnames = [
        'protocol',
        'file_size',
        'time_to_transfer',
        'latency',
        'goodput_mbps',
        'integrity_ok',
        'avg_cpu_usage',
        'peak_ram_usage',
        'energy_est',
    ]
    write_to_csv(output_path, fieldnames, data)

def write_to_file_pcap(data: list[dict]):
    """Append pcap-derived analysis results (from common.pcap_analyzer)."""
    output_path = _measurement_file("pcap")
    rows = []
    for row in data:
        record = dict(row)
        if isinstance(record.get("packet_types"), dict):
            record["packet_types"] = json.dumps(record["packet_types"])
        rows.append(record)

    fieldnames = [
        'protocol',
        'filename',
        'label',
        'qos',
        'file_size_bytes',
        'total_packets',
        'total_wire_bytes',
        'protocol_packets',
        'protocol_wire_bytes',
        'retransmissions',
        'duration_seconds',
        'total_overhead_bytes',
        'overhead_percentage',
        'wire_throughput_mbps',
        'goodput_mbps',
        'packet_types',
    ]
    write_to_csv(output_path, fieldnames, rows)
