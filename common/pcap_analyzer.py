import csv
import os
import shutil
import subprocess
from pathlib import Path

# Per-protocol config for tshark analysis.
#   filter:      protocol display filter used to isolate protocol frames
#   type_fields: tshark fields used to build the frame-type breakdown
#   is_tcp:      whether the transport is TCP (drives retransmission metrics)
PROTOCOL_CONFIG = {
    "mqtt": {
        "filter": "mqtt",
        "type_fields": ["mqtt.msgtype"],
        "is_tcp": True,
    },
    "http": {
        "filter": "http",
        "type_fields": ["http.request.method", "http.response.code"],
        "is_tcp": True,
    },
    "coap": {
        "filter": "coap",
        "type_fields": ["coap.code"],
        "is_tcp": False,
    },
}

RETRANSMISSION_FILTER = (
    "tcp.analysis.retransmission or "
    "tcp.analysis.fast_retransmission or "
    "tcp.analysis.spurious_retransmission"
)


def resolve_tshark() -> str:
    """Return the path to tshark, checking PATH and common install locations."""
    discovered = shutil.which("tshark")
    if not discovered:
        candidates = [
            r"C:\Program Files\Wireshark\tshark.exe",
            r"C:\Program Files (x86)\Wireshark\tshark.exe",
            "/usr/bin/tshark",
            "/usr/sbin/tshark",
        ]
        discovered = next(
            (p for p in candidates if os.path.exists(p)),
            None,
        )
    if not discovered:
        raise FileNotFoundError(
            "tshark not found on PATH. Install Wireshark (tshark is bundled "
            "with it) or add its folder to PATH."
        )
    return discovered


def run_tshark(pcap_file, display_filter=None, fields=None):
    """
    Run tshark and return rows of extracted fields.
    """
    command = [
        resolve_tshark(),
        "-r",
        str(pcap_file),
        "-T",
        "fields",
        "-E",
        "separator=,",
        "-E",
        "quote=d",
        "-E",
        "header=y",
    ]

    if display_filter:
        command.extend(["-Y", display_filter])

    for field in fields:
        command.extend(["-e", field])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout


def _validate_protocol(protocol: str) -> dict:
    if protocol not in PROTOCOL_CONFIG:
        raise ValueError(
            f"Unknown protocol {protocol!r}. Supported: {list(PROTOCOL_CONFIG)}"
        )
    return PROTOCOL_CONFIG[protocol]


def _parse_frame_type(line: str, type_fields: list[str]) -> str:
    """Build the frame-type label from the first non-empty type field."""
    parts = list(csv.reader([line]))[0]
    for field_idx, _ in enumerate(type_fields):
        # type_fields are requested after frame.number / frame.len
        value_index = 2 + field_idx
        if value_index < len(parts) and parts[value_index]:
            return parts[value_index]
    return "UNKNOWN"


