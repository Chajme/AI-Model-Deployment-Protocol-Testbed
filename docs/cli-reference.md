# CLI reference & environment variables

Every executable entry point, its arguments, and the environment variables that
change behavior.

---

## 1. `protocols/benchmark_manager.py` — per-transfer host harness

Runs one or more transfers against an **already-running** compose stack. It is
called directly for manual runs and by `runner.py` for the automated sweep.

```bash
python protocols/benchmark_manager.py [--protocol mqtt http coap amqp grpc lwm2m]
                                      [--file <name.bin>]
                                      [--qos 1 2]
                                      [--no-analyze]
```

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--protocol` | nargs+ (choices `mqtt http coap amqp grpc lwm2m`) | all | which protocols to run |
| `--file` | str | all `data/*.bin` | a single payload file |
| `--qos` | nargs+ int | `1 2` | MQTT QoS sweep (ignored for non-MQTT protocols) |
| `--no-analyze` | flag | off | capture pcaps but skip tshark analysis + CSV row |

Behavior notes:

- Non-MQTT protocols ignore `--qos`; MQTT requires `qos in {1,2}` (the client
  itself enforces `--qos` as required int).
- A manual invocation creates a **run** (`output/runs/<timestamp>_<proto>.../`)
  via `_ensure_run` unless `RUN_ID` is already set (e.g. by `runner.py`).
- Environment it reads: `DATA_DIR` (`./data`), `OUTPUT_DIR` (defaults to
  `./output`), `NETWORK_PROFILE` (recorded in the manifest), `RUN_ID` (or the
  `.active_run` marker).
- Expects `docker` (and the compose stack up). `tshark` is used from the host
  if present, otherwise analysis runs in the `netshoot` container.

---

## 2. `runner.py` — automated protocol × profile sweep

```bash
python runner.py [--protocols mqtt mqtt-windowed http http-get coap amqp grpc lwm2m]
                 [--profiles good iot harsh mobile satellite ltem nbiot]
                 [--sizes 250kb,1mb,5mb] [--qos 1] [--tls]
                 [--repeat 5] [--sweep-id NAME] [--seed N] [--run-id ID]
```

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--protocols` | nargs+ (choices = `RUNNERS` keys) | all | protocols to sweep; `http-get` = device download, `mqtt-windowed` = MQTT with 20 chunks in flight |
| `--profiles` | nargs+ (names from `network_chaos.sh`) | `[mobile]` | profiles to run |
| `--sizes` | comma list | every `data/*.bin` | payloads to transfer, e.g. `250kb,1mb` (fails fast on an unknown size) |
| `--qos` | nargs+ int | `1 2` | MQTT QoS levels |
| `--tls` | flag | off | TLS variant (HTTPS 8443 / MQTT 8883); only `http`, `http-get`, `mqtt`; generates `certs/` if missing |
| `--repeat` | int | `1` | repetitions of every combination (thesis tables use 5) |
| `--sweep-id` | str | `sweep-<timestamp>` when `--repeat > 1` | label shared by all runs of the sweep (`export_measurements.py --sweep-id`) |
| `--seed` | int | random | seed for the per-repetition shuffle of the combination order |
| `--run-id` | str | auto | explicit run id (must not already exist; not with `--repeat > 1`) |

Per (protocol × profile [× repetition]) it: creates a run
(`common/runs.new_run` → `output/runs/<timestamp>_<proto>_<profile>[_tls][_r<i>]/`),
sets `COMPOSE_FILE=docker-compose.automated.yaml`, `COMPOSE_PROFILES=<proto>`,
`NETWORK_PROFILE=<profile>`, `RUN_ID`, `TLS`, `MOSQUITTO_CONF`
into the **process environment**, writes the `.active_run` marker, builds
images, `docker compose up -d`, probes reachability, records provenance
(git commit, image digests, client `pip freeze`) in `run.json`, calls
`run_protocol(protocol)`, then `docker compose down -v` in a `finally`.

Unsupported profile names exit 1 (from `network_chaos.sh`).

Example — one profile batch of the thesis matrix:

```bash
python runner.py --protocols http http-get mqtt grpc amqp --profiles ltem --sizes 250kb,1mb,5mb --qos 1 --repeat 5 --sweep-id v2-ltem
python runner.py --protocols coap lwm2m --profiles ltem --sizes 250kb,1mb --repeat 5 --sweep-id v2-ltem
python scripts/export_measurements.py --sweep-id v2-ltem
```

---

## 2b. `scripts/export_measurements.py` — Markdown tables

```bash
python scripts/export_measurements.py [--sweep-id ID [ID ...]]
       [--runs-dir output/runs] [--protocols ...] [--profiles ...]
       [-o output/measurements_export.md] [--comparison-output output/measurements_comparison.md]
```

- With `--sweep-id`: every run of those sweeps is aggregated; each comparison
  cell shows `median [Q1–Q3] n=N S%` (success = verified transfers / attempts
  from run.json), flagged † when n < 5 or success < 100 %.
- Without it: newest complete run per protocol × profile (used for the legacy
  runs: `--runs-dir output/runs-legacy-v1`).
- TLS runs appear as separate columns (`http-get+tls`, `mqtt+tls`).

## 2c. Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

Unit tests for the statistics helpers, the export's aggregation/selection logic
and `runner.py --sizes`.

---

## 3. `common/charts.py` — chart generator

```bash
python common/charts.py [options]
```

Full flag table in [charts.md](charts.md). Summary:

- Data source: `--run <run_id>` (preferred) / `--runs-dir <parent>`; legacy
  fallback `--csv-dir`, `--outdir`, `--suffix`.
- Selection: `--protocols`, `--metrics`, `--file-sizes`, `--qos`, `--mqtt-side`,
  `--no-client`, `--no-pcap`, `--no-overview`.
- Styling: `--chart-type auto|line|bar`, `--agg mean|median|min|max`,
  `--error none|minmax|std|q90|iqr`, `--x-scale auto|linear|log`,
  `--y-scale linear|log`, `--dpi N`, `--figsize WxH`.

Requires matplotlib (`pip install -r requirements-charts.txt`); exits with a
message if it is missing.

---

## 4. `data/binary_file_generator.py` — payload generator

```bash
cd data && python binary_file_generator.py
```

Generates `binary_file_<size>kb.bin` / `binary_file_<size>mb.bin` with
`os.urandom`. Sizes are edited at the bottom of the file:

```python
# file_sizes_kb = [250]
file_sizes_kb = []
file_sizes_mb = [5, 20, 50]
# file_sizes_mb = [100, 200]
```

Existing files are skipped (idempotent). Files are random — **copy** them
between machines for reproducibility; don't regenerate.

---

## 5. Client entry points (inside containers)

| Module | Args | Notes |
|---|---|---|
| `protocols.MQTT.clients.client_a` | `--file <name>` `--qos <1\|2>` | sender; both args required |
| `protocols.MQTT.clients.client_b` | — | receiver; subscribes and runs forever |
| `protocols.MQTT.clients.client_a` (windowed) | `--file <name>` `--qos <1\|2>` `--window <N>` | `--window 20` = protocol key `mqtt-windowed` |
| `protocols.HTTP.client.http_client` | `--file <name>` `--mode put\|get` | `put` = key `http`, `get` = key `http-get`; default all `*.bin` |
| `protocols.CoAP.client.coap_client` | `--file <name>` | optional; default all `*.bin` |
| `protocols.AMQP.client.amqp_client` | `--file <name>` | sender; publisher confirms |
| `protocols.GRPC.client.grpc_client` | `--file <name>` | client-streaming upload + Ping latency |
| `protocols.LWM2M.client.lwm2m_client` | `--file <name>` | firmware-update flow emulator |

All transfer clients sleep ~5 s at startup to let the server/broker come up;
after a `--file` run they keep the container alive ~3 s, otherwise ~30 s.

---

## 6. Environment variables

| Variable | Where | Default | Effect |
|---|---|---|---|
| `DATA_DIR` | harness, file_manager | `./data` | payload directory |
| `OUTPUT_DIR` | write_csv, file_manager, charts, runs | `./output` (host) / `/app/output` (container) | results directory (runs live under `<OUTPUT_DIR>/runs/`) |
| `RUN_ID` | write_csv, runs | `` (empty) | active run id (containers fall back to the `.active_run` marker) |
| `NETWORK_PROFILE` | network_chaos.sh, manifest | `iot` | which tc profile to apply (recorded per row + manifest) |
| `APP_COMMAND` | network_chaos.sh | unset | command to run after tc (servers/receiver) |
| `COMPOSE_FILE` / `COMPOSE_PROFILES` | runner.py | — | selects the automated stack + protocol |
| `SHAPE_DST` | network_chaos.sh | unset | shape only egress to this host (MQTT/AMQP capture sidecars → `client-b`) |
| `SHAPE_IFACE` | network_chaos.sh | `eth0` | interface to shape |
| `TLS` | HTTP/MQTT clients + server, analyzer | `0` | `1` = TLS variant (set by `runner.py --tls`) |
| `CERTS_DIR` | HTTP/MQTT clients + server | `/app/certs` | CA + server certificate location |
| `MOSQUITTO_CONF` | compose (broker) | `mosquitto.conf` | `mosquitto-tls.conf` for MQTT over TLS |
| `COAP_MAX_RETRIES` | coap_client | `3` (`1` on `nbiot`) | whole-file retry attempts |
| `GRPC_MIN_THROUGHPUT_BPS` | grpc_client | `32000` (`16000` on `nbiot`) | floor used to scale the RPC deadline |
| `HTTP_MAX_RETRY_ATTEMPTS` | http_client (GET) | `30` | reconnect attempts while resuming a download |
| `HTTP_READ_TIMEOUT_S` | http_client (GET) | `120` | stalled-read timeout before a resume is attempted |

---

## 7. Docker / compose

```bash
docker compose build                                   # build the app image (once)
docker compose up -d                                   # manual stack (all 20 services)
docker compose ps                                      # verify status
docker compose exec <svc> <cmd>                        # manual introspection
docker compose down                                    # stop (keep volumes/data)
docker compose down -v                                 # runner cleanup (named volumes only)
```

The automated stack is driven exclusively through `runner.py`; `COMPOSE_FILE`
and profiles are set by the runner, so don't mix compose flags manually.
