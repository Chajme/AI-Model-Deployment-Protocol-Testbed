# Known Issues & Findings

Issues discovered while adding and verifying the AMQP / gRPC / LwM2M protocol
stacks (Aug 2026). Items marked OPEN need future work; items marked FIXED are
recorded here for traceability. Evidence references refer to run
`output/runs/20260825T183032_mqtt/` (all six protocols, 250 KB + 1 MB, clean
network) unless noted otherwise.

---

## OPEN-1: pcap time-derived metrics are unreliable for small files

**Severity:** high (misleading chart data) · **Affects:** all protocols
(pre-existing) · **Status:** OPEN

`analyze_pcap()` computes `duration_seconds` as the timestamp of the last
captured frame minus 0. The benchmark clients each `time.sleep(5)` at startup
(waiting for their broker/server), and that sleep happens *inside* the capture
window. Whether the 5 s lands in the pcap depends on a race between the
detached `docker compose exec tcpdump` attaching and the client container
starting. Result: pcap `duration_seconds`, `goodput_mbps`, and
`wire_throughput_mbps` are essentially random for small/fast transfers.

**Evidence (run 20260825T183032_mqtt, pcap_measurements.csv):**

| row | pcap duration | pcap goodput | client-measured goodput |
|---|---|---|---|
| mqtt 250kb | 5.20 s | 0.39 Mbps | 259.9 Mbps |
| http 250kb | 5.11 s | 0.40 Mbps | 90.7 Mbps |
| coap 250kb | 5.03 s | 0.41 Mbps | 10.6 Mbps |
| amqp 250kb | 0.09 s | 23.4 Mbps | 270.6 Mbps |
| amqp 1mb | 5.75 s | 1.46 Mbps | 587.9 Mbps |

The 250 KB rows split into ~5.0 s (sleep captured) vs ~0.09 s (attach raced
past the sleep) with no in-between — the signature of the race.

**Suggested fix:** compute duration from the first to the last
*protocol-filtered* frame (the `PROTOCOL_CONFIG[protocol]["filter"]` display
filter already exists) instead of the first captured frame; idle startup and
ARP/ICMPv6 noise then drop out of the window. Byte-derived metrics (overhead,
wire bytes, retransmissions, packet counts) are unaffected and trustworthy.

---

## OPEN-2: CPU/energy samples read 0 for fast small transfers

**Severity:** low · **Affects:** every protocol using `ResourceMonitor`
**Status:** OPEN

`ResourceMonitor(sample_interval=0.01)` over a transfer window of tens of
milliseconds collects zero or one sample; rows then record `0.00%` CPU and
`0.0000` J (e.g. all four AMQP rows and grpc-250kb in the reference run).
The numbers are not wrong (little CPU over 10 ms rounds to zero) but the CPU/
RAM/energy bar panels under-represent fast protocols.

**Suggested fix:** either record the sample count and flag rows below a
minimum (say <5 samples) as unreliable in the CSV, or use a fixed minimum
monitoring window (keep sampling for e.g. 200 ms after the transfer).

---

## OPEN-3: servers silently benchmark the wrong network profile (pre-existing)

**Severity:** high for chaos sweeps · **Affects:** `http-server`, `coap-server`
**Status:** OPEN (deliberately not fixed — out of agreed scope)

`docker-compose.automated.yaml` passes `NETWORK_PROFILE` to client services
but not to `http-server`/`coap-server`; `scripts/network_chaos.sh` then
defaults to the `iot` profile regardless of the sweep profile chosen.
`docs/network-chaos.md` states the same profile should apply on both ends.
The new `grpc-server`/`lwm2m-server` had the same flaw and **were** fixed
(their LwM2M goodput tripled once fixed). Any historical http/coap
chaos-sweep numbers are client-good/server-iot composites.

**Suggested fix:** add `- NETWORK_PROFILE=${NETWORK_PROFILE}` to both
services' environment in `docker-compose.automated.yaml` (one line each).

---

## OPEN-4: LwM2M large-file sweeps are RTT-bound and extremely slow

**Severity:** medium (operational) · **Affects:** lwm2m under latency profiles
**Status:** OPEN (inherent protocol behavior, needs sweep-time budgeting)

LwM2M pulls models with CoAP blockwise (~1.4 KB per GET). Under the `good`
profile (40 ms RTT) a 1 MB model takes ~86 s and a 50 MB model would take
>60 minutes; harsher profiles scale worse. A full-size LwM2M sweep can take
hours.

