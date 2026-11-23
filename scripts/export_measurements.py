"""
Export every captured benchmark measurement into Markdown documents.

Two documents are emitted from the same dataset (identical run selection
and pcap re-analysis):

  measurements_export.md       per-protocol detail: one section per
                               protocol, client + packet-side tables per
                               network profile
  measurements_comparison.md   cross-protocol comparison: per profile,
                               one table per metric with the protocols as
                               columns (MQTT split into QoS 1 / QoS 2)

Two selection modes:

  default         newest complete run per protocol x profile (one run per
                  cell; used for the legacy runs, e.g.
                  --runs-dir output/runs-legacy-v1)
  --sweep-id ...  every run of the given sweep(s) (runner.py --repeat N
                  --sweep-id X). Each cell shows median [Q1-Q3], n and the
                  success rate (verified transfers / attempts recorded in
                  run.json, so a transfer that crashed without writing a row
                  still counts as a failure).

TLS runs (runner.py --tls) appear as their own columns, e.g. "http-get+tls".

pcap time columns are re-analyzed with the current analyzer so they are
trustworthy; byte-derived columns are identical to the run CSVs.
Re-analysis results are cached in <runs-dir>/../.pcap_reanalysis_cache.json
(keyed by run + pcap + mtime), so regenerations after the first are fast.

Usage (from the project root):
    python scripts/export_measurements.py --sweep-id sweep-good sweep-iot
    python scripts/export_measurements.py --runs-dir output/runs-legacy-v1
    python scripts/export_measurements.py --protocols http-get --profiles good

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
from common.stats import quartiles, to_number  # noqa: E402

# Base protocols (= runner/manifest protocol keys) and the column variants
# derived from them. A TLS run of protocol P is reported as "P+tls".
BASE_PROTOCOLS = ["mqtt", "mqtt-windowed", "http", "http-get", "coap", "amqp", "grpc", "lwm2m"]
TLS_BASES = ["mqtt", "http", "http-get"]
PROTOCOLS = [
    "mqtt", "mqtt+tls", "mqtt-windowed", "http", "http+tls", "http-get",
    "http-get+tls", "coap", "amqp", "grpc", "lwm2m",
]
PROFILES = ["good", "iot", "harsh", "mobile", "satellite", "ltem", "nbiot"]

# Sizes used when a run's manifest does not list its payloads.
DEFAULT_SIZES = [256000, 1048576, 5242880, 20971520, 52428800]
KNOWN_SIZE_LABELS = {
    256000: "250 KB",
    1048576: "1 MB",
    5242880: "5 MB",
    20971520: "20 MB",
    52428800: "50 MB",
}
# Rendered sizes: set in main() from the selected runs' manifests.
SIZE_ORDER = list(DEFAULT_SIZES)

# Broker/gRPC chunk size -- mirrors the clients' CHUNK_SIZE; files that fit
# in one chunk have no measurable receiver-side arrival window.
CHUNK_SIZE = 1024 * 1024

NA_TEXT = "N/A (single chunk)"
NA_SINGLE_CHUNK = NA_TEXT + "¹"
DASH = "—"  # em dash for empty/not-applicable cells
WARN = "⚠"  # degraded-capture marker
FLAG = "†"  # dagger: n < MIN_N or success < 100 %
MIN_N = 5

CACHE_FILENAME = ".pcap_reanalysis_cache.json"

# Set in main(): True when cells aggregate several runs (--sweep-id).
AGGREGATE = False


def size_label(size):
    if size in KNOWN_SIZE_LABELS:
        return KNOWN_SIZE_LABELS[size]
    if size % 1048576 == 0:
        return f"{size // 1048576} MB"
    return f"{size / 1024:g} KB"


def schema_of(variant):
    """CSV schema / analyzer protocol for a column variant (mqtt+tls -> mqtt)."""
    base = variant.split("+")[0]
    return "mqtt" if base == "mqtt-windowed" else base


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
        base = manifest.get("protocol", "")
        profile = manifest.get("network_profile", "")
        if base not in BASE_PROTOCOLS or profile not in PROFILES:
            continue
        tls = bool(manifest.get("tls"))
        runs.append(
            {
                "id": name,
                "dir": os.path.join(runs_dir, name),
                "protocol": f"{base}+tls" if tls else base,
                "base": base,
                "tls": tls,
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
    """Client CSV rows of a run (mqtt-windowed writes the mqtt schema)."""
    return read_csv_rows(os.path.join(run["dir"], f"{schema_of(run['base'])}_measurements.csv"))


def row_size(row):
    try:
        return round(float(row["file_size"]) * 1024 * 1024)
    except (KeyError, ValueError, TypeError):
        return None


def sizes_covered(rows):
    return {s for s in (row_size(r) for r in rows) if s is not None}


def run_sizes(run):
    sizes = run["manifest"].get("file_sizes")
    return list(sizes) if sizes else list(DEFAULT_SIZES)


def is_complete(run):
    """A run is complete when every payload it attempted has a client row."""
    return sizes_covered(client_rows(run)) >= set(run_sizes(run))


def pick_canonical(runs, protocol, profile):
    """Newest complete run for the combination (falls back to newest partial)."""
    candidates = sorted(
        (r for r in runs if r["protocol"] == protocol and r["profile"] == profile),
        key=lambda r: r["id"],
        reverse=True,
    )
    for run in candidates:
        if is_complete(run):
            return run, True
    return (candidates[0], False) if candidates else (None, False)


def key_rows(rows):
    """Client CSV rows grouped by (size_bytes, qos, side) -> [rows]."""
    out = {}
    for row in rows:
        size = row_size(row)
        if size is None:
            continue
        out.setdefault((size, row.get("qos", ""), row.get("side", "")), []).append(row)
    return out


# Which client row carries the integrity verdict of a transfer.
INTEGRITY_SIDE = {"mqtt": "receiver", "amqp": "receiver", "grpc": "sender", "lwm2m": "client"}


def attempts_of(run):
    """{(size, qos): 1} for every transfer the run attempted (from run.json)."""
    qos_levels = [""]
    if schema_of(run["base"]) == "mqtt":
        qos_levels = [str(q) for q in run["manifest"].get("qos_levels", [1, 2])]
    return {(size, qos): 1 for size in run_sizes(run) for qos in qos_levels}


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
# Dataset
# ---------------------------------------------------------------------------

def reanalyze_pcap(run, row, cache):
    """Analyze one pcap (cache-aware).

    Returns (status, result): status in {"ok", "no-capture", "failed"};
    result is the analyze_pcap dict when status == "ok".
    """
    label = row.get("label")
    try:
        size = int(row["file_size_bytes"])
    except (KeyError, ValueError):
        return "failed", None

    # pcaps are named after the runner protocol key (e.g. http-get_<label>).
    pcap_path = os.path.join(run["dir"], "pcap", f"{run['base']}_{label}.pcap")
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
    # The analyzer picks its TLS (port-based) config from the TLS env var.
    previous_tls = os.environ.get("TLS")
    os.environ["TLS"] = "1" if run["tls"] else "0"
    try:
        result = analyze_pcap(
            pcap_path,
            size,
            protocol=schema_of(run["base"]),
            filename=row.get("filename"),
            qos_level=qos_level,
            label=label,
        )
    except Exception as exc:  # one bad pcap must not kill the whole export
        print(f"    WARNING: pcap analysis failed for {os.path.basename(pcap_path)}: {exc}")
        return "failed", None
    finally:
        if previous_tls is None:
            os.environ.pop("TLS", None)
        else:
            os.environ["TLS"] = previous_tls

    cache[key] = result
    return "ok", result


def select_runs(runs, protocol, profile, sweep_ids):
    """(runs, complete) for one cell, by sweep or newest-complete."""
    if sweep_ids:
        chosen = [r for r in runs
                  if r["protocol"] == protocol and r["profile"] == profile
                  and r["manifest"].get("sweep_id") in sweep_ids]
        return chosen, all(is_complete(r) for r in chosen)
    run, complete = pick_canonical(runs, protocol, profile)
    return ([run] if run else []), complete


def collect_dataset(runs, protocols, profiles, cache, sweep_ids=None):
    """dataset[(protocol, profile)] -> entry (or None when never run)."""
    dataset = {}
    for protocol in protocols:
        for profile in profiles:
            chosen, complete = select_runs(runs, protocol, profile, sweep_ids)
            if not chosen:
                dataset[(protocol, profile)] = None
                continue
            ids = ", ".join(r["id"] for r in chosen)
            print(f"  {protocol}/{profile}: {len(chosen)} run(s) {ids} (complete={complete})")
            entry = {
                "run_ids": [r["id"] for r in chosen],
                "sweep_ids": sorted({str(r["manifest"].get("sweep_id")) for r in chosen
                                     if r["manifest"].get("sweep_id")}),
                "complete": complete,
                "client": [],
                "pcap_keys": [],
                "pcap_results": {},
                "pcap_status": {},
                "attempts": {},
                "sizes": set(),
            }
            for run in chosen:
                entry["client"].extend(client_rows(run))
                entry["sizes"].update(run_sizes(run))
                for key, n in attempts_of(run).items():
                    entry["attempts"][key] = entry["attempts"].get(key, 0) + n
                for row in read_csv_rows(os.path.join(run["dir"], "pcap_measurements.csv")):
                    try:
                        size = int(row["file_size_bytes"])
                    except (KeyError, ValueError):
                        continue
                    qos = row.get("qos", "").strip()
                    status, result = reanalyze_pcap(run, row, cache)
                    if (size, qos) not in entry["pcap_status"]:
                        entry["pcap_keys"].append((size, qos))
                    entry["pcap_status"].setdefault((size, qos), []).append(status)
                    entry["pcap_results"].setdefault((size, qos), []).append(result)
            entry["client_keyed"] = key_rows(entry["client"])
            dataset[(protocol, profile)] = entry
    return dataset


def successes(entry, protocol, size, qos):
    """Number of verified transfers for one (size, qos) of a cell."""
    schema = schema_of(protocol)
    side = INTEGRITY_SIDE.get(schema, "")
    qos_key = qos if schema == "mqtt" else ""
    rows = entry["client_keyed"].get((size, qos_key, side), [])
    return sum(1 for r in rows if str(r.get("integrity_ok", "")).strip() == "True")


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


def fmt_num(x):
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:.4g}"


def agg_text(raw_values):
    """One cell from several raw CSV values.

    One value: shown exactly as recorded (legacy single-run output stays
    byte-identical). Several numeric values: median [Q1-Q3].
    """
    raw = [v for v in raw_values if fmt(v) != DASH]
    if not raw:
        return DASH
    if len(raw) == 1:
        return fmt(raw[0])
    numbers = [n for n in (to_number(v) for v in raw) if n is not None]
    if not numbers:
        return fmt(raw[0])
    q1, median, q3 = quartiles(numbers)
    return f"{fmt_num(median)} [{fmt_num(q1)}–{fmt_num(q3)}]"


PASS_THROUGH_FIELDS = {"protocol", "qos", "side", "direction", "tls", "run_id",
                       "timestamp", "network_profile"}


def agg_row(rows):
    """Aggregate a list of client rows into one dict of display strings."""
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    out = {}
    for field in rows[0]:
        values = [r.get(field) for r in rows]
        if field in PASS_THROUGH_FIELDS:
            out[field] = rows[0].get(field)
        elif field == "integrity_ok":
            ok = sum(1 for v in values if str(v).strip() == "True")
            known = sum(1 for v in values if fmt(v) != DASH)
            out[field] = f"{ok}/{known}" if known else DASH
        else:
            out[field] = agg_text(values)
    return out


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

# "Latency" columns are named after what each protocol actually times; they
# are not comparable across protocols.
CLIENT_HEADERS = {
    "mqtt": ["Size", "QoS", "Side", "Duration s", "PUBACK RTT s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Samples", "Integrity"],
    "http": ["Size", "Transfer s", "TCP connect s", "TTFB s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Samples", "Integrity"],
    "http-get": ["Size", "Transfer s", "TCP connect s", "TLS handshake s", "TTFB s",
                 "Goodput Mbps", "Resumed", "Avg CPU", "Peak RAM", "Samples", "Integrity"],
    "coap": ["Size", "Transfer s", "Discovery GET s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Samples", "Integrity"],
    "amqp": ["Size", "Side", "Duration s", "Confirm RTT s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Samples", "Integrity"],
    "grpc": ["Size", "Side", "Duration s", "Ping RPC s", "Goodput Mbps",
             "Avg CPU", "Peak RAM", "Samples", "Integrity"],
    "lwm2m": ["Size", "Download s", "Registration s", "Goodput Mbps",
              "Avg CPU", "Peak RAM", "Samples", "Integrity"],
}


def duration_cell(schema, row, side, size):
    """Duration/goodput cells, with the single-chunk receiver guard."""
    if schema in ("mqtt", "amqp", "grpc") and side == "receiver" and is_single_chunk(size):
        return NA_SINGLE_CHUNK, NA_SINGLE_CHUNK
    if schema in ("mqtt", "amqp", "grpc"):
        field = "sender_duration" if side == "sender" else "receiver_duration"
        return fmt(row.get(field)), fmt(row.get("goodput_mbps"))
    if schema in ("http", "http-get", "coap"):
        return fmt(row.get("time_to_transfer")), fmt(row.get("goodput_mbps"))
    if schema == "lwm2m":
        return fmt(row.get("download_duration")), fmt(row.get("goodput_mbps"))
    return DASH, DASH


def resource_cells(row):
    return (
        fmt(row.get("avg_cpu_usage")),
        fmt(row.get("peak_ram_usage")),
        fmt(row.get("sample_count")),
        fmt(row.get("integrity_ok")),
    )


def render_client_table(protocol, rows):
    schema = schema_of(protocol)
    header = CLIENT_HEADERS[schema]
    keyed = key_rows(rows)
    body = []

    for size in SIZE_ORDER:
        label = size_label(size)
        if schema == "mqtt":
            emitted = False
            for qos in ("1", "2"):
                for side in ("sender", "receiver"):
                    row = agg_row(keyed.get((size, qos, side)))
                    if row is None:
                        continue
                    duration, goodput = duration_cell(schema, row, side, size)
                    cpu, ram, samples, integrity = resource_cells(row)
                    body.append([label, f"qos {qos}", side, duration,
                                 fmt(row.get("latency")), goodput,
                                 cpu, ram, samples, integrity])
                    emitted = True
            if not emitted:
                body.append(not_run_row(label, len(header)))
        elif schema in ("amqp", "grpc"):
            emitted = False
            for side in ("sender", "receiver"):
                row = agg_row(keyed.get((size, "", side)))
                if row is None:
                    continue
                duration, goodput = duration_cell(schema, row, side, size)
                cpu, ram, samples, integrity = resource_cells(row)
                body.append([label, side, duration, fmt(row.get("latency")),
                             goodput, cpu, ram, samples, integrity])
                emitted = True
            if not emitted:
                body.append(not_run_row(label, len(header)))
        else:
            # LwM2M rows carry side="client"; HTTP/CoAP have no side column.
            side_key = "client" if schema == "lwm2m" else ""
            row = agg_row(keyed.get((size, "", side_key)))
            if row is None:
                body.append(not_run_row(label, len(header)))
                continue
            duration, goodput = duration_cell(schema, row, "", size)
            cpu, ram, samples, integrity = resource_cells(row)
            if schema == "http":
                body.append([label, duration, fmt(row.get("latency_tcp_rtt")),
                             fmt(row.get("latency_ttfb")), goodput,
                             cpu, ram, samples, integrity])
            elif schema == "http-get":
                body.append([label, duration, fmt(row.get("latency_tcp_rtt")),
                             fmt(row.get("tls_handshake_s")), fmt(row.get("latency_ttfb")),
                             goodput, fmt(row.get("resumed")),
                             cpu, ram, samples, integrity])
            else:
                body.append([label, duration, fmt(row.get("latency")), goodput,
                             cpu, ram, samples, integrity])

    return md_table(header, body)


PCAP_HEADER = ["Size", "QoS", "Duration s²", "Packets", "Wire bytes",
               "Overhead %", "Retrans", "Pcap goodput Mbps", "Wire Mbps"]


def _pcap_single(label, qos_cell, size, result):
    """One captured transfer, formatted exactly like the legacy export."""
    dropped = result["total_wire_bytes"] < size
    duration_text = f"{result['duration_seconds']:.2f}"
    if dropped:
        duration_text += f" {WARN}"
    return [
        label,
        qos_cell,
        duration_text,
        f"{result['total_packets']:,}",
        f"{result['total_wire_bytes']:,}",
        f"{result['overhead_percentage']:.2f}",
        str(result["retransmissions"]),
        f"{result['goodput_mbps']:.3f}",
        f"{result['wire_throughput_mbps']:.3f}",
    ]


def _pcap_aggregate(label, qos_cell, size, results):
    """Several captured transfers: median [Q1-Q3] per column.

    Degraded captures (wire bytes below the file size) are left out of the
    aggregate and counted in a marker.
    """
    usable = [r for r in results if r["total_wire_bytes"] >= size]
    dropped = len(results) - len(usable)
    pool = usable or results

    def agg(key):
        q1, median, q3 = quartiles([float(r[key]) for r in pool])
        return f"{fmt_num(median)} [{fmt_num(q1)}–{fmt_num(q3)}]"

    duration_text = agg("duration_seconds") + f" n={len(pool)}"
    if dropped:
        duration_text += f" {WARN}{dropped}"
    return [label, qos_cell, duration_text, agg("total_packets"), agg("total_wire_bytes"),
            agg("overhead_percentage"), agg("retransmissions"), agg("goodput_mbps"),
            agg("wire_throughput_mbps")]


def render_pcap_table(entry):
    body = []
    seen_sizes = set()

    for size, qos_key in entry["pcap_keys"]:
        seen_sizes.add(size)
        label = size_label(size)
        qos_cell = f"qos {qos_key}" if qos_key else ""
        statuses = entry["pcap_status"][(size, qos_key)]
        results = [r for s, r in zip(statuses, entry["pcap_results"][(size, qos_key)])
                   if s == "ok" and r is not None]

        if not results:
            reason = "no capture" if "no-capture" in statuses else "analysis failed"
            body.append([label, qos_cell, reason] + [""] * (len(PCAP_HEADER) - 3))
            continue
        if len(statuses) == 1:
            body.append(_pcap_single(label, qos_cell, size, results[0]))
        else:
            body.append(_pcap_aggregate(label, qos_cell, size, results))

    for size in SIZE_ORDER:
        if size not in seen_sizes:
            body.append(not_run_row(size_label(size), len(PCAP_HEADER)))

    return md_table(PCAP_HEADER, body)


def run_note(entry):
    if len(entry["run_ids"]) == 1:
        return f"_Run: `{entry['run_ids'][0]}`_"
    sweeps = ", ".join(f"`{s}`" for s in entry["sweep_ids"]) or "—"
    return f"_{len(entry['run_ids'])} runs (sweep {sweeps}): " + \
        ", ".join(f"`{r}`" for r in entry["run_ids"]) + "_"


def render_protocol(dataset, protocol, profiles):
    lines = [f"## {protocol.upper()}", ""]

    for profile in profiles:
        entry = dataset.get((protocol, profile))
        lines.append(f"### {protocol.upper()} — {profile}")
        lines.append("")

        if entry is None:
            lines.append("**Not run.**")
            lines.append("")
            continue

        note = run_note(entry)
        if not entry["complete"]:
            note += (
                " — *partial run: some sizes were attempted but never"
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


def build_footnotes(commit):
    if AGGREGATE:
        return build_footnotes_v2(commit)
    return f"""**How to read this document**

