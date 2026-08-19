"""
    Optional chart generator for the benchmark results.

    Reads the CSV files produced by the benchmark runs (client-side runtime
    metrics + pcap-derived analysis) and renders comparison charts as PNGs.

    Chart style:
      - Line charts (protocol / MQTT-QoS as series, file size on the x axis,
        mean point + min-max band) for metrics that scale with file size.
      - Grouped bar charts for size-invariant metrics (CPU / RAM / energy) and
        for the combined overview dashboard.
      - --chart-type line|bar overrides the per-metric auto choice.

    Selection:
      --run <id> selects one run directory (output/runs/<id>/) and charts its
      data. Alternatively --csv-dir/--suffix select the legacy flat layout.
      --protocols / --qos / --mqtt-side / --file-sizes / --metrics narrow down
      which metrics are charted.

    Requires matplotlib (optional dependency):
        pip install -r requirements-charts.txt

    Usage (run from the project root):
        python common/charts.py
        python common/charts.py --run 20260818T201455_mqtt_harsh
        python common/charts.py --runs-dir output --run 20260818T201455_mqtt_harsh
        python common/charts.py --protocols http mqtt
        python common/charts.py --metrics goodput_mbps overhead_percentage
        python common/charts.py --file-sizes 1 5 20 50
        python common/charts.py --chart-type bar --x-scale linear
        python common/charts.py --qos 2 --mqtt-side both
        python common/charts.py --error none --agg median
"""

import argparse
import csv
import os
import re
import statistics
import sys
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use("Agg")  # headless: save figures, never open a window
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit(
        "matplotlib is not installed.\n"
        "Run: pip install -r requirements-charts.txt"
    )

# Project root is not on sys.path when running `python common/charts.py`.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import common.runs as runs


PROTOCOLS = ["http", "mqtt", "coap"]
PROTO_ORDER = {p: i for i, p in enumerate(PROTOCOLS)}
COLORS = {"http": "#1f77b4", "mqtt": "#ff7f0e", "coap": "#2ca02c"}
# MQTT QoS is rendered as a line style (or bar hatch) on the protocol color.
QOS_STYLES = {None: "-", "1": "--", "2": ":"}
QOS_HATCH = {None: None, "1": "//", "2": "xx"}

# Client-side metrics. `fields` maps protocol -> CSV column holding the value
# for this metric (MQTT has no cpu/ram/energy columns). `size_dependent`
# drives the auto chart type: size-dependent metrics -> line charts.
CLIENT_METRICS = {
    "goodput_mbps": {
        "title": "Goodput (client-measured)",
        "ylabel": "Mbps",
        "size_dependent": True,
        "fields": {"http": "goodput_mbps", "coap": "goodput_mbps",
                   "mqtt": "goodput_mbps"},
    },
    "transfer_time": {
        "title": "Transfer time",
        "ylabel": "seconds",
        "size_dependent": True,
        "fields": {"http": "time_to_transfer", "coap": "time_to_transfer",
                   "mqtt": "sender_duration"},
    },
    "latency": {
        "title": "Latency",
        "ylabel": "seconds",
        "size_dependent": True,
        "fields": {"http": "latency_tcp_rtt", "coap": "latency",
                   "mqtt": "latency"},
    },
    "avg_cpu_pct": {
        "title": "Avg CPU usage",
        "ylabel": "%",
        "size_dependent": False,
        "fields": {"http": "avg_cpu_usage", "coap": "avg_cpu_usage"},
    },
    "peak_ram_mb": {
        "title": "Peak RAM",
        "ylabel": "MB",
        "size_dependent": False,
        "fields": {"http": "peak_ram_usage", "coap": "peak_ram_usage"},
    },
    "energy_j": {
        "title": "Energy estimate",
        "ylabel": "J",
        "size_dependent": False,
        "fields": {"http": "energy_est", "coap": "energy_est"},
    },
}

# pcap-derived metrics (single CSV, one row per transfer).
PCAP_METRICS = {
    "goodput_mbps":         {"title": "Goodput (pcap)",         "ylabel": "Mbps",    "size_dependent": True},
    "wire_throughput_mbps": {"title": "Wire throughput (pcap)", "ylabel": "Mbps",    "size_dependent": True},
    "overhead_percentage":  {"title": "Overhead (pcap)",        "ylabel": "%",       "size_dependent": True},
    "total_overhead_bytes": {"title": "Total overhead bytes (pcap)", "ylabel": "bytes", "size_dependent": True},
    "total_wire_bytes":     {"title": "Total wire bytes (pcap)", "ylabel": "bytes",  "size_dependent": True},
    "retransmissions":      {"title": "Retransmissions",         "ylabel": "count",  "size_dependent": True},
    "total_packets":        {"title": "Total packets",           "ylabel": "packets", "size_dependent": True},
}

