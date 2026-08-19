# Tutorial — Running the MQTT / HTTP / CoAP Transfer Testbed Reproducibly

End-to-end guide to transfer benchmark files over the three IoT protocols, capture
the traffic, analyze it with tshark, and get comparable numbers on any machine.

---

## 1. What this testbed does (architecture in 30 seconds)

- Three **isolated Docker bridge networks**: `mqtt-net`, `http-net`, `coap-net`.
- Each network has a **client**, a **server** (or broker), and a **capture sidecar**.
  The capture sidecar runs in the *server's network namespace*, so it sees the
  traffic between client and server exactly as the server does.
- A **host-side harness** (`protocols/benchmark_manager.py`) drives one transfer at a
  time: it starts `tcpdump` in the sidecar, runs the transfer inside the client
  container, stops `tcpdump`, then analyzes the resulting `.pcap` with `tshark` and
  appends a row to a CSV.

Manual stack (baseline, `docker-compose.yaml`) vs. automated stack
(`docker-compose.automated.yaml`):

| | docker-compose.yaml | docker-compose.automated.yaml |
|---|---|---|
| Network model | none (clean baseline) | `tc` chaos applied inside every container via `scripts/network_chaos.sh` |
| Servers/clients | servers auto-run, clients idle | ALL containers default to"apply tc then stay idle" |
| Driven by | `protocols/benchmark_manager.py` | `runner.py` (builds, up, waits, drives, tears down) |
| Profiles | — | `good`, `iot`, `harsh`, `mobile`, `satellite` |

---

## 2. Prerequisites

| Tool | Why | Check with |
|---|---|---|
| Docker Engine 24+ with Compose v2 | containers / networking / `tc` | `docker --version`, `docker compose version` |
| Backend that supports `CAP_NET_ADMIN` | the chaos profiles use Linux `tc` (netem/tbf) | Docker Desktop **WSL2** backend on Windows, or native Linux |
| Python 3.11+ (with `venv`) | host harness + data generator | `python --version` |
| Wireshark CLI `tshark` | pcap analysis | `tshark --version` (auto-detected: PATH or `C:\Program Files\Wireshark`) |

No host-side MQTT/HTTP/CoAP libraries are needed — everything protocol-related runs
inside the containers.

> Windows note: use Docker Desktop with the **WSL2** backend, not Hyper-V, so the
> `tc` chaos profiles work inside containers.

---

## 3. Reproducible setup

### 3.1 Get the code

```bash
# either clone ...
git clone <your-repo-url>
cd <folder>
# ... or copy the whole folder as-is (name = docker compose project name).
```

### 3.2 Create the Python environment (host harness only)

```bash
python -m venv .venv
# PowerShell:  .\.venv\Scripts\activate
# bash:        source .venv/bin/activate
pip install -r requirements.txt
```

Verify: `python -c "import flask, paho.mqtt, aiocoap"` (no error = OK).
These are only for the harness; the containers install their own copy via the Dockerfile.

### 3.3 Generate the test payloads

```bash
cd data
python binary_file_generator.py
cd ..
```

Edit `data/binary_file_generator.py` to change sizes (default: 100 MB and 200 MB). The
harness auto-discovers every `*.bin` in `data/`. Alternatively drop any `*.bin` files there.

### 3.4 (Once) Build the images

The `nicolaka/netshoot` capture images are pulled automatically. Your app image is
built from the Dockerfile; the manual and automated stacks share the same image
(same project, same services), so one build covers both:

```bash
docker compose build
```

(`runner.py` also rebuilds automatically when it starts, so a manual build is only
needed for the manual workflow.)

### 3.5 Start the manual stack

```bash
docker compose up -d
docker compose ps
```

Wait until every container shows `Up`. Then sanity-check:

```bash
# each capture sidecar must see traffic on its server's eth0:
docker compose exec mqtt-capture  sh -c "grep -c eth0 /proc/net/dev"   # 1
docker compose exec http-capture  sh -c "grep -c eth0 /proc/net/dev"   # 1
docker compose exec coap-capture  sh -c "grep -c eth0 /proc/net/dev"   # 1
# the MQTT receiver must be connected:
docker logs mqtt-client-b-1           # "Connected to broker. Listening for files..."
```

---

## 4. Manual (baseline) benchmark

Run from the project root with the venv active.

```bash
# one protocol, one file (with pcap analysis)
.venv\Scripts\python protocols\benchmark_manager.py --protocol http --file binary_file_1mb.bin

# one protocol, all files
.venv\Scripts\python protocols\benchmark_manager.py --protocol mqtt

# everything, all files (MQTT sweeps QoS 1 and 2)
.venv\Scripts\python protocols\benchmark_manager.py

# capture only — no tshark analysis (fast smoke test)
.venv\Scripts\python protocols\benchmark_manager.py --protocol coap --file binary_file_1mb.bin --no-analyze
```

CLI reference (`python protocols/benchmark_manager.py --help`):

| Flag | Effect |
|---|---|
| `--protocol mqtt http coap` | which protocols to run (default: all) |
| `--file <name.bin>` | single file instead of all `data/*.bin` |
| `--qos 1 2` | MQTT QoS sweep (default `1 2`; ignored for http/coap) |
| `--no-analyze` | capture pcaps but skip the tshark analysis step |

