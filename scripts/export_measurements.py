"""
Export every captured benchmark measurement into Markdown documents.

Two documents are emitted from the same dataset (identical run selection
and pcap re-analysis):

  measurements_export.md       per-protocol detail: one section per
                               protocol, client + packet-side tables per
                               network profile
  measurements_comparison.md    cross-protocol comparison: per profile,
                               one table per metric with the protocols as
                               columns (MQTT split into QoS 1 / QoS 2)

pcap time columns are re-analyzed with the current (post-FIXED-9) analyzer
so they are trustworthy; byte-derived columns are identical to the run
CSVs. Re-analysis results are cached in output/.pcap_reanalysis_cache.json
(keyed by pcap path + mtime), so regenerations after the first are fast.

Usage (from the project root):
    python scripts/export_measurements.py
    python scripts/export_measurements.py --protocols http --profiles good
    python scripts/export_measurements.py -o output/my_export.md \
        --comparison-output output/my_comparison.md

Output is plain Markdown with GFM tables -- copy/paste straight into Word.
"""

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

# Allow `python scripts/export_measurements.py` from the project root.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from common.pcap_analyzer import analyze_pcap  # noqa: E402

PROTOCOLS = ["mqtt", "http", "coap", "amqp", "grpc", "lwm2m"]
PROFILES = ["good", "iot", "harsh", "mobile", "satellite"]

# The payload set used by every recorded run (data/binary_file_generator.py
# output present on disk).
SIZE_ORDER = [256000, 1048576, 5242880, 20971520, 52428800]
SIZE_LABELS = {
    256000: "250 KB",
    1048576: "1 MB",
    5242880: "5 MB",
    20971520: "20 MB",
    52428800: "50 MB",
}

# Broker/gRPC chunk size -- mirrors the clients' CHUNK_SIZE; files that fit
# in one chunk have no measurable receiver-side arrival window.
CHUNK_SIZE = 1024 * 1024

NA_TEXT = "N/A (single chunk)"
NA_SINGLE_CHUNK = NA_TEXT + "\u00b9"
DASH = "\u2014"  # em dash for empty/not-applicable cells
WARN = "\u26a0"  # degraded-capture marker

CACHE_FILENAME = ".pcap_reanalysis_cache.json"


# ---------------------------------------------------------------------------
# Run discovery / selection
# ---------------------------------------------------------------------------