DEFAULT_CSV_DIR = os.getenv("OUTPUT_DIR", "./output")
DEFAULT_OUT_DIR = "output/charts"

OVERVIEW_METRICS = ["goodput_mbps", "transfer_time", "latency", "avg_cpu_pct",
                    "wire_throughput_mbps", "overhead_percentage",
                    "retransmissions", "total_wire_bytes"]


def _to_number(value):
    """Parse a leading number from cells like '2.71%', '28.15 MB' or 'X'."""
    if value is None:
        return None
    match = re.match(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", str(value).strip())
    return float(match.group(0)) if match else None


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _resolve_file(csv_dir, base, suffix_candidates):
    for suffix in suffix_candidates:
        path = os.path.join(csv_dir, f"{base}_measurements{suffix}.csv")
        if os.path.isfile(path):
            return path
    return None


def _run_file(csv_dir, base):
    """Exact filename inside a run directory (no suffix guessing)."""
    path = os.path.join(csv_dir, f"{base}_measurements.csv")
    return path if os.path.isfile(path) else None


def _client_label(row, protocol):
    size = _to_number(row.get("file_size"))
    label = f"{size:.3g} MB" if size is not None else "?"
    if protocol == "mqtt":
        qos = (row.get("qos") or "").strip()
        return f"{label} | qos {qos}"
    return label


def _pcap_label(row, protocol=None):
    name = (row.get("filename") or row.get("label") or "?").strip()
    name = name.replace("binary_file_", "").replace(".bin", "")
    qos = (row.get("qos") or "").strip()
    return f"{name}" + (f" | qos {qos}" if qos else "")


def _size_mb_client(row):
    return _to_number(row.get("file_size"))


def _size_mb_pcap(row):
    size = _to_number(row.get("file_size_bytes"))
    return size / (1024 * 1024) if size else None


def _label_sort_key(label):
    nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", label)]
    return nums or [0.0]


def _series_label(key):
    proto, qos = key
    return f"{proto.upper()} qos{qos}" if qos else proto.upper()


def _series_sort_key(key):
    proto, qos = key
    return (PROTO_ORDER.get(proto, 99), qos or "")


def _aggregate(values, agg):
    values = [v for v in values if v is not None]
    if not values:
        return None
    if agg == "median":
        return statistics.median(values)
    if agg == "min":
        return min(values)
    if agg == "max":
        return max(values)
    return sum(values) / len(values)


def _error_bounds(values, error):
    """Return (low, high) band around the aggregate for the given error mode."""
    values = [v for v in values if v is not None]
    if not values or error == "none":
        return (None, None)
    if error == "std":
        mean = sum(values) / len(values)
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
        return (mean - sd, mean + sd)
    if error == "q90":
        ordered = sorted(values)
        lo = ordered[int(round(0.1 * (len(ordered) - 1)))]
        hi = ordered[int(round(0.9 * (len(ordered) - 1)))]
        return (lo, hi)
    return (min(values), max(values))


def _collect(rows_by_protocol, field_by_protocol, label_fn, args, size_mb_fn=None):
    """
    Return {(protocol, qos): {x_label: [run values, ...]}} for one metric.

    Applies the --protocols (caller), --qos, --mqtt-side and --file-sizes
    filters. The series key carries the MQTT QoS so it can be charted as a
    separate series; other protocols use qos=None.
    """
    data = {}
    for protocol, rows in rows_by_protocol.items():
        field = field_by_protocol.get(protocol)
        if not field:
            continue
        series = defaultdict(lambda: defaultdict(list))
        for row in rows:
            qos = None
            if protocol == "mqtt":
                side = (row.get("side") or "").strip()
                if side and args.mqtt_side != "both" and side != args.mqtt_side:
                    continue
                qos = (row.get("qos") or "").strip() or None
                if args.qos and qos and int(qos) not in args.qos:
                    continue
            size = size_mb_fn(row) if size_mb_fn else None
            if args.file_sizes and size is not None and not any(
                    abs(size - s) < 1e-6 for s in args.file_sizes):
                continue
            value = _to_number(row.get(field))
            if value is None:
                continue
            series[(protocol, qos)][label_fn(row, protocol)].append(value)
        if series:
            data.update(series)
    return data


def _plot_line(series, title, ylabel, outpath, args):
    """Line chart: x = numeric file size, one line per (protocol, qos) series."""
    labels = sorted({l for d in series.values() for l in d}, key=_label_sort_key)
    if not labels:
        print(f"  (skip) {title}: no data")
        return False

    xscale = "log" if args.x_scale == "auto" else args.x_scale
    if xscale == "log" and any(_label_sort_key(l)[0] <= 0 for l in labels):
        xscale = "linear"

    fig, ax = plt.subplots(figsize=args.figsize or (max(8.0, 1.5 * len(labels)), 5.0))
    for key in sorted(series, key=_series_sort_key):
        points = []
        for label in labels:
            x = _label_sort_key(label)[0]
            y = _aggregate(series[key].get(label, []), args.agg)
            if y is None:
                continue
            lo, hi = _error_bounds(series[key].get(label, []), args.error)
            points.append((x, y, lo, hi))
        if not points:
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        if args.error != "none":
            los = [p[2] if p[2] is not None else p[1] for p in points]
            his = [p[3] if p[3] is not None else p[1] for p in points]
            ax.fill_between(xs, los, his, color=COLORS[key[0]], alpha=0.15)
        ax.plot(xs, ys, marker="o", color=COLORS[key[0]],
                linestyle=QOS_STYLES[key[1]], label=_series_label(key))

    yscale = args.y_scale
    if yscale == "log":
        all_ys = [v for d in series.values() for v in d.values() for v in v]
        if any(v is not None and v <= 0 for v in all_ys):
            print(f"  (info) {title}: y values <= 0, falling back to linear y scale")
            yscale = "linear"
    ax.set_xscale(xscale)
    ax.set_yscale(yscale)
    x_ticks = sorted({_label_sort_key(l)[0] for l in labels})
    ax.set_xticks(x_ticks)
    ax.set_xticklabels([f"{x:g} MB" for x in x_ticks], rotation=30, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outpath, dpi=args.dpi)
    plt.close(fig)
    print(f"  wrote {outpath}")
    return True


def _draw_bars(ax, series, args, legend=True):
    """Draw grouped bars into an existing axes; protocols/QoS as groups."""
    labels = sorted({l for d in series.values() for l in d}, key=_label_sort_key)
    if not labels:
        return
    keys = sorted(series, key=_series_sort_key)
    n = len(keys)
    width = 0.8 / max(n, 1)
    for i, key in enumerate(keys):
        data = series[key]
        ys, elo, ehi = [], [], []
        for label in labels:
            y = _aggregate(data.get(label, []), args.agg)
            if y is None:
                ys.append(0)
                elo.append(0)
                ehi.append(0)
                continue
            lo, hi = _error_bounds(data.get(label, []), args.error)
            ys.append(y)
            elo.append(y - lo if lo is not None else 0)
            ehi.append(hi - y if hi is not None else 0)
        x = [j + (i - (n - 1) / 2) * width for j in range(len(labels))]
        ax.bar(x, ys, width=width, label=_series_label(key) if legend else None,
               color=COLORS[key[0]], hatch=QOS_HATCH[key[1]],
               yerr=[elo, ehi] if args.error != "none" else None, capsize=2)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)


