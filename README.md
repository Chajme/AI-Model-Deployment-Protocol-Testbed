# AI-Model-Deployment-Protocol-Testbed

A **reproducible, containerized benchmark harness** that compares how three IoT
protocols — **MQTT**, **HTTP**, and **CoAP** — move AI-model-sized binary files
(250 KB up to 200 MB) over a network. It measures each transfer **twice**:

- **client side** — runtime metrics collected inside the sender (goodput,
  transfer time, latency, CPU, RAM, energy estimate, integrity),
- **packet side** — a pcap captured by a sidecar container and analyzed with
  tshark (packet counts, wire bytes, protocol overhead, retransmissions,
  goodput/throughput).

Transfers can run on a **clean baseline** network or under **emulated network
chaos** (latency, loss, jitter, reordering, bandwidth caps) via Linux `tc`, so
results are comparable across machines without needing a real network.

---

## Features

- **Three protocols, one harness** — MQTT (1 MB chunked publish, QoS 1/2 sweep),
  HTTP (streaming PUT), CoAP (blockwise PUT) against real servers/brokers in
  Docker.
- **Per-transfer packet capture** — a `netshoot` sidecar shares the server's
  network namespace; `tcpdump` is started/stopped per run and the resulting
  pcap is analyzed with tshark.
- **Capture-faithful measurement** — NIC segmentation offloads (GRO/GSO/TSO)
  are disabled and tcpdump uses an 8 MiB kernel buffer so captures show real
  MTU-sized frames without drops.
- **Client-side resource metrics** — CPU %, peak RSS, and a TDP-based energy
  estimate sampled during each transfer.
- **End-to-end integrity** — SHA-256 is computed by the sender and verified by
  the receiver/server; every row records whether the file arrived intact.
- **Emulated network profiles** — `good`, `iot`, `harsh`, `mobile`,
  `satellite` applied with `tc netem` + `tbf` inside the containers (no real
  network needed, reproducible on any host with NET_ADMIN).
- **Automated sweep** — `runner.py` builds, starts, waits, drives, and tears
  down each protocol × profile combination; per-profile CSV files are kept
  separate via a `MEASUREMENT_SUFFIX`.
- **Chart generation** — `common/charts.py` turns the CSVs into PNG comparison
  charts (line charts for size-dependent metrics, grouped bars for CPU/RAM/energy
  and the overview dashboard), with min–max bands across repeat runs and
  MQTT QoS 1/2 as distinct series.

---

## Architecture

Three isolated Docker bridge networks — `mqtt-net`, `http-net`, `coap-net` —
each containing a **client**, a **server** (or **broker**), and a **capture
sidecar**. The sidecar (`nicolaka/netshoot`) uses `network_mode:
service:<server>` so it sees traffic exactly as the server does.

A **host-side harness** drives one transfer at a time:

1. start `tcpdump` in the capture sidecar (offloads disabled first),
2. exec a single-file transfer inside the client container,
3. stop `tcpdump`, copy the pcap from the container to `output/pcap/`,
4. analyze the pcap with tshark and append a row to `output/pcap_measurements*.csv`,
   while the client appends its runtime row to `output/<proto>_measurements*.csv`.

Two compose stacks share the same image:

| | `docker-compose.yaml` | `docker-compose.automated.yaml` |
|---|---|---|
| Purpose | manual baseline benchmark | automated chaos sweep |
| Network | clean (no tc) | `tc` chaos applied at startup in every container |
| Driven by | `protocols/benchmark_manager.py` | `runner.py` (build → up → wait → drive → down) |
| Profiles | — | `good`, `iot`, `harsh`, `mobile`, `satellite` |

(`docker-compose.tc.yaml` is a legacy scratch file for single-service chaos
testing; the two files above are the supported paths.)

---

## Repository layout

```
common/                        host-side and shared helpers
  charts.py                    CSV → PNG comparison charts (line/bar, bands, QoS series)
  pcap_analyzer.py             tshark-based pcap analysis (overhead, goodput, retransmissions)
  packet_capture.py            tcpdump start/stop per run, offload tuning, pcap retrieval
  resource_monitor.py          background CPU/RAM sampler + energy estimate
  file_manager.py              data/output path helpers
  integrity_checker.py         SHA-256 helpers
protocols/                     per-protocol containers and the orchestration entry points
  benchmark_manager.py         host harness: captures + analyzes + logs one transfer at a time
  MQTT/clients/client_a.py     sender (1 MB chunks on file/control + file/data)
  MQTT/clients/client_b.py     receiver (reassembles chunks, verifies checksum)
  MQTT/mosquitto-broker/       broker config
  HTTP/client/http_client.py   streaming PUT client (TCP RTT, TTFB, server-side checksum)
  HTTP/server/                 Flask upload server (+ legacy nginx.conf WebDAV variant)
  CoAP/client/coap_client.py   blockwise PUT client (aiocoap)
  CoAP/server/coap_server.py   blockwise upload resource
scripts/network_chaos.sh       tc netem + tbf profile applicator (entrypoint for chaos images)
data/binary_file_generator.py  random-payload generator (edit sizes at the bottom)
output/                        bind-mounted results (see Outputs); write_csv.py lives here
runner.py                      automated protocol × profile sweep
docker-compose.yaml            manual stack
docker-compose.automated.yaml  automated stack (chaos profiles)
docker-compose.tc.yaml         legacy single-service chaos scratch file
Dockerfile                     app image (python:3.13.3-slim + iproute2 + ethtool)
```