def load_runs(runs_dir):
    """Runs with a manifest; the manual scratch run (no profile) is skipped."""
    runs = []
    if not os.path.isdir(runs_dir):
        return runs
    for name in sorted(os.listdir(runs_dir)):
        manifest_path = os.path.join(runs_dir, name, "run.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        protocol = manifest.get("protocol", "")
        profile = manifest.get("network_profile", "")
        if protocol not in PROTOCOLS or profile not in PROFILES:
            continue
        runs.append(
            {
                "id": name,
                "dir": os.path.join(runs_dir, name),
                "protocol": protocol,
                "profile": profile,
                "manifest": manifest,
            }
        )
    return runs


def read_csv_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def client_rows(run):
    return read_csv_rows(os.path.join(run["dir"], f"{run['protocol']}_measurements.csv"))


def sizes_covered(rows):
    covered = set()
    for row in rows:
        try:
            covered.add(round(float(row["file_size"]) * 1024 * 1024))
        except (KeyError, ValueError):
            continue
    return covered


def pick_canonical(runs, protocol, profile):
    """Newest complete run for the combination (falls back to newest partial)."""
    candidates = sorted(
        (r for r in runs if r["protocol"] == protocol and r["profile"] == profile),
        key=lambda r: r["id"],
        reverse=True,
    )
    for run in candidates:
        if sizes_covered(client_rows(run)) >= set(SIZE_ORDER):
            return run, True
    return (candidates[0], False) if candidates else (None, False)


def key_rows(rows):
    """Client CSV rows keyed by (size_bytes, qos, side)."""
    out = {}
    for row in rows:
        try:
            size = round(float(row["file_size"]) * 1024 * 1024)
        except (KeyError, ValueError):
            continue
        out[(size, row.get("qos", ""), row.get("side", ""))] = row
    return out


# ---------------------------------------------------------------------------
# Re-analysis cache
# ---------------------------------------------------------------------------

def load_cache(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path, cache):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
    except OSError as exc:
        print(f"WARNING: could not write re-analysis cache {path}: {exc}")


# ---------------------------------------------------------------------------
# Dataset: canonical run + client rows + re-analyzed pcap results
# ---------------------------------------------------------------------------

def reanalyze_pcap(run, row, cache):
    """Analyze one pcap (cache-aware).

    Returns (status, result): status in {"ok", "no-capture", "failed"};
    result is the analyze_pcap dict when status == "ok".
    """
    protocol = run["protocol"]
    label = row.get("label")
    try:
        size = int(row["file_size_bytes"])
    except (KeyError, ValueError):
        return "failed", None

    pcap_path = os.path.join(run["dir"], "pcap", f"{protocol}_{label}.pcap")
    if not os.path.isfile(pcap_path):
        return "no-capture", None

    try:
        mtime = f"{os.path.getmtime(pcap_path):.0f}"
    except OSError:
        mtime = "?"
    key = f"{run['id']}|{label}|{size}|{mtime}"
    if key in cache:
        return "ok", cache[key]

    qos_level = int(row["qos"]) if row.get("qos", "").strip() else None
    try:
        result = analyze_pcap(
            pcap_path,
            size,
            protocol=protocol,
            filename=row.get("filename"),
            qos_level=qos_level,
            label=label,
        )
    except Exception as exc:  # one bad pcap must not kill the whole export
        print(f"    WARNING: pcap analysis failed for {os.path.basename(pcap_path)}: {exc}")
        return "failed", None

    cache[key] = result
    return "ok", result


def collect_dataset(runs, protocols, profiles, cache):
    """dataset[(protocol, profile)] -> entry (or None when never run)."""
    dataset = {}
    for protocol in protocols:
        for profile in profiles:
            run, complete = pick_canonical(runs, protocol, profile)
            if run is None:
                dataset[(protocol, profile)] = None
                continue
            print(f"  {protocol}/{profile}: run {run['id']} (complete={complete})")
            print("    re-analyzing pcaps ...")
            rows = client_rows(run)
            entry = {
                "run_id": run["id"],
                "complete": complete,
                "client": rows,
                "client_keyed": key_rows(rows),
                "pcap_rows": read_csv_rows(os.path.join(run["dir"], "pcap_measurements.csv")),
                "pcap_results": {},
                "pcap_status": {},
            }
            for row in entry["pcap_rows"]:
                try:
                    size = int(row["file_size_bytes"])
                except (KeyError, ValueError):
                    continue
                qos = row.get("qos", "").strip()
                status, result = reanalyze_pcap(run, row, cache)
                entry["pcap_status"][(size, qos)] = status
                entry["pcap_results"][(size, qos)] = result
            dataset[(protocol, profile)] = entry
    return dataset


# ---------------------------------------------------------------------------
# Cell formatting helpers
# ---------------------------------------------------------------------------

def fmt(value, dash=DASH):
    """None / empty / 'X' -> em dash; anything else passes through."""
    if value is None:
        return dash
    text = str(value).strip()
    if text == "" or text.upper() == "X":
        return dash
    return text


def is_single_chunk(size_bytes):
    return math.ceil(size_bytes / CHUNK_SIZE) < 2


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def not_run_row(label, n_columns):
    cells = [label, "not run"] + [""] * (n_columns - 2)
    return [fmt(c, dash="") for c in cells]


# ---------------------------------------------------------------------------
# Document 1: per-protocol detail (measurements_export.md)
# ---------------------------------------------------------------------------

CLIENT_HEADERS = {
    "mqtt": ["Size", "QoS", "Side", "Duration s", "Latency s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Energy J", "Samples", "Integrity"],
    "http": ["Size", "Transfer s", "TCP RTT s", "TTFB s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Energy J", "Samples", "Integrity"],
    "coap": ["Size", "Transfer s", "Latency s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Energy J", "Samples", "Integrity"],
    "amqp": ["Size", "Side", "Duration s", "Latency s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Energy J", "Samples", "Integrity"],
    "grpc": ["Size", "Side", "Duration s", "Latency s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Energy J", "Samples", "Integrity"],
    "lwm2m": ["Size", "Download s", "Reg. RTT s", "Goodput Mbps",
              "Avg CPU", "Peak RAM", "Energy J", "Samples", "Integrity"],
}


def duration_cell(protocol, row, side, size):
    """Duration/goodput cells, with the single-chunk receiver guard."""
    if protocol in ("mqtt", "amqp", "grpc") and side == "receiver" and is_single_chunk(size):
        return NA_SINGLE_CHUNK, NA_SINGLE_CHUNK
    if protocol in ("mqtt", "amqp", "grpc"):
        field = "sender_duration" if side == "sender" else "receiver_duration"
        return fmt(row.get(field)), fmt(row.get("goodput_mbps"))
    if protocol == "http":
        return fmt(row.get("time_to_transfer")), fmt(row.get("goodput_mbps"))
    if protocol == "coap":
        return fmt(row.get("time_to_transfer")), fmt(row.get("goodput_mbps"))
    if protocol == "lwm2m":
        return fmt(row.get("download_duration")), fmt(row.get("goodput_mbps"))
    return DASH, DASH


def resource_cells(row):
    return (
        fmt(row.get("avg_cpu_usage")),
        fmt(row.get("peak_ram_usage")),
        fmt(row.get("energy_est")),
        fmt(row.get("sample_count")),
        fmt(row.get("integrity_ok")),
    )


def render_client_table(protocol, rows):
    header = CLIENT_HEADERS[protocol]
    keyed = key_rows(rows)
    body = []

    for size in SIZE_ORDER:
        label = SIZE_LABELS[size]
        if protocol == "mqtt":
            emitted = False
            for qos in ("1", "2"):
                for side in ("sender", "receiver"):
                    row = keyed.get((size, qos, side))
                    if row is None:
                        continue
                    duration, goodput = duration_cell(protocol, row, side, size)
                    cpu, ram, energy, samples, integrity = resource_cells(row)
                    body.append([label, f"qos {qos}", side, duration,
                                 fmt(row.get("latency")), goodput,
                                 cpu, ram, energy, samples, integrity])
                    emitted = True
            if not emitted:
                body.append(not_run_row(label, len(header)))
        elif protocol in ("amqp", "grpc"):
            emitted = False
            for side in ("sender", "receiver"):
                row = keyed.get((size, "", side))
                if row is None:
                    continue
                duration, goodput = duration_cell(protocol, row, side, size)
                cpu, ram, energy, samples, integrity = resource_cells(row)
                body.append([label, side, duration, fmt(row.get("latency")),
                             goodput, cpu, ram, energy, samples, integrity])
                emitted = True
            if not emitted:
                body.append(not_run_row(label, len(header)))
        else:
            # LwM2M rows carry side="client"; HTTP/CoAP have no side column.
            side_key = "client" if protocol == "lwm2m" else ""
            row = keyed.get((size, "", side_key))
            if row is None:
                body.append(not_run_row(label, len(header)))
                continue
            duration, goodput = duration_cell(protocol, row, "", size)
            cpu, ram, energy, samples, integrity = resource_cells(row)
            if protocol == "http":
                body.append([label, duration, fmt(row.get("latency_tcp_rtt")),
                             fmt(row.get("latency_ttfb")), goodput,
                             cpu, ram, energy, samples, integrity])
            else:
                body.append([label, duration, fmt(row.get("latency")), goodput,
                             cpu, ram, energy, samples, integrity])

    return md_table(header, body)


PCAP_HEADER = ["Size", "QoS", "Duration s\u00b2", "Packets", "Wire bytes",
               "Overhead %", "Retrans", "Pcap goodput Mbps", "Wire Mbps"]


def render_pcap_table(entry):
    body = []
    seen_sizes = set()

    for row in entry["pcap_rows"]:
        try:
            size = int(row["file_size_bytes"])
        except (KeyError, ValueError):
            continue
        seen_sizes.add(size)
        label = SIZE_LABELS.get(size, f"{size / 1024 / 1024:.3g} MB")
        qos = fmt(row.get("qos"), dash="")
        qos_cell = f"qos {qos}" if qos else ""
        qos_key = row.get("qos", "").strip()
        status = entry["pcap_status"].get((size, qos_key))
        result = entry["pcap_results"].get((size, qos_key))

        if status != "ok" or result is None:
            reason = "no capture" if status == "no-capture" else "analysis failed"
            body.append([label, qos_cell, reason] + [""] * (len(PCAP_HEADER) - 3))
            continue

        # Flag captures that dropped frames: wire bytes below the verified
        # file size mean the overhead/throughput columns are unreliable.
        dropped = result["total_wire_bytes"] < size
        duration_cell = f"{result['duration_seconds']:.2f}"
        if dropped:
            duration_cell += f" {WARN}"

        body.append([
            label,
            qos_cell,
            duration_cell,
            f"{result['total_packets']:,}",
            f"{result['total_wire_bytes']:,}",
            f"{result['overhead_percentage']:.2f}",
            str(result["retransmissions"]),
            f"{result['goodput_mbps']:.3f}",
            f"{result['wire_throughput_mbps']:.3f}",
        ])

    for size in SIZE_ORDER:
        if size not in seen_sizes:
            body.append(not_run_row(SIZE_LABELS[size], len(PCAP_HEADER)))

    return md_table(PCAP_HEADER, body)


def render_protocol(dataset, protocol, profiles):
    lines = [f"## {protocol.upper()}", ""]

    for profile in profiles:
        entry = dataset.get((protocol, profile))
        lines.append(f"### {protocol.upper()} \u2014 {profile}")
        lines.append("")

        if entry is None:
            lines.append("**Not run.**")
            lines.append("")
            continue

        note = f"_Run: `{entry['run_id']}`_"
        if not entry["complete"]:
            note += (
                " \u2014 *partial run: some sizes were attempted but never"
                " completed/recorded client-side (large files struggle under"
                " this profile, ISSUES.md OPEN-4); missing client sizes are"
                " marked 'not run' and the packet-side table may still list"
                " their (degraded) captures.*"
            )
        lines.append(note)
        lines.append("")

        lines.append("#### Client measurements")
        lines.append("")
        lines.extend(render_client_table(protocol, entry["client"]))
        lines.append("")
        lines.append("#### Packet-side measurements (pcap, re-analyzed)")
        lines.append("")
        lines.extend(render_pcap_table(entry))
        lines.append("")

    return lines


FOOTNOTES = None  # filled by build_footnotes() once the commit hash is known


def build_footnotes(commit):
    return f"""**How to read this document**

- All pcap time metrics (`Duration s\u00b2`, `Pcap goodput`, `Wire Mbps`) are
  **re-analyzed from the stored pcaps** with the current analyzer (commit
  {commit}): duration spans the first to the last frame of the
  protocol's own traffic window, so idle startup and ARP/ICMPv6 noise no
  longer inflate it (ISSUES.md FIXED-9). Byte-derived columns (packets, wire
  bytes, overhead, retransmissions) are identical to the run CSVs.
- \u00b9 **{NA_TEXT}**: a file that fits in one 1 MB chunk spans no
  measurable receiver-side arrival window; pre-fix runs recorded misleading
  ~0.00 s / 1500+ Mbps cells there, which are shown as N/A (ISSUES.md
  FIXED-13).
- \u00b2 see the first bullet.
- Under high-latency profiles (`satellite`, `harsh`) the pcap window also
  includes protocol control traffic around the data transfer itself --
  connection/channel setup, keepalive/BDP pings, and broker-receiver QoS
  retransmissions -- so `Duration s\u00b2` can exceed the client-side transfer
  window. The client-side columns are the transfer-only view.
- \u26a0 marks captures that dropped frames (captured wire bytes below the
  verified file size): the overhead/throughput columns of that row are
  unreliable (see docs/troubleshooting.md -- re-running the transfer is the
  remedy, which was not done for the historical coap harsh 20/50 MB rows).
- **MQTT/AMQP sender duration**: runs recorded before commit d2426af include
  the metadata-ACK round trip inside `Duration s`; runs after it (all runs
  dated 2026-11-20) time chunk transmission only (ISSUES.md FIXED-12).
- **Samples** is the CPU/RAM sample count behind the averages
  (ISSUES.md FIXED-10). Pre-fix runs did not record it (\u2014) and their
  CPU/energy can read 0 on very fast transfers.
- Sender-side **Integrity** is \u2014 for MQTT/AMQP by design: the sender hands
  the file to the broker and cannot observe the receiver's checksum result.
  gRPC sender rows show the server-reported result from the Upload reply.
- **"not run"** combinations were never executed: gRPC under `mobile`,
  LwM2M under `harsh` (blockwise pull at 300 ms RTT takes hours, ISSUES.md
  OPEN-4) and CoAP/LwM2M under `satellite`.
- Per protocol \u00d7 profile the newest **complete** run is used; older
  partial runs (e.g. the aborted gRPC harsh sweep) are superseded.
- **Network scenario asymmetry** (ISSUES.md OPEN-5): the brokers are stock
  images and are not tc-shaped, so MQTT/AMQP face one constrained link
  while HTTP/CoAP/gRPC/LwM2M face shaping on both ends. Keep this in mind
  when comparing protocols under the same profile.
"""


def render_export_doc(dataset, protocols, profiles, commit):
    lines = [
        "# Benchmark Measurements Export",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} \u00b7 "
        f"analyzer at commit `{commit}` \u00b7 payloads: 250 KB \u2013 50 MB",
        "",
        "Companion document: `measurements_comparison.md` (side-by-side"
        " protocol comparison).",
        "",
    ]
    for protocol in protocols:
        lines.extend(render_protocol(dataset, protocol, profiles))
    lines.append("---")
    lines.append("")
    lines.append(build_footnotes(commit))
    return lines