def analyze_pcap(
    pcap_file,
    file_size_bytes,
    protocol="mqtt",
    filename=None,
    qos_level=None,
    label=None,
):
    """
    Analyze one protocol PCAP.

    file_size_bytes:
        Actual size of the binary file being transferred.

    Returns:
        Dictionary containing the measurements.
    """
    cfg = _validate_protocol(protocol)

    pcap_file = Path(pcap_file)

    if not pcap_file.exists():
        raise FileNotFoundError(f"PCAP does not exist: {pcap_file}")

    # ---------------------------------------------------------
    # 1. All captured frames
    # ---------------------------------------------------------

    output = run_tshark(
        pcap_file,
        fields=[
            "frame.number",
            "frame.len",
            "frame.time_relative",
            "ip.proto",
        ],
    )

    lines = output.strip().splitlines()

    # Remove header
    if len(lines) <= 1:
        raise RuntimeError("PCAP contains no packets.")

    packet_rows = lines[1:]

    total_packets = 0
    total_wire_bytes = 0
    last_timestamp = 0.0

    for line in packet_rows:
        if not line.strip():
            continue

        parts = list(csv.reader([line]))[0]

        if len(parts) < 3:
            continue

        try:
            frame_len = int(parts[1])
            timestamp = float(parts[2])
        except ValueError:
            continue

        total_packets += 1
        total_wire_bytes += frame_len
        last_timestamp = max(last_timestamp, timestamp)

    duration = last_timestamp

    # ---------------------------------------------------------
    # 2. Protocol packets
    # ---------------------------------------------------------

    proto_output = run_tshark(
        pcap_file,
        display_filter=cfg["filter"],
        fields=["frame.number", "frame.len"] + cfg["type_fields"],
    )

    proto_lines = proto_output.strip().splitlines()

    proto_packets = 0
    proto_wire_bytes = 0
    proto_packet_types = {}

    if len(proto_lines) > 1:
        for line in proto_lines[1:]:
            if not line.strip():
                continue

            parts = list(csv.reader([line]))[0]

            if len(parts) < 2:
                continue

            try:
                frame_len = int(parts[1])
            except ValueError:
                continue

            frame_type = _parse_frame_type(line, cfg["type_fields"])

            proto_packets += 1
            proto_wire_bytes += frame_len

            proto_packet_types[frame_type] = (
                proto_packet_types.get(frame_type, 0) + 1
            )

    # ---------------------------------------------------------
    # 3. Retransmissions (TCP-based protocols only)
    # ---------------------------------------------------------

    if cfg["is_tcp"]:
        retransmission_output = run_tshark(
            pcap_file,
            display_filter=RETRANSMISSION_FILTER,
            fields=["frame.number"],
        )

        retransmission_lines = [
            line
            for line in retransmission_output.strip().splitlines()[1:]
            if line.strip()
        ]

        tcp_retransmissions = len(retransmission_lines)
    else:
        # CoAP: detect retransmissions as repeated Message IDs in the pcap.
        # Only Confirmable (CON) messages are ever retransmitted (RFC 7252),
        # and a retransmission reuses the same MID from the same source. A
        # normal exchange is one CON plus one piggybacked ACK that echoes the
        # request MID, so counting raw MID frequency would over-count; group
        # CON frames per (mid, ip.src) instead and count repeats.
        con_output = run_tshark(
            pcap_file,
            display_filter="coap",
            fields=["coap.type", "coap.mid", "ip.src"],
        )

        con_counts = {}
        for line in con_output.strip().splitlines()[1:]:
            if not line.strip():
                continue
            parts = list(csv.reader([line]))[0]
            # columns: coap.type, coap.mid, ip.src
            if len(parts) >= 3:
                msg_type = parts[0].strip()
                mid = parts[1].strip()
                src = parts[2].strip()
                if msg_type == "0" and mid and src:  # 0 = CON
                    key = (mid, src)
                    con_counts[key] = con_counts.get(key, 0) + 1

        tcp_retransmissions = sum(
            count - 1 for count in con_counts.values() if count > 1
        )

    # ---------------------------------------------------------
    # 4. Calculate derived metrics
    # ---------------------------------------------------------

    if total_wire_bytes < file_size_bytes:
        missing = file_size_bytes - total_wire_bytes
        print(
            f"  WARNING: capture looks incomplete -- captured {total_wire_bytes:,} B"
            f" is less than the {file_size_bytes:,} B file that was verified"
            f" intact (integrity OK). Frames were dropped during capture"
            f" (~{missing:,} B missing); overhead numbers are unreliable."
            f" Re-run this transfer."
        )

    total_overhead_bytes = total_wire_bytes - file_size_bytes

    if file_size_bytes > 0:
        overhead_percentage = (
            total_overhead_bytes / file_size_bytes
        ) * 100
    else:
        overhead_percentage = 0

    if duration > 0:
        wire_throughput_mbps = (
            total_wire_bytes * 8
        ) / (duration * 1_000_000)

        goodput_mbps = (
            file_size_bytes * 8
        ) / (duration * 1_000_000)
    else:
        wire_throughput_mbps = 0
        goodput_mbps = 0

    return {
        "filename": filename,
        "label": label,
        "protocol": protocol,
        "qos": qos_level,
        "file_size_bytes": file_size_bytes,
        "total_packets": total_packets,
        "total_wire_bytes": total_wire_bytes,
        "protocol_packets": proto_packets,
        "protocol_wire_bytes": proto_wire_bytes,
        "retransmissions": tcp_retransmissions,
        "duration_seconds": duration,
        "total_overhead_bytes": total_overhead_bytes,
        "overhead_percentage": overhead_percentage,
        "wire_throughput_mbps": wire_throughput_mbps,
        "goodput_mbps": goodput_mbps,
        "packet_types": proto_packet_types,
    }


def print_result(result):
    print("\n========== PCAP ANALYSIS ==========")

    print(f"Protocol:              {result['protocol']}")
    print(f"File:                  {result['filename']}")
    if result["qos"] is not None:
        print(f"QoS:                   {result['qos']}")

    print("\n--- Traffic ---")

    print(f"File size:             {result['file_size_bytes']:,} B")
    print(f"Captured packets:      {result['total_packets']:,}")
    print(f"Captured bytes:        {result['total_wire_bytes']:,} B")
    print(f"Protocol packets:      {result['protocol_packets']:,}")
    print(f"Protocol frame bytes:  {result['protocol_wire_bytes']:,} B")

    print("\n--- Overhead ---")

    print(
        f"Total overhead:        "
        f"{result['total_overhead_bytes']:,} B"
    )

    print(
        f"Overhead percentage:   "
        f"{result['overhead_percentage']:.2f}%"
    )

    print("\n--- Performance ---")

    print(
        f"Duration:              "
        f"{result['duration_seconds']:.4f} s"
    )

    print(
        f"Goodput:               "
        f"{result['goodput_mbps']:.3f} Mbps"
    )

    print(
        f"Wire throughput:       "
        f"{result['wire_throughput_mbps']:.3f} Mbps"
    )

    print(
        f"Retransmissions:       "
        f"{result['retransmissions']}"
    )

    print("\n--- Protocol packet types ---")

    for packet_type, count in result["packet_types"].items():
        print(f"{packet_type:20} {count}")

    print("===================================\n")


if __name__ == "__main__":
    pcap = "output/pcap/mqtt_binary_file_1mb.bin_1.pcap"
    file_size = 1024 * 1024
    filename = "binary_file_1mb.bin"

    result = analyze_pcap(
        pcap,
        file_size,
        protocol="mqtt",
        filename=filename,
        qos_level=1,
    )

    print_result(result)