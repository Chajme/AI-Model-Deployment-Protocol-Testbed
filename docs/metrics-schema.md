# Metrics & CSV schemas

All measurement files are appended CSVs with a header written on first write.

## Run layout

Every experiment writes to its own immutable **run directory**:

```
output/runs/<run_id>/
  run.json                        # manifest (see below)
  pcap_measurements.csv           # host harness (tshark)
  http_measurements.csv           # HTTP PUT client (protocol key http)
  http-get_measurements.csv       # HTTP GET download client (protocol key http-get)
  mqtt_measurements.csv           # MQTT sender AND receiver (side column)
  coap_measurements.csv           # CoAP client
  amqp_measurements.csv           # AMQP sender AND receiver (side column)
  grpc_measurements.csv           # gRPC sender AND receiver (side column)
  lwm2m_measurements.csv          # LwM2M client (side=client)
  transfer_failures.csv           # harness: attempts whose client process failed (if any)
  pcap/                           # one pcap per transfer
  charts/                         # generated on demand by common/charts.py --run
```

`<run_id>` is timestamp-based, e.g. `20260818T201455_mqtt_harsh`
(`<UTC-time>_<protocol>_<profile>`, plus `_tls` for a TLS run and `_r<i>` for
repetition *i* of a sweep), overridable via `--run-id` (runner.py) or
`RUN_ID`. The active run is shared between host and containers: `RUN_ID` env var
on the host, and an `.active_run` marker file inside `output/` (read through the
bind mount). Runs are **immutable** — a second write to the same id raises.

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
| `protocol` | `mqtt` / `http` / `coap` / `amqp` / `grpc` / `lwm2m` |
| `network_profile` | e.g. `iot`, `good`, `harsh` |
| `env` | `{NETWORK_PROFILE, DATA_DIR, OUTPUT_DIR}` snapshot |
| `docker`, `tshark` | tool versions at run start |
| `file_sizes`, `files` | bytes + names of the payloads actually transferred |
| `qos_levels` | MQTT QoS levels swept (MQTT runs only) |
| `flow` | `manual` for `benchmark_manager.py` CLI, absent for `runner.py` |
| `tls` | `true` for a `runner.py --tls` run |
| `shaping_model` | `access-link-bidir-v2` for runs made with the fixed shaping (ISSUES.md FIXED-15) |
| `git_commit`, `git_dirty` | code revision of the harness and whether tracked files had local changes |
| `images` | `{image: {id, repo_digests}}` of the containers of this stack |
| `pip_freeze` | `pip freeze` of the client container that ran the transfers |
| `sweep_id`, `repeat_index`, `seed` | sweep label, repetition number and order seed (`runner.py --repeat/--sweep-id`) |

`protocol` can also be `http-get` (device download) or `mqtt-windowed` (MQTT
with 20 chunks in flight; writes the `mqtt` CSV schema).

---

## 1. `output/pcap_measurements*.csv` — host harness (tshark)

| # | Column | Type | Meaning |
|---|---|---|---|
| 1 | `protocol` | str | `mqtt` / `http` / `coap` / `amqp` / `grpc` / `lwm2m` |
| 2 | `filename` | str | payload file name, e.g. `binary_file_1mb.bin` |
| 3 | `label` | str | `<filename>_<qos>` for MQTT, else `<filename>` |
| 4 | `qos` | int / empty | MQTT QoS (1 or 2); empty for the other protocols |
| 5 | `file_size_bytes` | int | exact payload size |
| 6 | `total_packets` | int | every frame captured on the server interface |
| 7 | `total_wire_bytes` | int | sum of `frame.len` across all frames |
| 8 | `protocol_packets` | int | frames matching the protocol filter |
| 9 | `protocol_wire_bytes` | int | sum of `frame.len` for protocol frames |
| 10 | `retransmissions` | int | TCP: `tcp.analysis.*` flags; CoAP/LwM2M: repeated CON MIDs (see pcap-analysis) |
| 11 | `duration_seconds` | float | first to last frame matching the protocol window filter (all-frames span only as a fallback) |
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
| `sample_count` | int | CPU/RAM samples behind the averages |