# ---------------------------------------------------------------------------
# Document 2: cross-protocol comparison (measurements_comparison.md)
# ---------------------------------------------------------------------------

# (protocol, qos, column label) -- MQTT split into its two QoS levels.
COMPARE_COLUMNS = [
    ("mqtt", "1", "MQTT QoS 1"),
    ("mqtt", "2", "MQTT QoS 2"),
    ("http", "", "HTTP"),
    ("coap", "", "CoAP"),
    ("amqp", "", "AMQP"),
    ("grpc", "", "gRPC"),
    ("lwm2m", "", "LwM2M"),
]

# Which client CSV row holds each protocol's transfer/sender view.
CLIENT_ROW_KEY = {
    "mqtt": lambda size, qos: (size, qos, "sender"),
    "http": lambda size, qos: (size, "", ""),
    "coap": lambda size, qos: (size, "", ""),
    "amqp": lambda size, qos: (size, "", "sender"),
    "grpc": lambda size, qos: (size, "", "sender"),
    "lwm2m": lambda size, qos: (size, "", "client"),
}

# Transfer-time / latency column names differ per protocol schema.
TRANSFER_FIELD = {
    "mqtt": "sender_duration",
    "http": "time_to_transfer",
    "coap": "time_to_transfer",
    "amqp": "sender_duration",
    "grpc": "sender_duration",
    "lwm2m": "download_duration",
}
LATENCY_FIELD = {
    "mqtt": "latency",
    "http": "latency_tcp_rtt",
    "coap": "latency",
    "amqp": "latency",
    "grpc": "latency",
    "lwm2m": "latency",
}
# Uniform client metrics (same CSV column for every protocol) get their
# field dicts built inline at the call sites below.