- All pcap time metrics (`Duration s²`, `Pcap goodput`, `Wire Mbps`) are
  **re-analyzed from the stored pcaps** with the current analyzer (commit
  {commit}): duration spans the first to the last frame of the
  protocol's own traffic window, so idle startup and ARP/ICMPv6 noise no
  longer inflate it (ISSUES.md FIXED-9). Byte-derived columns (packets, wire
  bytes, overhead, retransmissions) are identical to the run CSVs.
- ¹ **{NA_TEXT}**: a file that fits in one 1 MB chunk spans no
  measurable receiver-side arrival window; pre-fix runs recorded misleading
  ~0.00 s / 1500+ Mbps cells there, which are shown as N/A (ISSUES.md
  FIXED-13).
- ² see the first bullet.
- Under high-latency profiles (`satellite`, `harsh`) the pcap window also
  includes protocol control traffic around the data transfer itself --
  connection/channel setup, keepalive/BDP pings, and broker-receiver QoS
  retransmissions -- so `Duration s²` can exceed the client-side transfer
  window. The client-side columns are the transfer-only view.
- ⚠ marks captures that dropped frames (captured wire bytes below the
  verified file size): the overhead/throughput columns of that row are
  unreliable (see docs/troubleshooting.md -- re-running the transfer is the
  remedy, which was not done for the historical coap harsh 20/50 MB rows).