### What you get

Per transfer, the console prints transfer stats (from the client) and then the
`PCAP ANALYSIS` block (from tshark):

```
--- Traffic ---      file size / captured packets+bytes / protocol packets+bytes
--- Overhead ---     total-overhead bytes + % vs. payload
--- Performance ---  duration, goodput Mbps, wire throughput Mbps, retransmissions
--- Packet types --- per-type frame counts (PUT/200, CON/ACK, msgtype, ...)
```

Files written:

| Path | Producer | Content |
|---|---|---|
| `output/runs/<run_id>/<proto>_measurements.csv` | client container | runtime metrics (transfer time, RTT/TTFB, goodput, CPU/RAM, energy, integrity) |
| `output/runs/<run_id>/pcap_measurements.csv` | host harness | tshark analysis (packet counts, overhead, goodput, retransmissions, packet types) |
| `output/runs/<run_id>/pcap/<proto>_<file>.pcap` | capture sidecar | raw capture, one file per transfer |
| `output/runs/<run_id>/run.json` | harness | manifest (protocol, profile, files, tool versions) |

Each manual `benchmark_manager.py` invocation creates a fresh run directory
(e.g. `output/runs/20260818T201455_http/`). Inspect results:

```bash
# PowerShell
Import-Csv output\runs\<run_id>\http_measurements.csv
Import-Csv output\runs\<run_id>\pcap_measurements.csv
# python (run registry)
python -c "import common.runs as r; print(r.load_csv('output', '<run_id>', 'http'))"
```

---

## 5. Automated (network chaos) benchmark

`runner.py` automates the whole loop per (protocol × profile):
build → `docker compose up -d` (that protocol only) → wait until reachable →
drive every transfer → `docker compose down -v`.

```bash
# all protocols, one profile
.venv\Scripts\python runner.py --profiles mobile

# targeted runs
.venv\Scripts\python runner.py --protocols http mqtt --profiles good harsh satellite

# full sweep
.venv\Scripts\python runner.py --profiles good iot harsh mobile satellite
```

Network profiles (`scripts/network_chaos.sh`), applied on the client **and** server/ broker's `eth0`:

| Profile | Delay | Loss | Rate | Models |
|---|---|---|---|---|
| `good` | 40ms | 0.1% | 10 Mbit | clean Wi-Fi |
| `iot` | 200ms | 2% | 512 Kbit | constrained IoT |
| `harsh` | 300ms | gemodel | 256 Kbit | industrial edge |
| `mobile` | 150ms± | 3% | 1 Mbit | unstable cellular |
| `satellite` | 600ms | 0.5% | 1 Mbit | GEO satellite |

Because tc is applied inside the containers, each run is reproducible across hosts —
no real network needed.

Each (protocol × profile) writes to its own immutable run directory:

```bash
output/runs/20260818T201455_mqtt_good/
output/runs/20260818T201455_http_good/
...
```

> `docker compose down -v` in `runner.py` removes **named volumes** only. Your
> `output/` is a **bind mount**, so runs survive.

---

## 6. Optional: generate charts from the CSVs

`common/charts.py` turns the result CSVs into PNG comparison charts. It needs
matplotlib, which is **not** in the core `requirements.txt` (charts run on the
host only):

```bash
pip install -r requirements-charts.txt   # adds matplotlib

python common/charts.py --run <run_id>   # charts ONE run's data into <run>/charts/
python common/charts.py                   # legacy: reads ./output flat files
```

### Chart types (auto-selected, overridable)

- **Line charts** — for metrics that scale with file size (goodput, transfer
  time, latency, overhead %, bytes, packets, retransmissions). File size is on
  the x axis (log scale by default, since sizes span 0.25→50 MB), one line per
  protocol; MQTT QoS 1/2 are dashed/dotted lines on the same protocol color.
  Repeat runs are aggregated (mean by default) with a shaded min–max band.
- **Grouped bar charts** — for size-invariant metrics (CPU, RAM, energy) and for
  the combined `overview.png` dashboard. Protocols are the bar groups; QoS is
  distinguished by hatching.

### Options (`python common/charts.py --help`)

Selection:

| Flag | Effect |
|---|---|
| `--run <run_id>` | chart one run directory under `--runs-dir` (preferred; overrides the legacy flags) |
| `--runs-dir <dir>` | directory containing the `runs/` tree (default `./output`) |
| `--suffix _testing` | legacy: pick a measurement set (default: `MEASUREMENT_SUFFIX` env, then `_testing`, then plain) |
| `--csv-dir <dir>` | legacy: where the flat CSVs live (default `./output`) |
| `--outdir <dir>` | where the PNGs are written (default `<run>/charts` with `--run`, else `output/charts`) |
| `--protocols http mqtt` | subset of protocols to plot |
| `--metrics goodput_mbps overhead_percentage` | only these metrics (default: all) |
| `--file-sizes 1 5 20 50` | only these file sizes in MB |
| `--qos 1 2` | which MQTT QoS levels to include (default: both) |
| `--mqtt-side sender\|receiver\|both` | which MQTT row side to use (default: sender) |
| `--no-client` / `--no-pcap` | skip the client-runtime or the pcap-analysis charts |
| `--no-overview` | skip the combined dashboard |

