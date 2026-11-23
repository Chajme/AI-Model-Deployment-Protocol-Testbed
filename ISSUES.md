# Known Issues & Findings

Issues discovered and fixed while extending and auditing the testbed
(Aug–Nov 2026). Items marked OPEN need future work; items marked FIXED are
recorded here for traceability. Note: the evidence run cited by the August
entries (`output/runs/20260825T183032_mqtt/`) predates the run-directory
history of the current checkout and is no longer present; later evidence
references runs that do exist.

> **Legacy boundary (tag `analysis-v1-legacy`).** Every run produced up to that
> tag used the legacy shaping, in which the MQTT/AMQP device link
> (broker → `client-b`) was not shaped (see OPEN-5). Those runs live in
> `output/runs-legacy-v1/` and must never be mixed with v2 runs in one table.
> The v2 changes are tracked in `docs/protocol-analysis-completion-plan.md`.

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

## OPEN-5: the six protocols run under two different network scenarios

**Severity:** high for cross-protocol chaos comparisons · **Affects:**
MQTT/AMQP vs HTTP/CoAP/gRPC/LwM2M under any chaos profile
**Status:** OPEN (design decided, implementation deferred)

`tc` runs on all clients and on the http/coap/grpc/lwm2m servers, but the
brokers are stock images (`eclipse-mosquitto`, `rabbitmq`) and are never
shaped. Consequences:

- **MQTT/AMQP** face one constrained link (the sender's egress). The
  broker→receiver delivery leg is clean, and the sender's PUBACK/confirm
  return path is clean too (it leaves the unshaped broker).
- **HTTP/CoAP/gRPC/LwM2M** face shaping on both ends, so their ACK/response
  path is also delayed and lossy — effectively double the delay/loss exposure
  per round trip compared to the broker protocols.

Evidence: under `harsh` (256 Kbit cap) the MQTT sender pushed 250 KB at
0.101 Mbps while the receiver recorded the same bytes at 1724 Mbps
(`20260901T175347_mqtt_harsh`) — only possible on an unshaped delivery leg.
So a "same profile name" means a harsher network for the direct protocols
than for the broker protocols, and cross-protocol absolute numbers under
chaos conflate protocol efficiency with scenario difference.

**Agreed target design (deferred, "single constrained link" model):** the
edge device's access link is the only constrained link; the backend sits in
a good network. Concretely: unshape `mqtt-client-b`, `amqp-client-b`,
`http-server`, `coap-server`, `grpc-server`; keep `tc` on all senders
(clients) and on `lwm2m-server` (it is the data source of a download —
unshaping it would leave the transfer unconstrained, since only egress can
be shaped). Known limitation to document: for upload protocols the
constrained link is modeled in the data direction only; the return direction
would need per-destination `tc` filters on the broker/server side.

**Impact when implemented:** http/coap/grpc chaos numbers will get faster
(clean ACK path); all pre-change http/coap/grpc chaos CSVs are a *harsher
legacy scenario* and must not be mixed with post-change results in one chart.

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
   and a 32 MiB tcpdump buffer (`TCPDUMP_BUFFER_KB = 32768`).

## FIXED-6: new protocol servers ran the default `iot` chaos profile

`grpc-server`/`lwm2m-server` lacked `NETWORK_PROFILE` env (see OPEN-3 —
same root cause, fixed for the new services only per scope decision).

## FIXED-7: merging runs for combined charts silently dropped pcap rows

Every run writes its own `pcap_measurements.csv`; copying several runs' CSVs
into one flat directory for a combined chart overwrote the file (same
filename), leaving pcap panels with only the last-copied protocol's rows.
Fixed by adding `charts.py --runs <id> <id> ...`: client CSVs (already
protocol-prefixed) and every listed run's pcap CSV are read and concatenated,
so per-protocol runs of one sweep chart together. `--outdir` defaults to
`output/charts` in multi-run mode; row-level `run_id`/`network_profile`
columns keep the merged data self-describing.

## FIXED-8: MQTT never recorded CPU / RAM / energy

MQTT was the only protocol with no resource sampling: `client_a` (sender) and
`client_b` (receiver) left the `avg_cpu_usage`/`peak_ram_usage`/`energy_est`
columns empty even though `write_to_file_mqtt` declared them. Both clients now
wrap the transfer in `ResourceMonitor` (sender: before the control message to
after the last chunk; receiver: metadata arrival to final chunk), and
`common/charts.py` maps `mqtt` into the CPU/RAM/energy panels. All six protocols
are now consistent client-side.

## FIXED-9 (was OPEN-1): pcap time-derived metrics were unreliable for small files

`analyze_pcap()` computed `duration_seconds` from the *first captured frame*
to the last — the benchmark clients each `time.sleep(5)` at startup *inside*
the capture window, so idle noise anchored the window start and
`duration/goodput/wire_throughput` were essentially random for small transfers
(250 KB rows split into ~5 s vs ~0.09 s with no in-between).

**Fix (Nov 2026):** duration is now computed from the first to the last frame
matching a per-protocol *window filter* (`PROTOCOL_CONFIG[protocol].filter`,
with an optional `duration_filter` override), falling back to the all-frames
span only when nothing matches. Plain protocol filters work for MQTT/AMQP
(dissected per message) and CoAP/LwM2M/gRPC (blockwise and HTTP/2 frames are
all dissected), but HTTP needed a dedicated
`duration_filter: "http or (tcp.len > 0 and tcp.port == 8000)"`: a streamed
chunked PUT is dissected as a *single* http request frame while the body
travels as plain TCP segments, so the plain `http` filter collapses the
window to one frame. The wider filter also anchors the window at the first
uploaded byte and excludes the bare-socket latency probe (SYN carries no
payload).

**Verification (re-analysis of existing pcaps, byte metrics unchanged):**

| pcap (250 KB) | old duration | new duration | client-side reference |
|---|---|---|---|
| mqtt `20260903T162303_mqtt_mobile` | 16.52 s | 9.71 s | sender_duration 9.67 s |
| http `20260903T081214_http_mobile` | 10.04 s | 3.07 s | time_to_transfer 3.61 s (gap = TCP connect) |
| grpc `20260913T090042_grpc_good` | 6.53 s | 0.65 s | sender_duration 0.44 s (gap = Ping RPC) |

A fresh end-to-end sweep (run `20261120T135139_http_good`, 250 KB–50 MB)
confirms pcap durations now track the client-side `time_to_transfer` within
~0.1 s at every size (e.g. 50 MB: 58.44 s pcap vs 58.54 s client).

## FIXED-10 (was OPEN-2): CPU/energy samples read 0 for fast small transfers

`ResourceMonitor(sample_interval=0.01)` over a transfer window of tens of
milliseconds collected zero or one sample; rows then recorded `0.00%` CPU and
`0.0000` J. Fixed (Nov 2026) with both halves of the earlier suggestion:
`ResourceMonitor.stop()` now enforces a 0.2 s minimum sampling window
(`MIN_WINDOW_SECONDS`) so short transfers still collect a handful of samples,
and every client CSV schema gained a `sample_count` column recording how many
samples back the averages — rows with very few samples are low-confidence.
`stop()` is also idempotent now (a second call, e.g. from a `finally` block,
returns the cached stats instead of re-stopping). Confirmed in run
`20261120T135139_http_good`: `sample_count` 70–5708 per row and CPU/energy
non-zero even for the 250 KB transfer.

## FIXED-11 (was OPEN-3): servers silently benchmarked the wrong network profile

`docker-compose.automated.yaml` originally passed `NETWORK_PROFILE` to client
services but not to `http-server`/`coap-server`; `scripts/network_chaos.sh`
then defaulted to the `iot` profile regardless of the sweep profile chosen.
The fix (adding `- NETWORK_PROFILE=${NETWORK_PROFILE}` to both services)
was applied in the compose file before this audit; the entry is retained
here because the item had been left marked OPEN after the fix. See OPEN-5
for the scenario asymmetry that remains.

## FIXED-12: MQTT/AMQP sender duration included the metadata-ACK wait

The MQTT sender opened its timed window, published the tiny metadata message,
then blocked up to **10 s** waiting for the broker's PUBACK before sending
any chunk — a lost ACK would silently inject up to 10 s of dead time into
`sender_duration` and crash goodput (no such event occurred in recorded
runs; worst observed metadata latency was 1.78 s under `harsh`). Fixed
(Nov 2026): the timer starts only when chunk transmission begins; the
metadata round trip is recorded separately in `latency`. The AMQP sender was
aligned the same way (its metadata publish+confirm is control traffic, kept
out of the chunk-transmission window).

**Comparability note:** pre-change MQTT/AMQP rows include the metadata
round trip in `sender_duration` (bounded by one broker RTT); post-change
rows do not.

## FIXED-13: single-chunk receiver rows wrote meaningless duration/goodput

For a file that fits in one 1 MB chunk, the receiver window "first chunk
arrival → last chunk arrival" is empty, producing `receiver_duration ≈ 0.00`
and four-digit fake goodput (e.g. 1724 Mbps under a 256 Kbit profile — see
the OPEN-5 evidence). Fixed (Nov 2026): MQTT/AMQP receivers now record
`X` (not applicable) for `receiver_duration`/`goodput_mbps` on single-chunk
transfers; the first-chunk lag, integrity, CPU/RAM/energy and the sender
rows remain meaningful.

## FIXED-14: dead code and vestigial plumbing (Nov 2026 cleanup)

- `docker-compose.tc.yaml` (legacy single-service chaos scratch file)
  deleted; README references removed.
- `pcap_analyzer.resolve_tshark()` removed (never called; `run_tshark`
  already auto-falls back to the netshoot container).
- Stale `__main__` demo blocks in `packet_capture.py`/`pcap_analyzer.py`
  (referenced the pre-run-layout flat `output/pcap/` path) removed.
- Unused `./output/pcap:/pcap` capture-sidecar volume mounts removed from
  both compose files (tcpdump writes to container-local `/tmp`; the harness
  copies pcaps out with `docker compose cp`).
- `MEASUREMENT_SUFFIX` removed everywhere (compose files, `runner.py`,
  `runs.py` manifest keys) — it was never read at runtime; per-profile
  separation has been via immutable run directories since the run-layout
  change.
- `lwm2m_client.py`: unused `save_file` import removed; local duplicate
  `sha256_file()` replaced by `common.integrity_checker.compute_sha256_file`.
- `resource_monitor.py` docstring corrected (default `sample_interval` is
  0.05, not 0.1).

Kept deliberately: `runs.find_runs`/`load_csv` (unused in-repo but
documented as the public run-reading API) and charts' legacy
`--csv-dir/--suffix` fallback.

---

## Non-issues (documented so they are not "fixed" by mistake)

- **Broker-topology overhead ≈114% is correct.** The capture sidecar shares
  the broker's netns, so MQTT/AMQP pcaps contain both data legs (publish +
  delivery). AMQP 114.76% vs MQTT baseline 114.4% on 50 MB — statistically
  identical. See docs/protocol-transfers.md.