- **MQTT/AMQP sender duration**: runs recorded before commit d2426af include
  the metadata-ACK round trip inside `Duration s`; runs after it (all runs
  dated 2026-11-20) time chunk transmission only (ISSUES.md FIXED-12).
- **Samples** is the CPU/RAM sample count behind the averages
  (ISSUES.md FIXED-10). Pre-fix runs did not record it (—) and their
  CPU can read 0 on very fast transfers. The energy estimate these runs
  recorded is no longer reported (it described the host, not a device).
- The **latency columns** are named after what each protocol times (PUBACK,
  TCP connect, discovery GET, publish confirm, Ping RPC, registration); they
  are not comparable across protocols.
- Sender-side **Integrity** is — for MQTT/AMQP by design: the sender hands
  the file to the broker and cannot observe the receiver's checksum result.
  gRPC sender rows show the server-reported result from the Upload reply.
- **"not run"** combinations were never executed: gRPC under `mobile`,
  LwM2M under `harsh` (blockwise pull at 300 ms RTT takes hours, ISSUES.md
  OPEN-4) and CoAP/LwM2M under `satellite`.
- Per protocol × profile the newest **complete** run is used; older
  partial runs (e.g. the aborted gRPC harsh sweep) are superseded.
- **Legacy shaping** (ISSUES.md FIXED-15): in these runs the MQTT/AMQP device
  link (broker → client-b) carried the data unshaped while the
  server-side hop was shaped, so their chaos-profile numbers are not
  comparable with the direct protocols or with v2 runs.