---

## How each protocol transfers a file

| Protocol | Mechanism | Integrity | Latency metric |
|---|---|---|---|
| **MQTT** | file split into 1 MB chunks; metadata (filename/chunks/checksum/QoS) on `file/control`, chunks on `file/data`; **QoS 1 and 2 are both benchmarked** | receiver re-assembles and compares SHA-256 | publisher ACK latency (metadata) / first-chunk lag (receiver) |
| **HTTP** | streaming `PUT /upload/<file>` with `X-Checksum` header | server computes SHA-256 and returns 400 on mismatch | raw TCP RTT (bare socket) + TTFB (response hook) |
| **CoAP** | blockwise `PUT coap://coap-server/upload` (aiocoap auto-blockwise) | server compares SHA-256 in the query, returns 2.04 on match | RTT to `/.well-known/core` |

---

## Metrics collected

### Client side (`output/<proto>_measurements<suffix>.csv`)

| Metric | HTTP | MQTT | CoAP |
|---|---|---|---|
| transfer / sender / receiver time | ✓ | ✓ | ✓ |
| latency (RTT / ACK / first chunk) | ✓ (RTT + TTFB) | ✓ | ✓ |
| goodput (Mbps) | ✓ | ✓ | ✓ |
| integrity OK (bool) | ✓ | ✓ | ✓ |
| avg CPU % | ✓ | ✓ | ✓ |
| peak RAM (MB) | ✓ | ✓ | ✓ |
| energy estimate (J) | ✓ | ✓ | ✓ |
| QoS level / side | — | ✓ (qos, sender/receiver) | — |

Energy is estimated as `avg CPU fraction × TDP × duration`, where TDP defaults
to 15 W and can be overridden with the `CPU_TDP_WATTS` environment variable.

### Packet side (`output/pcap_measurements<suffix>.csv`)

| Column | Meaning |
|---|---|
| `total_packets` / `total_wire_bytes` | everything captured on the server's interface |
| `protocol_packets` / `protocol_wire_bytes` | frames matching the protocol filter (`mqtt` / `http` / `coap`) |
| `retransmissions` | TCP: `tcp.analysis.*` retransmission flags; CoAP: repeated **CON** message IDs per (MID, source) — an ACK echoing a request MID is *not* a retransmission |
| `duration_seconds` | time from first to last captured frame |
| `total_overhead_bytes` / `overhead_percentage` | captured bytes above the payload size |
| `wire_throughput_mbps` / `goodput_mbps` | wire-rate vs. payload-rate throughput |
| `packet_types` | per-type frame breakdown (JSON), e.g. PUT/200, CON/ACK, MQTT msgtypes |

---

## Prerequisites

| Tool | Why |
|---|---|
| Docker Engine 24+ with Compose v2 | containers, networking, `tc` (`docker compose version`) |
| Backend with `CAP_NET_ADMIN` | chaos profiles use Linux `tc` — Docker Desktop **WSL2** backend on Windows, or native Linux |
| Python 3.11+ (with `venv`) | host harness + data generator |
| Wireshark CLI `tshark` | pcap analysis (auto-detected on PATH or `C:\Program Files\Wireshark`) |

No host-side MQTT/HTTP/CoAP libraries are required — everything protocol-related
runs inside the containers. Chart generation additionally needs matplotlib
(`requirements-charts.txt`).

---

## Quick start

```bash
# 1. Python environment (host harness only)
python -m venv .venv
.\.venv\Scripts\activate          # bash: source .venv/bin/activate
pip install -r requirements.txt

# 2. Test payloads (edit sizes in data/binary_file_generator.py first)
cd data && python binary_file_generator.py && cd ..

# 3. Build once (both stacks share the image)
docker compose build

# 4. Start the manual stack (10 containers; capture sidecars + receiver idle)
docker compose up -d
docker compose ps

# 5. Manual benchmark: one protocol / one file / everything
.\.venv\Scripts\python protocols\benchmark_manager.py --protocol http --file binary_file_1mb.bin
.\.venv\Scripts\python protocols\benchmark_manager.py --protocol mqtt
.\.venv\Scripts\python protocols\benchmark_manager.py

# 6. Automated chaos sweep (protocols × profiles)
.\.venv\Scripts\python runner.py --profiles mobile
.\.venv\Scripts\python runner.py --protocols http mqtt --profiles good harsh satellite

# 7. Charts from the CSVs (needs matplotlib)
pip install -r requirements-charts.txt
.\.venv\Scripts\python common\charts.py
```

