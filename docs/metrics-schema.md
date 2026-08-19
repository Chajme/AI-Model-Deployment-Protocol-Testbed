# Metrics & CSV schemas

All measurement files are appended CSVs with a header written on first write.

## Run layout

Every experiment writes to its own immutable **run directory**:

```
output/runs/<run_id>/
  run.json                        # manifest (see below)
  pcap_measurements.csv           # host harness (tshark)
  http_measurements.csv           # HTTP client
  mqtt_measurements.csv           # MQTT sender AND receiver (side column)
  coap_measurements.csv           # CoAP client
  pcap/                           # one pcap per transfer
  charts/                         # generated on demand by common/charts.py --run
```

`<run_id>` is timestamp-based, e.g. `20260818T201455_mqtt_harsh`
(`<UTC-time>_<protocol>_<profile>`), overridable via `--run-id` (runner.py) or
`RUN_ID`. The active run is shared between host and containers: `RUN_ID` env var
on the host, and an `.active_run` marker file inside `output/` (read through the
bind mount). Runs are **immutable** â€” a second write to the same id raises.

Legacy flat files (`output/*_measurements*.csv`, `output/pcap/`) were archived
to `output/legacy/`. Without an active run, writers fall back to the flat
`OUTPUT_DIR` so out-of-band transfers still work.

## Common metadata columns

Every CSV carries three leading columns so files stay self-describing even if
concatenated across runs:

| Column | Type | Meaning |
|---|---|---|
| `run_id` | str | id of the run that produced the row (empty when no run is active) |
| `timestamp` | str | UTC ISO-8601 time of the write |
| `network_profile` | str | `NETWORK_PROFILE` env (e.g. `iot`, `good`) |

## `run.json` manifest

Written by `common/runs.new_run()`, extended by `benchmark_manager.run_protocol()`:

| Key | Meaning |
|---|---|
| `run_id` | the run id |
| `created_at` | UTC ISO-8601 creation time |
| `protocol` | `mqtt` / `http` / `coap` |
| `network_profile` | e.g. `iot`, `good`, `harsh` |
| `env` | `{NETWORK_PROFILE, MEASUREMENT_SUFFIX, DATA_DIR, OUTPUT_DIR}` snapshot |
| `docker`, `tshark` | tool versions at run start |
| `file_sizes`, `files` | bytes + names of the payloads actually transferred |
| `qos_levels` | MQTT QoS levels swept (MQTT runs only) |
| `flow` | `manual` for `benchmark_manager.py` CLI, absent for `runner.py` |

---

## 1. `output/pcap_measurements*.csv` â€” host harness (tshark)

| # | Column | Type | Meaning |
|---|---|---|---|
| 1 | `protocol` | str | `mqtt` / `http` / `coap` |
| 2 | `filename` | str | payload file name, e.g. `binary_file_1mb.bin` |
| 3 | `label` | str | `<filename>_<qos>` for MQTT, else `<filename>` |
| 4 | `qos` | int / empty | MQTT QoS (1 or 2); empty for HTTP/CoAP |
| 5 | `file_size_bytes` | int | exact payload size |
| 6 | `total_packets` | int | every frame captured on the server interface |
| 7 | `total_wire_bytes` | int | sum of `frame.len` across all frames |
| 8 | `protocol_packets` | int | frames matching the protocol filter |
| 9 | `protocol_wire_bytes` | int | sum of `frame.len` for protocol frames |
| 10 | `retransmissions` | int | TCP: `tcp.analysis.*` flags; CoAP: repeated CON MIDs (see pcap-analysis) |
| 11 | `duration_seconds` | float | last â’ first frame relative timestamp |
| 12 | `total_overhead_bytes` | int | `total_wire_bytes â’ file_size_bytes` |
| 13 | `overhead_percentage` | float | overhead as % of payload |
| 14 | `wire_throughput_mbps` | float | `total_wire_bytes Ă— 8 / (duration Ă— 1e6)` |
| 15 | `goodput_mbps` | float | `file_size_bytes Ă— 8 / (duration Ă— 1e6)` |
| 16 | `packet_types` | JSON str | per-type frame histogram, e.g. `{"0": 391, "2": 407}` for CoAP CON/ACK |