"""


def build_footnotes_v2(commit):
    return f"""**How to read this document**

- **Statistics.** Every cell aggregates all runs of the selected sweep(s):
  `median [Q1–Q3]` over the repetitions (inclusive quartiles). A single
  value means one run. **Integrity** shows verified transfers / rows.
- All pcap time metrics (`Duration s²`, `Pcap goodput`, `Wire Mbps`) are
  re-analyzed from the stored pcaps with the analyzer at commit {commit}.
  `n=` after the pcap duration is the number of captures aggregated;
  ⚠N counts captures left out because they dropped frames.
- ¹ **{NA_TEXT}**: a file that fits in one 1 MB chunk spans no
  measurable receiver-side arrival window.
- ² see the second bullet.
- **Shaping model** (docs/network-chaos.md, ISSUES.md FIXED-15): exactly one
  constrained link, between the device and its data source, shaped in both
  directions with the same per-direction values (RTT ≈ 2 × delay). MQTT/AMQP:
  the publisher (server side) is unshaped, the broker → device direction is
  shaped by the capture sidecar, and only the device leg is captured.
- The **latency columns** are named after what each protocol times (PUBACK,
  TCP connect, discovery GET, publish confirm, Ping RPC, registration); they
  are not comparable across protocols. `TLS handshake s` is the handshake on
  top of the TCP connect (TLS runs only).
