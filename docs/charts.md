# Charts — `common/charts.py`

Renders the result CSVs into PNG comparison charts. This page documents the
metric catalog, the auto line/bar decision, series construction, aggregation,
error bands, resolution logic, and every flag.

Requires matplotlib (not in the core requirements):

```bash
pip install -r requirements-charts.txt
```

---

## 1. Metric catalog

### Client-side metrics (`CLIENT_METRICS`)

`fields` maps each protocol to its CSV column (MQTT has **no** CPU/RAM/energy;
every other protocol populates all columns via `common/resource_monitor.py`):

| Metric | Title | y-label | size-dep. | http col | coap col | mqtt col | amqp col | grpc col | lwm2m col |
|---|---|---|---|---|---|---|---|---|---|
| `goodput_mbps` | Goodput (client-measured) | Mbps | yes | `goodput_mbps` | `goodput_mbps` | `goodput_mbps` | `goodput_mbps` | `goodput_mbps` | `goodput_mbps` |
| `transfer_time` | Transfer time | seconds | yes | `time_to_transfer` | `time_to_transfer` | `sender_duration` | `sender_duration` | `sender_duration` | `download_duration` |
| `latency` | Latency | seconds | yes | `latency_tcp_rtt` | `latency` | `latency` | `latency` | `latency` | `latency` |
| `avg_cpu_pct` | Avg CPU usage | % | no | `avg_cpu_usage` | `avg_cpu_usage` | — | `avg_cpu_usage` | `avg_cpu_usage` | `avg_cpu_usage` |
| `peak_ram_mb` | Peak RAM | MB | no | `peak_ram_usage` | `peak_ram_usage` | — | `peak_ram_usage` | `peak_ram_usage` | `peak_ram_usage` |
| `energy_j` | Energy estimate | J | no | `energy_est` | `energy_est` | — | `energy_est` | `energy_est` | `energy_est` |

#### Metric semantics caveats

- **Sender vs receiver rows.** MQTT, AMQP, gRPC and LwM2M record one row per
  side per transfer. The `--side` flag (default `sender`) selects which rows
  feed the charts; without filtering, sender and receiver values would average
  together into meaningless midpoints (e.g. gRPC sender goodput counts from
  stream start, receiver goodput only from first chunk arrival).
- **`transfer_time` mixes push and pull semantics.** HTTP/CoAP/MQTT/AMQP/gRPC
  measure an *upload* (including metadata + acks); LwM2M measures the
  *blockwise download* only (registration and state exchange excluded), since
  LwM2M is a pull-model firmware update. Compare accordingly.
- **`latency` differs per protocol**: TCP connect RTT (HTTP), Ping RPC RTT
  (gRPC), broker publish-confirm round trip (MQTT/AMQP), registration round
  trip (LwM2M), CoAP discovery GET (CoAP).

### pcap metrics (`PCAP_METRICS`)