def make_client_field(field_by_protocol):
    def field_fn(dataset, protocol, profile, qos, size):
        entry = dataset.get((protocol, profile))
        if entry is None:
            return None
        row = entry["client_keyed"].get(CLIENT_ROW_KEY[protocol](size, qos))
        if row is None:
            return None
        value = row.get(field_by_protocol[protocol])
        if value is None:
            return None
        text = str(value).strip()
        if text == "" or text.upper() == "X":
            return None
        return text
    return field_fn


def make_pcap_field(result_key):
    """pcap-metric extractor: returns the raw value or None.

    Degraded captures (dropped frames: wire bytes below the verified file
    size) are excluded from comparison cells -- their derived numbers are
    unreliable.
    """
    def field_fn(dataset, protocol, profile, qos, size):
        entry = dataset.get((protocol, profile))
        if entry is None:
            return None
        result = entry["pcap_results"].get((size, qos))
        if result is None:
            return None
        if result["total_wire_bytes"] < size:
            return None
        return result[result_key]
    return field_fn


def fmt_raw(value):
    return DASH if value is None else value


def fmt_pct(value):
    return DASH if value is None else f"{value:.2f}"


def fmt_int(value):
    return DASH if value is None else str(value)


def render_compare_metric_table(dataset, profile, title, field_fn, cell_fmt):
    """One metric, one profile: rows = file sizes, columns = protocols."""
    header = ["Size"] + [label for _, _, label in COMPARE_COLUMNS]
    body = []
    for size in SIZE_ORDER:
        cells = [SIZE_LABELS[size]]
        for protocol, qos, _ in COMPARE_COLUMNS:
            value = field_fn(dataset, protocol, profile, qos, size)
            cells.append(cell_fmt(value))
        body.append(cells)
    return [f"### {title}", "", *md_table(header, body), ""]