def _plot_bar(series, title, ylabel, outpath, args):
    """Grouped bar chart (categorical x)."""
    labels = sorted({l for d in series.values() for l in d}, key=_label_sort_key)
    if not labels:
        print(f"  (skip) {title}: no data")
        return False
    fig, ax = plt.subplots(figsize=args.figsize or (max(8.0, 1.5 * len(labels)), 5.0))
    _draw_bars(ax, series, args)
    if args.y_scale == "log":
        ax.set_yscale("log")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outpath, dpi=args.dpi)
    plt.close(fig)
    print(f"  wrote {outpath}")
    return True


def _chart_type_for(metric_cfg, args):
    if args.chart_type != "auto":
        return args.chart_type
    return "line" if metric_cfg["size_dependent"] else "bar"


def _render(data, cfg, prefix, metric, outdir, args):
    """Render one metric with the resolved chart type; return the fig tuple."""
    if not data:
        print(f"  (skip) {cfg['title']}: no data")
        return None
    outpath = os.path.join(outdir, f"{prefix}_{metric}.png")
    if _chart_type_for(cfg, args) == "line":
        _plot_line(data, cfg["title"], cfg["ylabel"], outpath, args)
    else:
        _plot_bar(data, cfg["title"], cfg["ylabel"], outpath, args)
    return (cfg["title"], data, cfg["ylabel"])