**Suggested fix:** gate payload sizes per profile (e.g. LwM2M only runs
250 KB/1 MB on `iot` and below), or raise the block size (aiocoap supports
up to 1024-byte Block2 by default; a `BLOCKWISE` tuning or HTTP-fallback mode
would change the wire profile and should be a deliberate choice).

---

## OPEN-5: merging runs for combined charts silently drops pcap rows

**Severity:** low (tooling) · **Affects:** legacy flat `--csv-dir` chart mode
**Status:** OPEN

Every run writes its own `pcap_measurements.csv`; copying several runs'
CSVs into one flat directory for a combined chart overwrites the file (same
filename), leaving pcap panels with only the last-copied protocol's rows.
Client-side CSVs are protocol-prefixed and merge fine.

**Suggested fix:** document a merge snippet (header + all bodies), or teach
`charts.py --runs-dir` a multi-run mode that concatenates pcap CSVs from
several run dirs.

---

## FIXED-1: sender/receiver rows averaged into one series

Charts' `_collect()` only filtered MQTT by row side; AMQP/gRPC CSVs contain
sender *and* receiver rows per transfer, so client charts averaged
incompatible measurements (gRPC 250 KB: sender 105 Mbps vs receiver
997 Mbps → nonsense ~550 Mbps midpoint). Fixed by generalizing the side
filter to any protocol with a `side` column plus a `--side auto` default
(sender rows when present, else the only side recorded — LwM2M logs
`side=client`). Verified: exactly one value per size per protocol.

## FIXED-2: pcap x-axis rendered "250 MB" for the 250 KB file

`_pcap_label` derived labels from filenames ("250kb"); `_label_sort_key`
extracted 250 → x tick "250 MB", sorted after 50 MB. Fixed by deriving pcap
labels from `file_size_bytes` (MB format).

## FIXED-3: MQTT QoS split sizes into extra x categories

`_client_label` appended `| qos N` to x labels, so MQTT qos1/qos2 got
separate x positions instead of grouped bars at the same size. Fixed
(labels are size-only; the `(protocol, qos)` series key already separates
QoS).

## FIXED-4: overview panels had no legend and zero-valued panels got negative axes

`_make_overview` never called `ax.legend()` (colors were unidentifiable) and
all-zero metrics (retransmissions on a clean network) produced a ±0.04 axis.
Fixed: per-panel legend when >1 series, `ax.set_ylim(bottom=0)` in
`_draw_bars`.

## FIXED-5: negative pcap overhead from truncated captures

Two stacked causes, both fixed earlier in August 2026:
1. `OFFLOAD_CONTAINERS` lacked `grpc` (client-side TSO/GSO produced 2950 B
   super-frames instead of MTU segments).
2. `stop_capture_run` SIGTERM'd tcpdump immediately when the client exited,
   losing the transfer tail (~5% of bytes; e.g. 242,921 B captured vs
   272,545 B with a 2 s settle). Fixed with `CAPTURE_SETTLE_SECONDS = 2.0`
   and a 32 MiB tcpdump buffer.

## FIXED-6: new protocol servers ran the default `iot` chaos profile

`grpc-server`/`lwm2m-server` lacked `NETWORK_PROFILE` env (see OPEN-3 —
same root cause, fixed for the new services only per scope decision).

---

## Non-issues (documented so they are not "fixed" by mistake)

- **Broker-topology overhead ≈114% is correct.** The capture sidecar shares
  the broker's netns, so MQTT/AMQP pcaps contain both data legs (publish +
  delivery). AMQP 114.76% vs MQTT baseline 114.4% on 50 MB — statistically
  identical. See docs/protocol-transfers.md.
- **LwM2M ≈ CoAP overhead (~22%) is expected** — same UDP/blockwise wire
  mechanics plus management-layer messages (registration, state reports).
- **Sender vs receiver goodput differ by 5–10x** (e.g. gRPC 84.7 vs
  1223.9 Mbps at 250 KB): the receiver's window starts at first-chunk
  arrival, the sender's at stream start. Both are "correct"; charts use the
  sender side by default (`--side auto`).
- **paho-mqtt DeprecationWarning** (Callback API v1) at every MQTT client
  start — cosmetic; migrating to paho 2.x callback API is a small chore.