---

## 2b. `output/http-get_measurements*.csv` — HTTP GET download client

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `http-get` |
| `direction` | str | `download` |
| `tls` | bool | HTTPS run (`TLS=1`) |
| `file_size` | float | MB |
| `time_to_transfer` | float / `X` | s, request-start → last byte (includes resume time); `X` on failure |
| `latency_tcp_rtt` | float | s, bare TCP connect to the server |
| `tls_handshake_s` | float / `X` | s, TLS handshake after the TCP connect (TLS runs only) |
| `latency_ttfb` | float | s, request-start → response headers |
| `goodput_mbps` | float / `X` | `file_size_bytes × 8 / (time_to_transfer × 1e6)` |
| `resumed` | int | number of Range (206) continuations |
| `bytes_resumed` | int | bytes received after a resume |
| `integrity_ok` | bool | SHA-256 of the received bytes equals the source payload |
| `avg_cpu_usage`, `peak_ram_usage`, `sample_count` | str / int | as for HTTP |

---

## 3. `output/mqtt_measurements*.csv` — MQTT sender **and** receiver

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `mqtt` |
| `qos` | int | 1 or 2 |
| `side` | str | `sender` (client_a) or `receiver` (client_b) |
| `tls` | bool | MQTT over TLS run (`TLS=1`) |
| `tls_handshake_s` | float / `X` | sender: publisher's TLS handshake (server side); receiver: the device's handshake over the constrained link, measured once per connection |
| `file_size` | float | MB |
| `sender_duration` | float / `X` | chunk-transmission window only (the metadata publish+ACK happens before the timer starts; `X` in receiver rows) |
| `receiver_duration` | float / `X` | receiver wall-clock; `X` in sender rows and in single-chunk receiver rows |
| `latency` | float | sender: metadata publish→ACK round trip; receiver: first-chunk lag |
| `goodput_mbps` | float | file_size × 8 / (own duration × 1e6) |
| `integrity_ok` | bool / empty | receiver verifies SHA-256; empty in sender rows |
| `avg_cpu_usage` | str | `"12.34%"` |
| `peak_ram_usage` | str | `"28.15 MB"` |
| `sample_count` | int | CPU/RAM samples behind the averages |

One transfer → **two rows** (sender + receiver), each with its own duration and
latency definition. `charts.py` selects the sender row by default (`--side auto`).

Timing note: the sender's timed window covers **only chunk transmission** —
the metadata publish+ACK round trip happens before the timer starts, so a lost
metadata ACK can no longer inflate `sender_duration`; the metadata round trip
is recorded separately in `latency`. Single-chunk transfers (file ≤ 1 chunk)
record `receiver_duration="X"` and `goodput_mbps="X"` in receiver rows — a
single chunk spans no measurable arrival window (the old sub-millisecond
windows produced fake 1500+ Mbps rows). First-chunk lag and integrity are
still recorded.

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
| `sample_count` | int | CPU/RAM samples behind the averages |

---

## 5. `output/amqp_measurements*.csv` — AMQP sender **and** receiver

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `amqp` |
| `side` | str | `sender` or `receiver` |
| `file_size` | float | MB |
| `sender_duration` | float / `X` | chunk-transmission window only (the metadata publish+confirm happens before the timer starts; `X` in receiver rows) |
| `receiver_duration` | float / `X` | receiver wall-clock; `X` in sender rows and in single-chunk receiver rows |
| `latency` | float | sender: metadata publish-confirm round trip; receiver: first-chunk lag |
| `goodput_mbps` | float | file_size × 8 / (own duration × 1e6) |
| `integrity_ok` | bool / empty | receiver verifies SHA-256; empty in sender rows |
| `avg_cpu_usage` | str | `"12.34%"` |
| `peak_ram_usage` | str | `"28.15 MB"` |
| `sample_count` | int | CPU/RAM samples behind the averages |

One transfer → **two rows** (sender + receiver). The sender's timed window
covers only chunk transmission (metadata confirm outside the window, recorded
in `latency`); single-chunk transfers record `receiver_duration="X"` and
`goodput_mbps="X"` in receiver rows.

