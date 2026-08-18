import csv
import json
import os

def _measurement_file(protocol: str) -> str:
    # Optional suffix keeps baseline and chaos runs in separate CSV files.
    suffix = os.getenv("MEASUREMENT_SUFFIX", "").strip()
    safe_suffix = suffix.replace(" ", "_")
    # Inside containers the default is /app/output; on the host the benchmark
    # harness sets OUTPUT_DIR=<project>/output.
    base = os.getenv("OUTPUT_DIR", "/app/output")
    return f"{base}/{protocol}_measurements{safe_suffix}.csv"

def write_to_csv(output_path: str, fieldnames: list, data: list[dict]):
    if not data:
        return

    file_exists = os.path.isfile(output_path)

    with open(output_path, 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerows(data)
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