---

## 2. `output/http_measurements*.csv` â€” HTTP client

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `http` |
| `file_size` | float | MB |
| `time_to_transfer` | float | s, request-start â†’ response-end (`time.perf_counter`) |
| `latency_tcp_rtt` | float | s, bare TCP connect to `http-server:8000` |
| `latency_ttfb` | float | s, request-start â†’ response headers arrive (response hook) |
| `goodput_mbps` | float | `file_size_bytes Ă— 8 / (time_to_transfer Ă— 1e6)` |
| `integrity_ok` | bool | HTTP 200 (server verified checksum) |
| `avg_cpu_usage` | str | e.g. `"12.34%"` |
| `peak_ram_usage` | str | e.g. `"28.15 MB"` |
| `energy_est` | str | e.g. `"0.0041"` (joules) |

---

## 3. `output/mqtt_measurements*.csv` â€” MQTT sender **and** receiver

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `mqtt` |
| `qos` | int | 1 or 2 |
| `side` | str | `sender` (client_a) or `receiver` (client_b) |
| `file_size` | float | MB |
| `sender_duration` | float / `X` | sender wall-clock; `X` in receiver rows |
| `receiver_duration` | float / `X` | receiver wall-clock; `X` in sender rows |
| `latency` | float | sender: metadata ACK latency; receiver: first-chunk lag |
| `goodput_mbps` | float | file_size Ă— 8 / (own duration Ă— 1e6) |
| `integrity_ok` | bool / empty | receiver verifies SHA-256; empty in sender rows |
| `avg_cpu_usage` | â€” | MQTT writes **no** CPU/RAM/energy columns |

One transfer â†’ **two rows** (sender + receiver), each with its own duration and
latency definition. `charts.py` reads the sender row by default.

---

## 4. `output/coap_measurements*.csv` â€” CoAP client

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `coap` |
| `file_size` | float | MB |
| `time_to_transfer` | float | s, request â†’ final response |
| `latency` | float | s, `GET /.well-known/core` round-trip |
| `goodput_mbps` | float | file_size Ă— 8 / (time_to_transfer Ă— 1e6) |
| `integrity_ok` | bool | response code is successful (2.04 Changed) |
| `avg_cpu_usage` | str | `"12.34%"` |
| `peak_ram_usage` | str | `"28.15 MB"` |
| `energy_est` | str | joules |

---

## 5. CPU / RAM / energy â€” `common/resource_monitor.py`

`ResourceMonitor` samples the **client process tree** (`psutil.Process(os.getpid())`
â†’ cpu_percent(non-blocking) + RSS) on a background thread.

| Output | Definition |
|---|---|
| `avg_cpu_pct` | mean of CPU% samples, **divided by `cpu_count`** (so it's per-core %) |
| `peak_rss_mb` | max RSS sample in MiB |
| `energy_j` | `(avg_cpu_pct / 100) / logical_cores Ă— TDP Ă— duration_s` |

`TDP` defaults to `CPU_TDP_WATTS` env var or **15.0 W**. The comment in the code
notes this is an approximation; RAPL (`intel-rapl`) is more accurate.

HTTP and CoAP sample at `sample_interval=0.01` (100 Hz); the chart tooling
parses the units off the strings (e.g. `"2.71%"`, `"28.15 MB"`) â€” see
[charts.md](charts.md) `_to_number`.

---

## 6. Which CSV is which (quick reference)

| Path | Producer | When |
|---|---|---|
| `output/runs/<run_id>/{proto}_measurements.csv` | client container | every run (manual or automated) |
| `output/runs/<run_id>/pcap_measurements.csv` | host harness | every run |
| `output/runs/<run_id>/pcap/*.pcap` | capture sidecar | one per transfer |
| `output/runs/<run_id>/charts/*.png` | `common/charts.py --run` | generated on demand |
| `output/*_measurements*.csv`, `output/pcap/` | any | **legacy** â€” archived to `output/legacy/`, written only when no run is active |