def render_headline_matrix(dataset, profiles, title, field_fn, cell_fmt, size):
    """One metric, one file size: rows = profiles, columns = protocols."""
    header = ["Profile"] + [label for _, _, label in COMPARE_COLUMNS]
    body = []
    for profile in profiles:
        cells = [profile]
        for protocol, qos, _ in COMPARE_COLUMNS:
            value = field_fn(dataset, protocol, profile, qos, size)
            cells.append(cell_fmt(value))
        body.append(cells)
    return [f"## {title}", "", *md_table(header, body), ""]


def render_comparison_profile(dataset, profile):
    lines = [f"## Profile: {profile}", ""]
    metric_tables = [
        ("Transfer time (s)", make_client_field(TRANSFER_FIELD), fmt_raw),
        ("Client goodput (Mbps)",
         make_client_field({p: "goodput_mbps" for p in PROTOCOLS}), fmt_raw),
        ("Latency (s) \u00b3", make_client_field(LATENCY_FIELD), fmt_raw),
        ("Avg CPU (%)",
         make_client_field({p: "avg_cpu_usage" for p in PROTOCOLS}), fmt_raw),
        ("Peak RAM (MB)",
         make_client_field({p: "peak_ram_usage" for p in PROTOCOLS}), fmt_raw),
        ("Energy (J)",
         make_client_field({p: "energy_est" for p in PROTOCOLS}), fmt_raw),
        ("Wire overhead % (pcap)", make_pcap_field("overhead_percentage"), fmt_pct),
        ("Retransmissions (pcap)", make_pcap_field("retransmissions"), fmt_int),
    ]
    for title, field_fn, cell_fmt in metric_tables:
        lines += render_compare_metric_table(dataset, profile, title, field_fn, cell_fmt)
    return lines


