# Measurement pipeline — one transfer, end to end

This page follows a single transfer through every stage, at the code level.
The orchestrator is `protocols/benchmark_manager.py`; the two helpers it calls
are `common/packet_capture.py` (capture) and `common/pcap_analyzer.py`
(analysis), and the CSV writer is `output/write_csv.py`.

---

## 1. Entry points

| How it starts | Called from | Where rows go |
|---|---|---|
| `python protocols/benchmark_manager.py ...` | manual | new run dir: `output/runs/<timestamp>_<proto>[_<profile>]/` |
| `run_protocol()` inside `runner.py` | automated sweep | run dir: `output/runs/<timestamp>_<proto>_<profile>/` |

A run is created before transfers start (`common/runs.new_run` writes the
`run.json` manifest and the `.active_run` marker). Both entry points end up in
`run_protocol(protocol, files, qos_levels, analyze)`, which records the
transferred `files` / `file_sizes` / `qos_levels` back into the manifest.

```python
# benchmark_manager.py
RUNNERS = {
    "mqtt": {"service": "mqtt-client-a",
             "module": "protocols.MQTT.clients.client_a",
             "has_qos": True},
    "http": {"service": "http-client",
             "module": "protocols.HTTP.client.http_client",
             "has_qos": False},
    "coap": {"service": "coap-client",
             "module": "protocols.CoAP.client.coap_client",
             "has_qos": False},
}
DEFAULT_MQTT_QOS = [1, 2]
```

`run_protocol` discovers every `*.bin` in `DATA_DIR` (`./data`, sorted by size),
and for MQTT iterates the QoS sweep (default `1 2`) × every file; for HTTP/CoAP
it iterates just the files. Each combination becomes one `run_transfer()` call.

---

## 2. `run_transfer()` — capture, transfer, capture-stop

```python
label  = f"{filename}_{qos}" if qos is not None else filename
outfile = start_capture_run(label, protocol)          # 1. tcpdump up
try:
    docker compose exec <service> python -m <module> --file <filename> [--qos N]
finally:
    stop_capture_run(protocol, outfile, runs.pcap_dir())  # 2. tcpdump down, pcap copied
# 3. analyze + log (unless --no-analyze)
```

`runs.pcap_dir()` resolves to `output/runs/<run_id>/pcap/` when a run is active,
else the legacy `output/pcap/`.

### 2a. `start_capture_run(label, protocol)` — `common/packet_capture.py`

1. **Reset**: `rm -f /tmp/{protocol}_{label}.pcap` inside the sidecar, so a
   previous identical run can't contaminate this one.
2. **Offload tuning** — `_disable_offloads(protocol)`. Runs, for the capture
   sidecar plus every client that originates traffic:
   ```bash
   docker compose exec <svc> ethtool -K eth0 gro off gso off tso off
   ```
   Target map:
   ```python
   OFFLOAD_CONTAINERS = {
       "mqtt": ["mqtt-client-a", "mqtt-client-b"],
       "http": ["http-client"],
       "coap": [],                       # UDP — no segmentation offloads
   }
   OFFLOAD_SETTINGS = ["gro", "gso", "tso"]
   ```
   Failures are warnings, not errors (a missed disable only *under*-reports
   header overhead; aborting would kill the whole benchmark).
3. **Start tcpdump** (detached, in the sidecar):
   ```bash
   docker compose exec -d <capture-svc> tcpdump -B 8192 -i eth0 -s 0 -w /tmp/<proto>_<label>.pcap
   ```
   - `-B 8192` — 8 MiB kernel capture buffer (`TCPDUMP_BUFFER_KB = 8192`). The
     default ~1 MiB overflows and drops frames during fast large-file bursts.
   - `-s 0` — full snapshot length (capture every byte of every frame).
   - **Deliberately not `-U`**: packet-buffered mode does a `write(2)` per frame
     to the filesystem and the kernel ring overflows; default buffered mode
     drains the ring in bulk and flushes large chunks to disk.
   - The pcap is written to `/tmp` (container-local overlay fs) rather than the
     bind-mounted `/pcap`, because the volume mount is too slow for the high
     packet rate of MTU-sized captures.
4. **Wait for readiness** — polls `pgrep -x tcpdump` in the sidecar until it
   appears (5 s deadline) and raises if it never does.