- **Samples** is the CPU/RAM sample count behind the averages. CPU and RAM
  are host-side process metrics of the containerised clients.
- Sender-side **Integrity** is — for MQTT/AMQP by design: the sender hands
  the file to the broker; the receiver row carries the checksum result.
"""


def payload_range():
    if not SIZE_ORDER:
        return DASH
    return f"{size_label(min(SIZE_ORDER))} – {size_label(max(SIZE_ORDER))}"


def render_export_doc(dataset, protocols, profiles, commit):
    lines = [
        "# Benchmark Measurements Export",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"analyzer at commit `{commit}` · payloads: {payload_range()}",
        "",
        "Companion document: `measurements_comparison.md` (side-by-side"
        " protocol comparison).",
        "",
    ]
    for protocol in protocols:
        if any(dataset.get((protocol, p)) for p in profiles) or not AGGREGATE:
            lines.extend(render_protocol(dataset, protocol, profiles))
    lines.append("---")
    lines.append("")
    lines.append(build_footnotes(commit))
    return lines


# ---------------------------------------------------------------------------
# Document 2: cross-protocol comparison (measurements_comparison.md)
# ---------------------------------------------------------------------------

# (protocol variant, qos, column label) -- MQTT split into its two QoS levels.
COMPARE_COLUMNS = [
    ("mqtt", "1", "MQTT QoS 1"),
    ("mqtt", "2", "MQTT QoS 2"),
    ("mqtt+tls", "1", "MQTT QoS 1 + TLS"),
    ("mqtt+tls", "2", "MQTT QoS 2 + TLS"),
    ("mqtt-windowed", "1", "MQTT QoS 1 windowed"),
    ("mqtt-windowed", "2", "MQTT QoS 2 windowed"),
    ("http", "", "HTTP PUT"),
    ("http+tls", "", "HTTP PUT + TLS"),
    ("http-get", "", "HTTP GET"),
    ("http-get+tls", "", "HTTP GET + TLS"),
    ("coap", "", "CoAP"),
    ("amqp", "", "AMQP"),
    ("grpc", "", "gRPC"),
    ("lwm2m", "", "LwM2M"),
]

# Which client CSV row holds each schema's transfer/sender view.
CLIENT_ROW_KEY = {
    "mqtt": lambda size, qos: (size, qos, "sender"),
    "http": lambda size, qos: (size, "", ""),
    "http-get": lambda size, qos: (size, "", ""),
    "coap": lambda size, qos: (size, "", ""),
    "amqp": lambda size, qos: (size, "", "sender"),
    "grpc": lambda size, qos: (size, "", "sender"),
    "lwm2m": lambda size, qos: (size, "", "client"),
}

# Transfer-time / round-trip column names differ per schema.
TRANSFER_FIELD = {
    "mqtt": "sender_duration",
    "http": "time_to_transfer",
    "http-get": "time_to_transfer",
    "coap": "time_to_transfer",
    "amqp": "sender_duration",
    "grpc": "sender_duration",
    "lwm2m": "download_duration",
}
LATENCY_FIELD = {
    "mqtt": "latency",
    "http": "latency_tcp_rtt",
    "http-get": "latency_tcp_rtt",
    "coap": "latency",
    "amqp": "latency",
    "grpc": "latency",
    "lwm2m": "latency",
}


def uniform(field):
    return {schema: field for schema in CLIENT_ROW_KEY}


def make_client_field(field_by_schema, side_override=None):
    """Client-metric extractor: list of raw CSV values (one per run)."""
    side_override = side_override or {}

    def field_fn(dataset, protocol, profile, qos, size):
        entry = dataset.get((protocol, profile))
        schema = schema_of(protocol)
        if entry is None or schema not in field_by_schema:
            return []
        key = CLIENT_ROW_KEY[schema](size, qos)
        if schema in side_override:
            key = (key[0], key[1], side_override[schema])
        rows = entry["client_keyed"].get(key, [])
        values = [r.get(field_by_schema[schema]) for r in rows]
        return [v for v in values if fmt(v) != DASH]
    return field_fn


def make_pcap_field(result_key):
    """pcap-metric extractor: list of numbers, degraded captures excluded."""
    def field_fn(dataset, protocol, profile, qos, size):
        entry = dataset.get((protocol, profile))
        if entry is None:
            return []
        results = entry["pcap_results"].get((size, qos), [])
        return [r[result_key] for r in results
                if r is not None and r["total_wire_bytes"] >= size]
    return field_fn


def success_info(dataset, protocol, profile, qos, size):
    entry = dataset.get((protocol, profile))
    if entry is None:
        return 0, 0
    qos_key = qos if schema_of(protocol) == "mqtt" else ""
    return successes(entry, protocol, size, qos), entry["attempts"].get((size, qos_key), 0)


def cell_raw(values):
    return fmt(values[0]) if values else DASH


def cell_pct(values):
    return f"{values[0]:.2f}" if values else DASH


def cell_int(values):
    return str(values[0]) if values else DASH


def aggregate_cell(values, ok, attempts):
    """median [Q1-Q3] n=N S% (dagger when n < MIN_N or success < 100 %)."""
    numbers = [n for n in (to_number(v) if not isinstance(v, (int, float)) else float(v)
                           for v in values) if n is not None]
    if not numbers:
        if attempts:
            return f"failed (0/{attempts})"
        return DASH
    q1, median, q3 = quartiles(numbers)
    text = f"{fmt_num(median)} [{fmt_num(q1)}–{fmt_num(q3)}] n={len(numbers)}"
    if attempts:
        text += f" {100 * ok / attempts:.0f}%"
    if len(numbers) < MIN_N or (attempts and ok < attempts):
        text += FLAG
    return text


def render_cell(dataset, protocol, profile, qos, size, field_fn, legacy_fmt):
    values = field_fn(dataset, protocol, profile, qos, size)
    if not AGGREGATE:
        return legacy_fmt(values)
    ok, attempts = success_info(dataset, protocol, profile, qos, size)
    return aggregate_cell(values, ok, attempts)


def active_columns(dataset, profiles):
    """Columns with any data in the dataset (empty variants are dropped)."""
    cols = []
    for protocol, qos, label in COMPARE_COLUMNS:
        for profile in profiles:
            entry = dataset.get((protocol, profile))
            if entry is None:
                continue
            schema = schema_of(protocol)
            qos_key = qos if schema == "mqtt" else ""
            has_rows = any(k[1] == qos_key for k in entry["client_keyed"])
            has_pcap = any(k[1] == qos for k in entry["pcap_results"])
            if has_rows or has_pcap:
                cols.append((protocol, qos, label))
                break
    return cols


def render_compare_metric_table(dataset, profile, title, field_fn, legacy_fmt, columns):
    """One metric, one profile: rows = file sizes, columns = protocols."""
    header = ["Size"] + [label for _, _, label in columns]
    body = []
    for size in SIZE_ORDER:
        cells = [size_label(size)]
        for protocol, qos, _ in columns:
            cells.append(render_cell(dataset, protocol, profile, qos, size, field_fn, legacy_fmt))
        body.append(cells)
    return [f"### {title}", "", *md_table(header, body), ""]


def render_headline_matrix(dataset, profiles, title, field_fn, legacy_fmt, size, columns):
    """One metric, one file size: rows = profiles, columns = protocols."""
    header = ["Profile"] + [label for _, _, label in columns]
    body = []
    for profile in profiles:
        cells = [profile]
        for protocol, qos, _ in columns:
            cells.append(render_cell(dataset, protocol, profile, qos, size, field_fn, legacy_fmt))
        body.append(cells)
    return [f"## {title}", "", *md_table(header, body), ""]


def render_comparison_profile(dataset, profile, columns):
    lines = [f"## Profile: {profile}", ""]
    metric_tables = [
        ("Transfer time (s)", make_client_field(TRANSFER_FIELD), cell_raw),
        ("Client goodput (Mbps)", make_client_field(uniform("goodput_mbps")), cell_raw),
        ("Control round trip (s) ³ — protocol-specific, not comparable across protocols",
         make_client_field(LATENCY_FIELD), cell_raw),
    ]
    if any("+tls" in protocol for protocol, _, _ in columns):
        # Device-side handshake: for MQTT that is the receiver (client-b) row.
        metric_tables.append((
            "TLS handshake (s) ⁴",
            make_client_field({"mqtt": "tls_handshake_s", "http-get": "tls_handshake_s"},
                              side_override={"mqtt": "receiver"}),
            cell_raw,
        ))
    metric_tables += [
        ("Avg CPU (%)", make_client_field(uniform("avg_cpu_usage")), cell_raw),
        ("Peak RAM (MB)", make_client_field(uniform("peak_ram_usage")), cell_raw),
        ("Wire overhead % (pcap)", make_pcap_field("overhead_percentage"), cell_pct),
        ("Retransmissions (pcap)", make_pcap_field("retransmissions"), cell_int),
    ]
    for title, field_fn, legacy_fmt in metric_tables:
        lines += render_compare_metric_table(dataset, profile, title, field_fn, legacy_fmt, columns)
    return lines


def build_comparison_footnotes():
    if AGGREGATE:
        return f"""**How to read the comparison document**