def build_comparison_footnotes():
    return """**How to read the comparison document**

- Same dataset and run selection as `measurements_export.md` (newest
  complete run per protocol \u00d7 profile; pcaps re-analyzed with the current
  analyzer). Receiver-side views, per-row sample counts and integrity
  values live in that detail document.
- Cells use the **sender-side** client measurements for MQTT/AMQP/gRPC,
  the single client measurement for HTTP/CoAP, and the device-side download
  view for LwM2M.
- \u00b3 **Latency definitions differ per protocol**: MQTT/AMQP = metadata
  publish-ack round trip; HTTP = bare TCP connect; CoAP = discovery GET;
  gRPC = Ping RPC; LwM2M = registration. Treat the latency table as a rough
  round-trip responsiveness comparison only.
- **Timing provenance**: runs dated 2026-11-20 (gRPC harsh, the satellite
  sweeps, the HTTP good verification run) use post-fix timing, where
  MQTT/AMQP transfer time excludes the metadata round trip; all older runs
  include it (bounded by one broker RTT, ISSUES.md FIXED-12). Pre-fix
  CPU/energy can read 0 on fast transfers \u2014 sample counts are in the
  detail document.
- \u2014 = **not run or attempted-but-uncompleted**: gRPC mobile; gRPC iot
  50 MB; coap harsh 20/50 MB; LwM2M harsh; CoAP/LwM2M satellite. The
  coap harsh 20/50 MB pcap rows exist but were frame-dropped and are
  excluded from the pcap-side cells (see the \u26a0 rows in the detail
  document).
- Wire overhead % and retransmissions are byte/packet-derived and
  unaffected by the timing fixes.
- Every recorded transfer in the included runs passed integrity
  verification.
- **Network scenario asymmetry** (ISSUES.md OPEN-5): the brokers are stock
  images and are not tc-shaped, so MQTT/AMQP face one constrained link
  while HTTP/CoAP/gRPC/LwM2M face shaping on both ends \u2014 the direct
  protocols carry a harder ACK path under chaos profiles.
"""