### 2b. The transfer itself

`docker compose exec <client> python -m <module> --file <filename>` (plus
`--qos N` for MQTT). Inside the container the client performs the transfer,
measures runtime metrics, and appends its own row to
`output/runs/<run_id>/<proto>_measurements.csv` (see
[protocol-transfers](protocol-transfers.md)). The run id is resolved from the
`RUN_ID` env var, or from the `.active_run` marker written by the host into the
output bind mount.

### 2c. `stop_capture_run(protocol, container_pcap_path, host_pcap_dir)`

1. `pkill -TERM tcpdump` in the sidecar — SIGTERM makes tcpdump flush buffered
   frames and close the pcap cleanly.
2. **Wait for the process to exit** (poll `pgrep`; 5 s deadline) so the file is
   guaranteed complete before it is copied.
3. `docker compose cp <capture-svc>:/tmp/<proto>_<label>.pcap <run pcap dir>/`
   then `rm -f` the container-local copy.

---

## 3. Analysis + logging (`run_transfer` tail)

Unless `--no-analyze`:

```python
size = os.path.getsize(os.path.join(DATA_DIR, filename))
result = analyze_pcap(pcap_path, size, protocol=protocol, filename=filename,
                      qos_level=qos, label=label)
print_result(result)                    # console "PCAP ANALYSIS" block
write_to_file_pcap([result])            # appends a row to <run>/pcap_measurements.csv
```

`analyze_pcap` is detailed in [pcap-analysis.md](pcap-analysis.md). If analysis
raises (e.g. tshark missing), the transfer is still counted as captured — the
error is printed and the run moves on.

---

## 4. CSV writing

`output/write_csv.py`:

```python
def _measurement_dir():
    output_dir = os.getenv("OUTPUT_DIR", "/app/output")
    run_id = runs.active_run_id()        # RUN_ID env, else the .active_run marker
    if run_id:
        return runs.run_dir(output_dir, run_id)   # <OUTPUT_DIR>/runs/<run_id>
    return output_dir                               # legacy flat fallback

def _measurement_file(protocol):
    return f"{_measurement_dir()}/{protocol}_measurements.csv"
```

- In containers `OUTPUT_DIR` defaults to `/app/output` (bind-mounted to
  `./output`); the host harness sets `OUTPUT_DIR=./output` before anything runs.
- **Every row** carries `run_id`, `timestamp`, `network_profile` metadata columns
  (`META_FIELDS`), added on first write. Pre-existing legacy files (without the
  columns) are appended unchanged.
- Rows are **appended**; the header is written only when the file is created.
- Filenames no longer carry `MEASUREMENT_SUFFIX` — the run id + `run.json`
  manifest carry the protocol/profile context. See
  [network-chaos](network-chaos.md) for how `runner.py` sets up a run.

All 16 pcap columns plus the client-side schemas are documented in
[metrics-schema.md](metrics-schema.md).

---

## 5. Timing and throughput definitions

| Value | Definition |
|---|---|
| `duration_seconds` | time of the **last captured frame** minus the first (relative timestamps) |
| `goodput_mbps` (pcap) | `file_size_bytes × 8 / (duration × 1_000_000)` — payload rate |
| `wire_throughput_mbps` | `total_wire_bytes × 8 / (duration × 1_000_000)` — everything on the wire |
| `overhead_percentage` | `(total_wire_bytes − file_size_bytes) / file_size_bytes × 100` |
| `retransmissions` | TCP: `tcp.analysis.*` flags; CoAP: repeated CON message IDs (see pcap-analysis) |

Client-side timing uses `time.perf_counter()` inside the container and is
**not** the same clock domain as tshark — treat the two durations as
complementary, not interchangeable.

---

## 6. Capture integrity check

`analyze_pcap` compares `total_wire_bytes` against the known file size and warns
when the capture looks incomplete:

```
WARNING: capture looks incomplete -- captured N B is less than the M B file ...
Re-run this transfer.
```

This catches dropped frames (kernel buffer overflow, transient container
stalls) so you don't chart garbage. Because a capture can legitimately be
*smaller* than the file (rare on clean runs, common under lossy profiles), the
check is a warning, not a failure.