def _make_overview(figs, outpath, args):
    """Collate the per-metric figures into one dashboard-style bar grid."""
    if not figs:
        return
    grid = 3, 3
    fig, axes = plt.subplots(*grid, figsize=(15, 11))
    for ax in axes.flat:
        ax.axis("off")
    for i, (title, data, ylabel) in enumerate(figs[: grid[0] * grid[1]]):
        ax = axes.flat[i]
        ax.axis("on")
        _draw_bars(ax, data, args)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.tick_params(axis="x", labelsize=8, rotation=30)
    fig.suptitle("Benchmark overview")
    fig.tight_layout()
    fig.savefig(outpath, dpi=args.dpi)
    plt.close(fig)
    print(f"  wrote {outpath}")


def _parse_figsize(value):
    if not value:
        return None
    try:
        w, h = value.lower().split("x")
        return (float(w), float(h))
    except ValueError:
        sys.exit(f"Invalid --figsize {value!r}; expected e.g. '10x5'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=None,
                        help="Run id under --runs-dir to chart (preferred). "
                             "Overrides --csv-dir/--suffix.")
    parser.add_argument("--runs-dir", default=DEFAULT_CSV_DIR,
                        help="Directory containing the runs/ tree, i.e. the OUTPUT_DIR "
                             "parent (default: ./output).")
    parser.add_argument("--csv-dir", default=DEFAULT_CSV_DIR,
                        help="Legacy flat directory holding *_measurements*.csv files "
                             "(default: ./output). Ignored when --run is given.")
    parser.add_argument("--outdir", default=None,
                        help="Where to write PNGs. Default: <run dir>/charts when "
                             "--run is given, else output/charts.")
    parser.add_argument("--suffix", default=None,
                        help="Legacy measurement suffix, e.g. '_testing' or '_http_mobile'. "
                             "Default: MEASUREMENT_SUFFIX env, else '_testing', else plain. "
                             "Ignored when --run is given.")
    parser.add_argument("--protocols", nargs="+", choices=PROTOCOLS, default=PROTOCOLS,
                        help="Protocols to include (default: all).")
    parser.add_argument("--metrics", nargs="+", default=None,
                        help="Metric names to plot (default: all). "
                             "Client: goodput_mbps, transfer_time, latency, avg_cpu_pct, "
                             "peak_ram_mb, energy_j. Pcap: goodput_mbps, wire_throughput_mbps, "
                             "overhead_percentage, total_overhead_bytes, total_wire_bytes, "
                             "retransmissions, total_packets.")
    parser.add_argument("--file-sizes", nargs="+", type=float, default=None,
                        help="Only plot these file sizes in MB (default: all).")
    parser.add_argument("--qos", nargs="+", type=int, default=None,
                        help="MQTT QoS levels to include (default: both).")
    parser.add_argument("--mqtt-side", choices=["sender", "receiver", "both"],
                        default="sender",
                        help="Which MQTT row side to use (default: sender).")
    parser.add_argument("--chart-type", choices=["auto", "line", "bar"], default="auto",
                        help="auto: line for size-dependent metrics, bar for "
                             "size-invariant ones (default).")
    parser.add_argument("--agg", choices=["mean", "median", "min", "max"], default="mean",
                        help="How to combine repeat runs (default: mean).")
    parser.add_argument("--error", choices=["none", "minmax", "std", "q90"], default="minmax",
                        help="Error/band representation across runs (default: minmax).")
    parser.add_argument("--x-scale", choices=["auto", "linear", "log"], default="auto",
                        help="X axis scale (default: log for line charts).")
    parser.add_argument("--y-scale", choices=["linear", "log"], default="linear")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--figsize", default=None,
                        help="Figure size as WxH, e.g. '10x5' (default: auto).")
    parser.add_argument("--no-client", action="store_true",
                        help="Skip charts from client-side measurement CSVs.")
    parser.add_argument("--no-pcap", action="store_true",
                        help="Skip charts from the pcap analysis CSV.")
    parser.add_argument("--no-overview", action="store_true",
                        help="Do not render the combined overview dashboard.")
    args = parser.parse_args()
    args.figsize = _parse_figsize(args.figsize)

    # ------------------------------------------------------------------
    # Data source: a single run directory (preferred) or the legacy flat CSVs.
    # ------------------------------------------------------------------
    if args.run is not None:
        if not runs.read_manifest(args.runs_dir, args.run):
            available = runs.list_runs(args.runs_dir)
            hint = " Available runs:\n  " + "\n  ".join(available) if available else ""
            sys.exit(f"No such run: {args.run!r} under {args.runs_dir!r}.{hint}")
        csv_dir = runs.run_dir(args.runs_dir, args.run)
        outdir = args.outdir or os.path.join(csv_dir, "charts")
        print(f"Run:    {args.run}")
    else:
        csv_dir = args.csv_dir
        outdir = args.outdir or DEFAULT_OUT_DIR

    os.makedirs(outdir, exist_ok=True)

    print(f"CSV dir: {csv_dir}")
    print(f"Output:  {outdir}")

    # ------------------------------------------------------------------
    # 1. Client-side measurement CSVs
    # ------------------------------------------------------------------
    client_rows = {}
    for protocol in args.protocols:
        if args.run is not None:
            path = _run_file(csv_dir, protocol)
        else:
            suffix = args.suffix if args.suffix is not None else os.getenv("MEASUREMENT_SUFFIX")
            candidates = [s for s in [suffix, "_testing", ""] if s is not None]
            path = _resolve_file(csv_dir, protocol, candidates)
        if not path:
            print(f"  (missing) {protocol}_measurements*.csv")
            continue
        print(f"  using {os.path.basename(path)}")
        client_rows[protocol] = list(_csv_rows(path))

    client_figs = []
    if not args.no_client:
        for metric, cfg in CLIENT_METRICS.items():
            if args.metrics and metric not in args.metrics:
                continue
            data = _collect(client_rows, cfg["fields"], _client_label, args,
                            _size_mb_client)
            fig = _render(data, cfg, "client", metric, outdir, args)
            if fig:
                client_figs.append(fig)

    # ------------------------------------------------------------------
    # 2. pcap analysis CSV
    # ------------------------------------------------------------------
    pcap_rows = None
    if not args.no_pcap:
        if args.run is not None:
            pcap_path = _run_file(csv_dir, "pcap")
        else:
            suffix = args.suffix if args.suffix is not None else os.getenv("MEASUREMENT_SUFFIX")
            candidates = [s for s in [suffix, "_testing", ""] if s is not None]
            pcap_path = _resolve_file(csv_dir, "pcap", candidates) or os.path.join(
                csv_dir, "pcap_measurements.csv")
        if pcap_path and os.path.isfile(pcap_path):
            print(f"  using {os.path.basename(pcap_path)}")
            pcap_rows = {p: [] for p in PROTOCOLS}
            for row in _csv_rows(pcap_path):
                protocol = (row.get("protocol") or "").strip().lower()
                if protocol in args.protocols:
                    pcap_rows[protocol].append(row)
        else:
            print("  (missing) pcap_measurements*.csv")

    pcap_figs = []
    if pcap_rows:
        for metric, cfg in PCAP_METRICS.items():
            if args.metrics and metric not in args.metrics:
                continue
            data = _collect(pcap_rows, {p: metric for p in PROTOCOLS},
                            _pcap_label, args, _size_mb_pcap)
            fig = _render(data, cfg, "pcap", metric, outdir, args)
            if fig:
                pcap_figs.append(fig)

    # ------------------------------------------------------------------
    # 3. Combined overview dashboard (always bars)
    # ------------------------------------------------------------------
    if not args.no_overview:
        client_by_name = {title: (title, data, ylabel) for title, data, ylabel in client_figs}
        pcap_by_name = {title: (title, data, ylabel) for title, data, ylabel in pcap_figs}

        overview_figs = []
        for metric in OVERVIEW_METRICS:
            if metric in CLIENT_METRICS and CLIENT_METRICS[metric]["title"] in client_by_name:
                overview_figs.append(client_by_name[CLIENT_METRICS[metric]["title"]])
            elif metric in PCAP_METRICS and PCAP_METRICS[metric]["title"] in pcap_by_name:
                overview_figs.append(pcap_by_name[PCAP_METRICS[metric]["title"]])
        seen, deduped = set(), []
        for fig in overview_figs:
            if fig[0] in seen:
                continue
            seen.add(fig[0])
            deduped.append(fig)
        _make_overview(deduped, os.path.join(outdir, "overview.png"), args)

    print("Done.")


if __name__ == "__main__":
    main()