def render_comparison_doc(dataset, protocols, profiles, commit):
    lines = [
        "# Protocol Comparison \u2014 Benchmark Measurements",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} \u00b7 "
        f"analyzer at commit `{commit}` \u00b7 payloads: 250 KB \u2013 50 MB",
        "",
        "Companion to `measurements_export.md` \u2014 same runs, same re-analyzed"
        " pcaps; per-protocol detail, receiver-side views and per-row samples"
        " live there.",
        "",
    ]

    goodput_field = make_client_field({p: "goodput_mbps" for p in PROTOCOLS})
    overhead_field = make_pcap_field("overhead_percentage")

    lines += render_headline_matrix(
        dataset, profiles, "Headline: client goodput (Mbps) at 50 MB",
        goodput_field, fmt_raw, 52428800)
    lines += render_headline_matrix(
        dataset, profiles, "Headline: client goodput (Mbps) at 250 KB",
        goodput_field, fmt_raw, 256000)
    lines += render_headline_matrix(
        dataset, profiles, "Headline: wire overhead % at 50 MB (pcap)",
        overhead_field, fmt_pct, 52428800)

    for profile in profiles:
        lines += render_comparison_profile(dataset, profile)

    lines.append("---")
    lines.append("")
    lines.append(build_comparison_footnotes())
    return lines


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def git_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=_PROJECT_ROOT,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def write_doc(path, lines):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nWrote {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default=os.path.join("output", "runs"))
    parser.add_argument("-o", "--output",
                        default=os.path.join("output", "measurements_export.md"))
    parser.add_argument("--comparison-output",
                        default=os.path.join("output", "measurements_comparison.md"))
    parser.add_argument("--protocols", nargs="+", choices=PROTOCOLS, default=PROTOCOLS)
    parser.add_argument("--profiles", nargs="+", default=PROFILES)
    args = parser.parse_args()

    commit = git_commit()
    runs = load_runs(args.runs_dir)
    print(f"Found {len(runs)} runs in {args.runs_dir}")

    cache_file = os.path.join(
        os.path.dirname(os.path.abspath(args.runs_dir)), CACHE_FILENAME)
    cache = load_cache(cache_file)
    dataset = collect_dataset(runs, args.protocols, args.profiles, cache)
    save_cache(cache_file, cache)

    write_doc(args.output,
              render_export_doc(dataset, args.protocols, args.profiles, commit))
    write_doc(args.comparison_output,
              render_comparison_doc(dataset, args.protocols, args.profiles, commit))


if __name__ == "__main__":
    main()