Styling:

| Flag | Effect |
|---|---|
| `--chart-type auto\|line\|bar` | force line or bar charts, or auto per metric (default auto) |
| `--agg mean\|median\|min\|max` | how to combine repeat runs (default mean) |
| `--error none\|minmax\|std\|q90` | error bars / shaded band (default minmax) |
| `--x-scale auto\|linear\|log` | x axis scale (default: log for line charts) |
| `--y-scale linear\|log` | y axis scale (default linear) |
| `--dpi 150` | PNG resolution |
| `--figsize 10x5` | figure size (default auto) |

Examples:

```bash
python common/charts.py --run 20260818T201455_mqtt_harsh
python common/charts.py --run <run_id> --metrics goodput_mbps overhead_percentage
python common/charts.py --run <run_id> --file-sizes 1 5 20 50 --qos 2
python common/charts.py --run <run_id> --chart-type bar --error none
```

What it produces (14 PNGs by default): `client_goodput_mbps`,
`client_transfer_time`, `client_latency`, `client_avg_cpu_pct`,
`client_peak_ram_mb`, `client_energy_j` from the client-runtime CSVs (MQTT uses
its sender rows), `pcap_goodput_mbps`, `pcap_wire_throughput_mbps`,
`pcap_overhead_percentage`, `pcap_total_overhead_bytes`, `pcap_total_wire_bytes`,
`pcap_retransmissions`, `pcap_total_packets` from `pcap_measurements.csv`, and
`overview.png` dashboard — all inside `output/runs/<run_id>/charts/`.

> **Note:** `--run <run_id>` charts exactly one run — no cross-profile mixing, no
> suffix guessing. Old flat CSVs are archived to `output/legacy/`; use the legacy
> `--csv-dir`/`--suffix` flags only for that historical data.

---

## 7. Making results comparable across machines

1. **Pin versions.** Record in a `versions.txt`:
   `python --version`, `docker --version`, `docker compose version`, `tshark --version`
   (the Dockerfile pins `python:3.13.3-slim`; `eclipse-mosquitto:latest` and
   `nicolaka/netshoot` are unpinned — pin them with a digest/tag for strict reproducibility).
2. **Normalize payloads.** Use the same `data/*.bin` set everywhere
   (`binary_file_generator.py` must produce identical files — it uses `os.urandom`,
   so copy the generated files, don't regenerate them on each machine).
3. **Use the same profiles and files.** Each run is immutable and self-describing
   (`run.json` + the `run_id`/`network_profile` columns), so keep files fixed and
   compare by run id.
4. **Same analysis path.** The pcap measurement columns come from the same
   `common/pcap_analyzer.py` on every host.

Naming collision note (the reason there is a `- Copy` folder): the compose **project
name is the folder name**, so two copies of the repo create two separate stacks.
Because the manual stack no longer binds host ports (1883 / 8080 / 5683), both stacks
can even run **simultaneously** without conflicts.

---

## 8. Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| `service '...-capture' is not running` | stack is down. `docker compose up -d` first |
| `pcap analysis failed: [WinError 2] The system cannot find the file specified` | host `tshark` not on PATH. Install Wireshark; `common/pcap_analyzer.py` now auto-detects `C:\Program Files\Wireshark\tshark.exe` |
| `tshark: Some fields aren't valid: coap.messageid` | old field name; analyzer now uses `coap.mid` |
| `ValueError: dict contains fields not in fieldnames: 'packet_types'` | needs the fixed `write_to_file_pcap` (adds `packet_types` as JSON) |
| `tcpdump never started writing ...` | capture sidecar isn't ready / netshoot not pulled. Re-run `docker compose up -d` and check `docker compose ps` |
| `Bind for 0.0.0.0:1883 failed: port is already allocated` | another stack still binds host ports. Use the updated compose (no host bindings), or change the left side to e.g. `11883:1883` |
| `tc` errors like `RTNETLINK answers: Operation not permitted` | Docker backend not giving NET_ADMIN. Switch to Docker Desktop **WSL2** backend (Windows) or native Linux |
| transfer succeeds but no `CON/ACK` in pcap | wrong pcap read back (pcaps live at `output/runs/<run_id>/pcap/`; CSVs at `output/runs/<run_id>/`) |

---

## 9. End-to-end checklist (hands-free run on a fresh machine)

```bash
git clone <repo> && cd <repo>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd data && python binary_file_generator.py && cd ..
docker compose build
docker compose up -d
docker compose ps                       # all 10 containers Up
.venv\Scripts\python protocols\benchmark_manager.py --protocol http --file binary_file_1mb.bin
# expect: Success! + PCAP ANALYSIS block + INTEGRITY OK
#         run dir: output/runs/<timestamp>_http/ (run.json + CSVs + pcap/)
.venv\Scripts\python runner.py --protocols http --profiles good mobile
# expect: one immutable run dir per (protocol × profile) under output/runs/
```