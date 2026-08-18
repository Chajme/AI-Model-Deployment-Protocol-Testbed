# Troubleshooting

Each entry lists the symptom, the root cause (with a code pointer), and the fix.
This page complements TUTORIAL.md §8 with deeper root-cause detail.

---

## Capture & capture integrity

### `service '...-capture' is not running`

`docker compose exec` can't find the sidecar. The stack isn't up, or the
service exited (e.g. netshoot image not pulled yet).

Fix: `docker compose up -d` then `docker compose ps`. Re-pull the netshoot image
if needed (`docker compose pull`).

### `WARNING: capture looks incomplete ... (~N B missing)`

`analyze_pcap` saw `total_wire_bytes < file_size_bytes` (common/pcap_analyzer.py
Pass D). Frames were dropped while capturing — the overhead/goodput numbers for
that run are unreliable.

Causes:
- tcpdump kernel buffer overflow on a burst. The harness already uses
  `-B 8192` (`TCPDUMP_BUFFER_KB`, common/packet_capture.py) and deliberately
  avoids `-U` packet-buffered mode — if you changed either, revert.
- Host I/O stall (large files, Windows/WSL2 disk backpressure).
- Under lossy chaos profiles a *legitimately* smaller capture is possible; the
  warning is informational then.

Fix: re-run that transfer. If it repeats on large files, watch the host disk
and increase `TCPDUMP_BUFFER_KB`.

### Transfer succeeds but pcap has no protocol frames (e.g. no `CON/ACK`)

The analyzed file isn't the one captured, or the capture never started.

- pcaps are written to `output/pcap/` on the host (copied from the sidecar's
  `/tmp` by `stop_capture_run`). Confirm the timestamp/size.
- Check the analyzer's filter matches the traffic (`-Y mqtt`/`http`/`coap`) —
  CoAP is dissected on UDP 5683 by default; the server binds `0.0.0.0:5683`.

### `pcap analysis failed: [WinError 2] The system cannot find the file specified`

Host `tshark` not found. `resolve_tshark()` checks PATH then
`C:\Program Files\Wireshark\tshark.exe` etc. (common/pcap_analyzer.py).

Fix: install Wireshark, or add its folder to PATH.

### `tshark: Some fields aren't valid: coap.messageid`

Stale field name in a modified analyzer. Current code uses `coap.mid`
(common/pcap_analyzer.py). Update any copy of the analyzer.

---

## Networking / `tc`

### `RTNETLINK answers: Operation not permitted` (tc)

The container lacks `CAP_NET_ADMIN`, or the Docker backend doesn't provide it.
Docker Desktop **Hyper-V** backend on Windows doesn't give containers the
capabilities the Linux `tc` needs.

Fix: switch Docker Desktop to the **WSL2** backend (or run natively on Linux).
Verify with `docker info | grep -i network` → the driver must be `overlay2` /
WSL2-based.

### `Bind for 0.0.0.0:1883 failed: port is already allocated`

An old/other stack still binds host ports. The current compose files do **not**
publish ports (all traffic is inside the bridge networks). Remove the old stack
(`docker compose down`) or update any leftover `ports:` mapping.

### CoAP transfers take a very long time under chaos

By design: UDP + blockwise + `tc`. E.g. 50 MB at `harsh` (256 kbit, 300 ms,
Gilbert–Elliott loss) ≈ tens of minutes, with CoAP CON retransmissions under
loss. The retransmission counter (repeated CON MIDs) will reflect it — check
`pcap_measurements*.csv`.

---

## CSVs / data separation

### Everything lands in `pcap_measurements.csv` regardless of profile

Regression of the `runner.py` env-propagation fix. `run_experiment` must call
`os.environ.update(env)` (runner.py) so the host-side `write_to_file_pcap`
reads `MEASUREMENT_SUFFIX` from the process environment. Without it, every
profile's pcap rows merge into the unsuffixed base file while the client CSVs
stay separated.

Fix: keep the `os.environ.update(env)` line in `run_experiment`; then pcap rows
go to `pcap_measurements{proto}_{profile}.csv`.

### Charts show mixed profiles / huge error bands

The chart tool plots whatever is in the selected CSV (`common/charts.py`
`_resolve_file`). If old runs from different profiles (or pre-fix states) are in
one file, aggregates span them.

Fix: delete the stale CSV(s) and re-run, or use `--suffix <proto_profile>` to
select one profile's dataset.

### `ValueError: dict contains fields not in fieldnames: 'packet_types'`

Old `write_to_file_pcap` without the `packet_types` column. The current
`output/write_csv.py` defines all 16 columns and JSON-serializes the histogram.

Fix: update `output/write_csv.py` (or run with the current checkout).

---

## Metrics that look wrong

### CoAP `retransmissions` is always 0 (or absurdly high)

Always 0: the analyzer parsed the wrong number of tshark columns (the
`coap.code,coap.mid` query was read as if `frame.number` were first).
Absurdly high (~1 per exchange): raw MID counting, forgetting that the **ACK
echoes the request MID**.

Correct behavior (current code): count CON frames per `(mid, ip.src)`, sum
`count - 1`. See [pcap-analysis.md](pcap-analysis.md) §4 for the worked example
(250 KB file → 7 real retransmissions).

### MQTT goodput looks low vs. HTTP/CoAP

By design: MQTT publishes **1 MiB chunks one at a time**, each with a blocking
`wait_for_publish(timeout=60)` (protocols/MQTT/clients/client_a.py). Under
latency, this serializes at ~one RTT per chunk.

### Energy estimates look tiny / large

`energy_j = CPU fraction × TDP × duration` (common/resource_monitor.py) with
TDP from `CPU_TDP_WATTS` (default 15 W). It is an approximation — set
`CPU_TDP_WATTS` to your actual CPU TDP for closer numbers, or use RAPL.

### Client and pcap durations disagree

They are different clocks: `time.perf_counter()` inside the container vs.
tshark relative frame timestamps. Use them as independent views, not
interchangeable values.

---

## Environment / setup

### `python -c "import flask, paho.mqtt, aiocoap"` fails

Host venv missing deps. `pip install -r requirements.txt`. These are only for
the harness; containers install their own copy in the image.

### Images build but `tc` commands fail inside containers

The app image installs `iproute2` (provides `tc`) and `ethtool` (Dockerfile).
If you replaced the base image or removed the `apt-get` lines, re-add them.

### Two copies of the repo — which stack is which?

Compose project name = folder name, so `AI-Model-Deployment-MQTT-HTTP-CoAP-Testbed`
and `...- Copy` are separate projects and can run simultaneously (no host port
bindings). Target a specific one with `docker compose -p <project> ...` or by
running the command inside that folder.