- Each cell: `median [Q1–Q3] n=N S%` over the runs of the selected
  sweep(s). `n` counts the values behind the median; `S%` is verified
  transfers / attempts recorded in run.json, so a transfer that crashed
  without writing a row still counts as a failure. {FLAG} marks cells with
  n < {MIN_N} or a success rate below 100 %. `failed (0/N)` means every
  attempt failed.
- Cells use the **sender-side** client measurements for MQTT/AMQP/gRPC,
  the single client measurement for HTTP/CoAP, and the device-side download
  view for HTTP GET and LwM2M. Success rates use the row that carries the
  integrity verdict (MQTT/AMQP receiver, gRPC sender, others the client).
- ³ **Round-trip definitions differ per protocol**: MQTT = metadata PUBACK;
  AMQP = publish confirm; HTTP = bare TCP connect; CoAP = discovery GET;
  gRPC = Ping RPC; LwM2M = registration. Not comparable across protocols;
  compare transfer time, goodput, overhead and success rate instead.
- ⁴ **TLS handshake**: on top of the TCP connect, on a bare socket. For
  MQTT it is the device's (client-b) handshake over the constrained link,
  measured once per connection; for HTTP GET it is measured per transfer.
- **Shaping model**: one constrained link between the device and its data
  source, shaped in both directions (RTT ≈ 2 × netem delay); see
  docs/network-chaos.md. Wire overhead for MQTT/AMQP covers the device leg
  only.