---

## 6. `output/grpc_measurements*.csv` — gRPC sender **and** receiver

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `grpc` |
| `side` | str | `sender` or `receiver` |
| `file_size` | float | MB |
| `sender_duration` | float / `X` | full `Upload` RPC call (stream start → result); `X` in receiver rows |
| `receiver_duration` | float / `X` | server-side reassembly window; `X` in sender rows |
| `latency` | float | unary `Ping` RPC round trip |
| `goodput_mbps` | float | file_size × 8 / (own duration × 1e6) |
| `integrity_ok` | bool / empty | server verifies SHA-256 and renames `.part` → final on match |
| `avg_cpu_usage` | str | `"12.34%"` |
| `peak_ram_usage` | str | `"28.15 MB"` |
| `sample_count` | int | CPU/RAM samples behind the averages |

One transfer → **two rows** (sender + receiver).

---

## 7. `output/lwm2m_measurements*.csv` — LwM2M client

| Column | Type | Meaning |
|---|---|---|
| `protocol` | str | `lwm2m` |
| `side` | str | `client` (the device-side emulator is the only row producer) |
| `file_size` | float | MB |
| `download_duration` | float | s, blockwise `GET` of the package object only (registration and state reports excluded) |
| `latency` | float | s, registration (`POST /rd`) round trip |
| `goodput_mbps` | float | file_size × 8 / (download_duration × 1e6) |
| `integrity_ok` | bool | client verifies the SHA-256 of the pulled object |
| `avg_cpu_usage` | str | `"12.34%"` |
| `peak_ram_usage` | str | `"28.15 MB"` |
| `sample_count` | int | CPU/RAM samples behind the averages |

---

## 8. CPU / RAM — `common/resource_monitor.py`

`ResourceMonitor` samples the **client process** (`psutil.Process(os.getpid())`
-> cpu_percent(non-blocking) + RSS) on a background thread. It samples only the
launched process, not its subprocess tree. `stop()` keeps sampling until at
least `MIN_WINDOW_SECONDS` (0.2 s) have elapsed since `start()` so fast
transfers still collect usable averages, and is idempotent — later calls return
the same stats.

| Output | Definition |
|---|---|
| `avg_cpu_pct` | mean of CPU% samples, **divided once by `cpu_count`** (fraction of all host cores, 0-100) |
| `peak_rss_mb` | max RSS sample in MiB |
| `sample_count` | number of CPU/RAM samples behind the averages |

All clients sample at `sample_interval=0.01` (100 Hz); the chart tooling parses
the units off the strings (e.g. `"2.71%"`, `"28.15 MB"`) - see
[charts.md](charts.md) `_to_number`.

**Caveats.** `avg_cpu_pct` is normalized by the *host* logical-core count
(Docker CPU limits are not applied), so absolute values are small and mainly
useful for relative comparison. `sample_count` is the confidence signal: rows
with very few samples should be treated as low-confidence.

**Energy was removed (v2).** Earlier runs recorded `energy_est` = CPU share ×
an assumed 15 W TDP × duration. That described the benchmark host, not an IoT
device, so it is no longer written or reported. Device energy is measured only
in the field test, on the real hardware (USB / INA219 meter).

---

## 9. Which CSV is which (quick reference)

| Path | Producer | When |
|---|---|---|
| `output/runs/<run_id>/{proto}_measurements.csv` | client container | every run (manual or automated) |
| `output/runs/<run_id>/pcap_measurements.csv` | host harness | every run |
| `output/runs/<run_id>/pcap/*.pcap` | capture sidecar | one per transfer |
| `output/runs/<run_id>/transfer_failures.csv` | host harness | only when a client process exits non-zero |
| `output/runs-legacy-v1/` | — | runs made before the v2 shaping fix (tag `analysis-v1-legacy`) |
| `output/evidence/*.txt` | manual checks | verification evidence of the v2 changes |
| `output/runs/<run_id>/charts/*.png` | `common/charts.py --run` | generated on demand |
| `output/*_measurements*.csv`, `output/pcap/` | any | **legacy** — archived to `output/legacy/`, written only when no run is active |