All size-dependent, single source (the run's `pcap_measurements.csv`):

| Metric | Title | y-label |
|---|---|---|
| `goodput_mbps` | Goodput (pcap) | Mbps |
| `wire_throughput_mbps` | Wire throughput (pcap) | Mbps |
| `overhead_percentage` | Overhead (pcap) | % |
| `total_overhead_bytes` | Total overhead bytes (pcap) | bytes |
| `total_wire_bytes` | Total wire bytes (pcap) | bytes |
| `retransmissions` | Retransmissions | count |
| `total_packets` | Total packets | packets |

### Overview dashboard

`OVERVIEW_METRICS = [goodput_mbps, transfer_time, latency, avg_cpu_pct,
wire_throughput_mbps, overhead_percentage, retransmissions, total_wire_bytes]`
rendered as a 3x3 grouped-bar grid (`overview.png`), deduplicated by title
(client vs pcap `goodput` share a slot).

### Overhead comparability across topologies

The capture sidecar sits on the server/broker network namespace, so
broker-topology protocols (MQTT, AMQP) record **both** data legs (publish +
delivery) plus confirm/ack traffic in one pcap: wire bytes of roughly **2x the
file size (~114% overhead)** at large sizes. Client/server-topology protocols
(HTTP, gRPC) only carry a single data leg through their capture point
(~5-13%). LwM2M sits between (~20%, blockwise per-block headers + acks).
When comparing `overhead_percentage` across protocols, normalize for this
topology difference first (see also protocol-transfers.md).

---

## 2. Auto chart type

```python
def _chart_type_for(metric_cfg, args):
    if args.chart_type != "auto":
        return args.chart_type
    return "line" if metric_cfg["size_dependent"] else "bar"
```

- **Line** — size-dependent metrics: file size on x (log by default), one line
  per (protocol, QoS) series, mean point + shaded band.
- **Bar** — size-invariant metrics (CPU/RAM/energy) and the overview: grouped
  bars per protocol, QoS via hatching.
- `--chart-type line|bar` forces a style for every metric.

---

## 3. Series construction (`_collect`)

Filters applied per row, in order:

1. **`--protocols`** — caller passes only the selected protocols.
2. **MQTT side** — `--mqtt-side sender|receiver|both` (default `sender`).
   Non-MQTT protocols always pass.
3. **MQTT QoS** — `--qos 1 2` filters the row's qos; HTTP/CoAP are unaffected.
4. **`--file-sizes`** — keeps only rows whose size (MB) matches a listed value
   (tolerance 1e-6).
5. **value parse** — `_to_number()` extracts the leading number from strings
   like `"2.71%"`, `"28.15 MB"`, or `"X"` (→ `None`, row skipped).

The series key is `(protocol, qos)` — MQTT QoS 1 and 2 become **separate
series**, HTTP/CoAP use `qos=None`. Each series maps `x label → [run values]`.

Labels:
- client: `"{size:.3g} MB"` (+ `" | qos N"` for MQTT).
- pcap: filename with `binary_file_` / `.bin` stripped (+ QoS).

---

## 4. Aggregation and error bands

```python
def _aggregate(values, agg):      # mean (default) | median | min | max
def _error_bounds(values, error): # none | minmax (default) | std | q90
```

- Repeat runs of the same (protocol, size) collapse to a single point via
  `_aggregate`.
- Line charts fill `fill_between(xs, lo, hi)` at `alpha=0.15` in the protocol
  color.
- Bar charts pass `yerr=[y-lo, hi-y]` to `ax.bar` (with `capsize=2`).
- `q90` uses 10th/90th percentile indices (`round(0.1*(n-1))`); `std` uses
  sample stdev around the mean.

---

## 5. Axes and layout

- `--x-scale auto|linear|log` (auto → **log**; auto falls back to linear if any
  x ≤ 0).
- `--y-scale linear|log` (log also auto-falls-back if any value ≤ 0, with an
  `(info)` message).
- `--figsize WxH` (e.g. `10x5`) or auto `(max(8, 1.5 × n_labels), 5)`.
- `--dpi` (default 150).
- Protocol colors: http `#1f77b4`, mqtt `#ff7f0e`, coap `#2ca02c`.
- QoS rendering: `QOS_STYLES = {None:"-", "1":"--", "2":":"}` (line styles),
  `QOS_HATCH = {None:None, "1":"//", "2":"xx"}` (bar hatches).

---

## 6. Data source (`--run` preferred, legacy fallback)

Run mode is the default workflow:

```bash
python common/charts.py --run 20260818T201455_mqtt_harsh
python common/charts.py --runs-dir output --run <run_id>   # --runs-dir is the OUTPUT_DIR parent
```

```python
run_dir = <runs-dir>/runs/<run_id>
client_files = run_dir/<proto>_measurements.csv      # exact names, no suffix guessing
pcap_file    = run_dir/pcap_measurements.csv
outdir       = <run_dir>/charts                        # unless --outdir given
```

- Charts **only the selected run** — no cross-run mixing, no `--suffix`.
- Unknown `--run` prints the available run ids (`common/runs.list_runs`) and exits.

Legacy flat mode (`--csv-dir`, `--suffix`) is kept for old data:

```python
suffix = args.suffix if args.suffix is not None else os.getenv("MEASUREMENT_SUFFIX")
candidates = [s for s in [suffix, "_testing", ""] if s is not None]
path = <csv-dir>/<base>_measurements<suffix>.csv   # first existing match
```

---

## 7. Full flag reference

| Flag | Default | Effect |
|---|---|---|
| `--run` | — | run id under `--runs-dir` to chart (preferred; overrides `--csv-dir`/`--suffix`) |
| `--runs-dir` | `./output` | directory containing the `runs/` tree (the `OUTPUT_DIR` parent) |
| `--csv-dir` | `./output` (`OUTPUT_DIR` env) | legacy flat CSVs (ignored with `--run`) |
| `--outdir` | `<run_dir>/charts` (with `--run`) / `output/charts` | where PNGs are written |
| `--suffix` | env → `_testing` → plain | legacy measurement set (ignored with `--run`) |
| `--protocols` | all | subset of `http mqtt coap` |
| `--metrics` | all | subset of the 13 metric names above |
| `--file-sizes` | all | only these sizes in MB |
| `--qos` | both | MQTT QoS levels |
| `--mqtt-side` | `sender` | `sender` / `receiver` / `both` |
| `--chart-type` | `auto` | `auto` / `line` / `bar` |
| `--agg` | `mean` | `mean` / `median` / `min` / `max` |
| `--error` | `minmax` | `none` / `minmax` / `std` / `q90` |
| `--x-scale` | `auto` | `auto` / `linear` / `log` |
| `--y-scale` | `linear` | `linear` / `log` |
| `--dpi` | `150` | PNG resolution |
| `--figsize` | auto | `WxH` e.g. `10x5` |
| `--no-client` | off | skip client CSVs |
| `--no-pcap` | off | skip pcap CSV |
| `--no-overview` | off | skip `overview.png` |

### Examples

```bash
python common/charts.py --run 20260818T201455_mqtt_harsh
python common/charts.py --run <run_id> --metrics goodput_mbps overhead_percentage
python common/charts.py --run <run_id> --file-sizes 1 5 20 50 --qos 2 --chart-type bar
python common/charts.py --run <run_id> --error none --agg median --no-overview
python common/charts.py --suffix http_good   # legacy flat mode
```

---

## 8. Output files (default run, 14 PNGs)

`client_goodput_mbps`, `client_transfer_time`, `client_latency`,
`client_avg_cpu_pct`, `client_peak_ram_mb`, `client_energy_j`,
`pcap_goodput_mbps`, `pcap_wire_throughput_mbps`, `pcap_overhead_percentage`,
`pcap_total_overhead_bytes`, `pcap_total_wire_bytes`, `pcap_retransmissions`,
`pcap_total_packets`, `overview.png`.

Metrics with no data are skipped with a `(skip) ...: no data` message; missing
CSVs print `(missing) ...` and are skipped.