- CPU and RAM are host-side process metrics of the containerised clients,
  not device measurements; device energy is measured in the field test.
- Library limitations behind some results (aiocoap stop-and-wait with 1 KB
  blocks, paho waiting per 1 MB chunk, synchronous AMQP confirms, LwM2M
  emulator without DTLS) are listed in docs/measurement-pipeline.md §5.
"""
    return """**How to read the comparison document**

- Same dataset and run selection as `measurements_export.md` (newest
  complete run per protocol × profile; pcaps re-analyzed with the current
  analyzer). Receiver-side views, per-row sample counts and integrity
  values live in that detail document.
- Cells use the **sender-side** client measurements for MQTT/AMQP/gRPC,
  the single client measurement for HTTP/CoAP, and the device-side download
  view for LwM2M.
- ³ **Round-trip definitions differ per protocol**: MQTT/AMQP = metadata
  publish-ack round trip; HTTP = bare TCP connect; CoAP = discovery GET;
  gRPC = Ping RPC; LwM2M = registration. Not comparable across protocols.
- **Timing provenance**: runs dated 2026-11-20 (gRPC harsh, the satellite
  sweeps, the HTTP good verification run) use post-fix timing, where
  MQTT/AMQP transfer time excludes the metadata round trip; all older runs
  include it (bounded by one broker RTT, ISSUES.md FIXED-12). Pre-fix
  CPU can read 0 on fast transfers — sample counts are in the detail
  document. The energy estimate is no longer reported.