`benchmark_manager.py` flags: `--protocol http mqtt coap`, `--file <name.bin>`,
`--qos 1 2` (MQTT sweep), `--no-analyze` (capture only).

`runner.py` flags: `--protocols http mqtt coap`, `--profiles good iot harsh
mobile satellite` (default `mobile`).

---

## Network chaos profiles

Applied by `scripts/network_chaos.sh` (netem + tbf) on the client **and**
server/broker `eth0`:

| Profile | Delay | Loss | Rate | Models |
|---|---|---|---|---|
| `good` | 40 ms ±10 ms | 0.1% | 10 Mbit | clean Wi-Fi |
| `iot` | 200 ms ±100 ms (30%) | 2% (25%) | 512 Kbit | constrained IoT |
| `harsh` | 300 ms ±200 ms (50%) | Gilbert–Elliott (gemodel) | 256 Kbit | industrial edge |
| `mobile` | 150 ms ±150 ms (60%) | 3% (40%) | 1 Mbit | unstable cellular |
| `satellite` | 600 ms ±100 ms (20%) | 0.5% | 1 Mbit | GEO satellite |

---

## Outputs

| Path | Producer | Content |
|---|---|---|
| `output/<proto>_measurements_testing.csv` | client container | runtime metrics per transfer (manual runs) |
| `output/<proto>_measurements<proto>_<profile>.csv` | client container | runtime metrics per profile (runner) |
| `output/pcap_measurements*.csv` | host harness | tshark analysis per run |
| `output/pcap/<proto>_<file>.pcap` | capture sidecar | raw capture, one file per run |
| `output/charts/*.png` | `common/charts.py` | 14 comparison charts incl. `overview.png` |
| `uploads/` | HTTP/CoAP servers | received files (mirror of what was transferred) |

Generated artifacts (pcaps, CSVs, binaries, charts, `.venv`) are git-ignored —
the repo tracks source only.

---

## Charts

`common/charts.py` reads the CSVs and writes PNGs to `output/charts/` (default)
or `--outdir`:

- **Line charts** for size-dependent metrics (goodput, transfer time, latency,
  overhead %, bytes, packets, retransmissions) — x = file size (log scale),
  one line per protocol, MQTT QoS 1/2 as dashed/dotted lines, repeat runs
  aggregated (mean) with a shaded min–max band.
- **Grouped bar charts** for CPU/RAM/energy and the overview dashboard.

Selection: `--suffix <proto_profile>`, `--protocols`, `--metrics`,
`--file-sizes`, `--qos`, `--mqtt-side`, `--no-client`, `--no-pcap`,
`--no-overview`, `--csv-dir`, `--outdir`.
Styling: `--chart-type auto|line|bar`, `--agg mean|median|min|max`,
`--error none|minmax|std|q90`, `--x-scale`, `--y-scale`, `--dpi`, `--figsize`.

Example: `python common/charts.py --suffix http_good --metrics goodput_mbps
overhead_percentage`

---

## Reproducibility notes

- **Same payloads**: `data/*.bin` are random (`os.urandom`) — copy the generated
  files between machines rather than regenerating them.
- **Same profiles & analysis path**: pcap columns come from the same
  `common/pcap_analyzer.py` on every host; CSV suffixes encode protocol + profile.
- **Pin versions** (see TUTORIAL §7): the Dockerfile pins `python:3.13.3-slim`;
  `eclipse-mosquitto:latest` and `nicolaka/netshoot` are unpinned.
- **Compose project name = folder name**, so two copies of the repo form two
  separate stacks. The stacks no longer bind host ports, so multiple copies can
  even run simultaneously without conflicts.
- **Manual vs. profile runs**: `benchmark_manager.py` (no suffix) appends to the
  plain `pcap_measurements.csv`; `runner.py` writes suffixed files per profile.
  Delete a CSV before a fresh manual round if you want clean, comparable charts.

---

## Troubleshooting

The full symptom → fix table lives in **TUTORIAL.md §8**. Common items:

- `service '...-capture' is not running` → `docker compose up -d` first.
- pcap analysis `WinError 2` → install Wireshark / add it to PATH (auto-detected).
- `RTNETLINK answers: Operation not permitted` → Docker backend without
  NET_ADMIN; use Docker Desktop **WSL2** backend (Windows) or native Linux.
- `capture looks incomplete ...` warning → dropped frames during capture;
  re-run that transfer (offloads are already disabled and the buffer is 8 MiB).

---

## Documentation

- **docs/** — code-level deep dive: [index](docs/README.md) → architecture,
  measurement pipeline, per-protocol transfer internals, pcap analysis,
  metrics/CSV schemas, network chaos, charts, CLI reference, troubleshooting.
- **TUTORIAL.md** — step-by-step end-to-end guide: setup, manual benchmark,
  automated chaos sweep, charts, cross-machine comparability, troubleshooting,
  and a hands-free checklist.
- `python protocols/benchmark_manager.py --help`, `python runner.py --help`,
  `python common/charts.py --help` — CLI references.