- **LwM2M ≈ CoAP overhead (~22%) is expected** — same UDP/blockwise wire
  mechanics plus management-layer messages (registration, state reports).
- **Sender vs receiver goodput differ** (e.g. gRPC 84.7 vs 1223.9 Mbps at
  250 KB clean): the receiver's window starts at first-chunk arrival, the
  sender's at stream start. Both are "correct"; charts use the sender side
  by default (`--side auto`).
- **Per-protocol `latency` columns measure different round trips**
  (HTTP: fresh TCP handshake; MQTT: metadata PUBACK, QoS 2 being a
  multi-round exchange; AMQP: publish confirm; gRPC: Ping unary RPC on an
  open channel; CoAP: discovery GET; LwM2M: registration). They are a rough
  "protocol round-trip responsiveness" comparison, not an apples-to-apples
  one — documented in docs/metrics-schema.md.
- **Peak RAM reflects implementation buffering, not a protocol limit.**
  CoAP/LwM2M load the whole file into RAM because aiocoap's simple API
  requires the full representation in memory (auto-blockwise slices it
  afterwards); HTTP/gRPC/MQTT/AMQP stream from disk. A hand-rolled blockwise
  state machine could avoid it with an identical wire profile. Documented
  in docs/metrics-schema.md.
- **paho-mqtt DeprecationWarning** (Callback API v1) at every MQTT client
  start — cosmetic; migrating to paho 2.x callback API is a small chore.