- — = **not run or attempted-but-uncompleted**: gRPC mobile; gRPC iot
  50 MB; coap harsh 20/50 MB; LwM2M harsh; CoAP/LwM2M satellite. The
  coap harsh 20/50 MB pcap rows exist but were frame-dropped and are
  excluded from the pcap-side cells (see the ⚠ rows in the detail
  document).
- Wire overhead % and retransmissions are byte/packet-derived and
  unaffected by the timing fixes.
- Every recorded transfer in the included runs passed integrity
  verification.
- **Legacy shaping** (ISSUES.md FIXED-15): in these runs the MQTT/AMQP
  device link carried the data unshaped while the server-side hop was
  shaped; MQTT/AMQP overhead counts both broker legs (~115 %).
"""


def render_comparison_doc(dataset, protocols, profiles, commit):
    columns = [c for c in active_columns(dataset, profiles) if c[0] in protocols]
    lines = [
        "# Protocol Comparison — Benchmark Measurements",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"analyzer at commit `{commit}` · payloads: {payload_range()}",
        "",
        "Companion to `measurements_export.md` — same runs, same re-analyzed"
        " pcaps; per-protocol detail, receiver-side views and per-row samples"
        " live there.",
        "",
    ]

    goodput_field = make_client_field(uniform("goodput_mbps"))
    overhead_field = make_pcap_field("overhead_percentage")

    largest = max(SIZE_ORDER) if SIZE_ORDER else None
    smallest = min(SIZE_ORDER) if SIZE_ORDER else None
    if largest is not None:
        lines += render_headline_matrix(
            dataset, profiles, f"Headline: client goodput (Mbps) at {size_label(largest)}",
            goodput_field, cell_raw, largest, columns)
    if smallest is not None and smallest != largest:
        lines += render_headline_matrix(
            dataset, profiles, f"Headline: client goodput (Mbps) at {size_label(smallest)}",
            goodput_field, cell_raw, smallest, columns)
    if largest is not None:
        lines += render_headline_matrix(
            dataset, profiles, f"Headline: wire overhead % at {size_label(largest)} (pcap)",
            overhead_field, cell_pct, largest, columns)

    for profile in profiles:
        lines += render_comparison_profile(dataset, profile, columns)

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
    global AGGREGATE, SIZE_ORDER

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs-dir", default=os.path.join("output", "runs"))
    parser.add_argument("-o", "--output",
                        default=os.path.join("output", "measurements_export.md"))
    parser.add_argument("--comparison-output",
                        default=os.path.join("output", "measurements_comparison.md"))
    parser.add_argument("--protocols", nargs="+", choices=PROTOCOLS, default=PROTOCOLS)
    parser.add_argument("--profiles", nargs="+", default=PROFILES)
    parser.add_argument("--sweep-id", nargs="+", default=None,
                        help="Aggregate every run of these sweep ids (median [IQR], "
                             "n, success %%) instead of picking one run per cell.")
    args = parser.parse_args()

    AGGREGATE = bool(args.sweep_id)
    commit = git_commit()
    runs = load_runs(args.runs_dir)
    print(f"Found {len(runs)} runs in {args.runs_dir}")

    cache_file = os.path.join(
        os.path.dirname(os.path.abspath(args.runs_dir)), CACHE_FILENAME)
    cache = load_cache(cache_file)
    dataset = collect_dataset(runs, args.protocols, args.profiles, cache,
                              sweep_ids=set(args.sweep_id) if args.sweep_id else None)
    save_cache(cache_file, cache)

    sizes = set()
    for entry in dataset.values():
        if entry:
            sizes.update(entry["sizes"])
    SIZE_ORDER = sorted(sizes) if sizes else list(DEFAULT_SIZES)

    # Profiles without any selected run are left out of a sweep report.
    profiles = args.profiles
    if AGGREGATE:
        profiles = [p for p in args.profiles
                    if any(dataset.get((proto, p)) for proto in args.protocols)]

    write_doc(args.output,
              render_export_doc(dataset, args.protocols, profiles, commit))
    write_doc(args.comparison_output,
              render_comparison_doc(dataset, args.protocols, profiles, commit))


if __name__ == "__main__":
    main()
