# CLI reference & environment variables

Every executable entry point, its arguments, and the environment variables that
change behavior.

---

## 1. `protocols/benchmark_manager.py` — per-transfer host harness

Runs one or more transfers against an **already-running** compose stack. It is
called directly for manual runs and by `runner.py` for the automated sweep.

```bash
python protocols/benchmark_manager.py [--protocol mqtt http coap]
                                      [--file <name.bin>]
                                      [--qos 1 2]
                                      [--no-analyze]
```

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--protocol` | nargs+ (choices `mqtt http coap`) | all | which protocols to run |
| `--file` | str | all `data/*.bin` | a single payload file |
| `--qos` | nargs+ int | `1 2` | MQTT QoS sweep (ignored for HTTP/CoAP) |
| `--no-analyze` | flag | off | capture pcaps but skip tshark analysis + CSV row |

Behavior notes:

- Non-MQTT protocols ignore `--qos`; MQTT requires `qos in {1,2}` (the client
  itself enforces `--qos` as required int).
- A manual invocation creates a **run** (`output/runs/<timestamp>_<proto>.../`)
  via `_ensure_run` unless `RUN_ID` is already set (e.g. by `runner.py`).
- Environment it reads: `DATA_DIR` (`./data`), `OUTPUT_DIR` (defaults to
  `./output`), `NETWORK_PROFILE` (recorded in the manifest), `RUN_ID` (or the
  `.active_run` marker).
- Expects `docker` and `tshark` on the host, and the compose stack up.

---

## 2. `runner.py` — automated protocol × profile sweep

```bash
python runner.py [--protocols mqtt http coap]
                 [--profiles good iot harsh mobile satellite]
```

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--protocols` | nargs+ (choices `http mqtt coap`) | all | protocols to sweep |
| `--profiles` | nargs+ (choices from `network_chaos.sh`) | `[mobile]` | profiles to run |
| `--run-id` | str | auto | explicit run id (must not already exist) |

Per (protocol × profile) it: creates a run
(`common/runs.new_run` → `output/runs/<timestamp>_<proto>_<profile>/`), sets
`COMPOSE_FILE=docker-compose.automated.yaml`, `COMPOSE_PROFILES=<proto>`,
`NETWORK_PROFILE=<profile>`, `MEASUREMENT_SUFFIX=<proto>_<profile>`, `RUN_ID`
into the **process environment**, writes the `.active_run` marker, builds
images, `docker compose up -d`, probes reachability, calls
`run_protocol(protocol)`, then `docker compose down -v` in a `finally`.

Unsupported profile names exit 1 (from `network_chaos.sh`).

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
  `--error none|minmax|std|q90`, `--x-scale auto|linear|log`,
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
file_sizes_kb = []          # e.g. [250]
file_sizes_mb = [100, 200]  # e.g. [1, 5, 20, 50]
```

Existing files are skipped (idempotent). Files are random — **copy** them
between machines for reproducibility; don't regenerate.

---

## 5. Client entry points (inside containers)

| Module | Args | Notes |
|---|---|---|
| `protocols.MQTT.clients.client_a` | `--file <name>` `--qos <1\|2>` | sender; both args required |
| `protocols.MQTT.clients.client_b` | — | receiver; subscribes and runs forever |
| `protocols.HTTP.client.http_client` | `--file <name>` | optional; default all `*.bin` |
| `protocols.CoAP.client.coap_client` | `--file <name>` | optional; default all `*.bin` |

All transfer clients sleep ~5 s at startup to let the server/broker come up;
after a `--file` run they keep the container alive ~3 s, otherwise ~30 s.

---

## 6. Environment variables

| Variable | Where | Default | Effect |
|---|---|---|---|
| `DATA_DIR` | harness, file_manager | `./data` | payload directory |
| `OUTPUT_DIR` | write_csv, file_manager, charts, runs | `./output` (host) / `/app/output` (container) | results directory (runs live under `<OUTPUT_DIR>/runs/`) |
| `RUN_ID` | write_csv, runs | `` (empty) | active run id (containers fall back to the `.active_run` marker) |
| `MEASUREMENT_SUFFIX` | runner, manifest | `` (empty) | recorded in `run.json`; no longer affects filenames |
| `NETWORK_PROFILE` | network_chaos.sh, manifest | `iot` | which tc profile to apply (recorded per row + manifest) |
| `APP_COMMAND` | network_chaos.sh | unset | command to run after tc (servers/receiver) |
| `COMPOSE_FILE` / `COMPOSE_PROFILES` | runner.py | — | selects the automated stack + protocol |
| `CPU_TDP_WATTS` | resource_monitor | `15.0` | TDP used in the energy estimate |
| `MAX_RETRIES`-style | coap_client | `3` | app-level retry attempts (hard-coded constant, not env) |

---

## 7. Docker / compose

```bash
docker compose build                                   # build the app image (once)
docker compose up -d                                   # manual stack (all 10)
docker compose ps                                      # verify status
docker compose exec <svc> <cmd>                        # manual introspection
docker compose down                                    # stop (keep volumes/data)
docker compose down -v                                 # runner cleanup (named volumes only)
```

The automated stack is driven exclusively through `runner.py`; `COMPOSE_FILE`
and profiles are set by the runner, so don't mix compose flags manually.
