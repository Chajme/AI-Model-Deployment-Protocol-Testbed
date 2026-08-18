# Metrics & CSV schemas

All measurement files are appended CSVs with a header written on first write.
The output directory comes from `OUTPUT_DIR` (host harness sets `./output`;
containers default to `/app/output`, bind-mounted to `./output`).

File naming: `output/<protocol>_measurements<suffix>.csv` where `<suffix>` is
`MEASUREMENT_SUFFIX` (e.g. `_testing`, or `mqtt_good` from the runner).

---

## 1. `output/pcap_measurements*.csv` — host harness (tshark)

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
| 11 | `duration_seconds` | float | last − first frame relative timestamp |
| 12 | `total_overhead_bytes` | int | `total_wire_bytes − file_size_bytes` |
| 13 | `overhead_percentage` | float | overhead as % of payload |
| 14 | `wire_throughput_mbps` | float | `total_wire_bytes × 8 / (duration × 1e6)` |
| 15 | `goodput_mbps` | float | `file_size_bytes × 8 / (duration × 1e6)` |
| 16 | `packet_types` | JSON str | per-type frame histogram, e.g. `{"0": 391, "2": 407}` for CoAP CON/ACK |

---

## 2. `output/http_measurements*.csv` — HTTP client

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `http` |
| `file_size` | float | MB |
| `time_to_transfer` | float | s, request-start → response-end (`time.perf_counter`) |
| `latency_tcp_rtt` | float | s, bare TCP connect to `http-server:8000` |
| `latency_ttfb` | float | s, request-start → response headers arrive (response hook) |
| `goodput_mbps` | float | `file_size_bytes × 8 / (time_to_transfer × 1e6)` |
| `integrity_ok` | bool | HTTP 200 (server verified checksum) |
| `avg_cpu_usage` | str | e.g. `"12.34%"` |
| `peak_ram_usage` | str | e.g. `"28.15 MB"` |
| `energy_est` | str | e.g. `"0.0041"` (joules) |

---

## 3. `output/mqtt_measurements*.csv` — MQTT sender **and** receiver

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `mqtt` |
| `qos` | int | 1 or 2 |
| `side` | str | `sender` (client_a) or `receiver` (client_b) |
| `file_size` | float | MB |
| `sender_duration` | float / `X` | sender wall-clock; `X` in receiver rows |
| `receiver_duration` | float / `X` | receiver wall-clock; `X` in sender rows |
| `latency` | float | sender: metadata ACK latency; receiver: first-chunk lag |
| `goodput_mbps` | float | file_size × 8 / (own duration × 1e6) |
| `integrity_ok` | bool / empty | receiver verifies SHA-256; empty in sender rows |
| `avg_cpu_usage` | — | MQTT writes **no** CPU/RAM/energy columns |

One transfer → **two rows** (sender + receiver), each with its own duration and
latency definition. `charts.py` reads the sender row by default.

---

## 4. `output/coap_measurements*.csv` — CoAP client

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `coap` |
| `file_size` | float | MB |
| `time_to_transfer` | float | s, request → final response |
| `latency` | float | s, `GET /.well-known/core` round-trip |
| `goodput_mbps` | float | file_size × 8 / (time_to_transfer × 1e6) |
| `integrity_ok` | bool | response code is successful (2.04 Changed) |
| `avg_cpu_usage` | str | `"12.34%"` |
| `peak_ram_usage` | str | `"28.15 MB"` |
| `energy_est` | str | joules |

---

## 5. CPU / RAM / energy — `common/resource_monitor.py`

`ResourceMonitor` samples the **client process tree** (`psutil.Process(os.getpid())`
→ cpu_percent(non-blocking) + RSS) on a background thread.

| Output | Definition |
|---|---|
| `avg_cpu_pct` | mean of CPU% samples, **divided by `cpu_count`** (so it's per-core %) |
| `peak_rss_mb` | max RSS sample in MiB |
| `energy_j` | `(avg_cpu_pct / 100) / logical_cores × TDP × duration_s` |

`TDP` defaults to `CPU_TDP_WATTS` env var or **15.0 W**. The comment in the code
notes this is an approximation; RAPL (`intel-rapl`) is more accurate.

HTTP and CoAP sample at `sample_interval=0.01` (100 Hz); the chart tooling
parses the units off the strings (e.g. `"2.71%"`, `"28.15 MB"`) — see
[charts.md](charts.md) `_to_number`.

---

## 6. Which CSV is which (quick reference)

| Path pattern | Producer | When |
|---|---|---|
| `output/{proto}_measurements_testing.csv` | client container | manual runs (`MEASUREMENT_SUFFIX=_testing` in `docker-compose.yaml`) |
| `output/{proto}_measurements{proto}_{profile}.csv` | client container | automated runs (`runner.py` sets suffix) |
| `output/pcap_measurements.csv` | host harness | manual runs (no suffix) |
| `output/pcap_measurements{proto}_{profile}.csv` | host harness | automated runs |