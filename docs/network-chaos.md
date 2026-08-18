# Network chaos — `runner.py` and `scripts/network_chaos.sh`

The automated sweep runs every (protocol × profile) combination with Linux `tc`
applied **inside** the containers, so results are reproducible on any host with
`CAP_NET_ADMIN` — no real degraded network needed.

---

## 1. `runner.py` — the sweep driver

```python
BASE_ENV = os.environ.copy()

PROBE = {
    "mqtt": ("mqtt-client-a", "mosquitto-broker", 1883),
    "http": ("http-client",  "http-server",       8000),
}
COAP_SETTLE_SECONDS = 8
```

### Per experiment

```python
def run_experiment(protocol, profile):
    env = BASE_ENV.copy()
    env["COMPOSE_FILE"]      = "docker-compose.automated.yaml"
    env["COMPOSE_PROFILES"]  = protocol
    env["NETWORK_PROFILE"]   = profile
    env["MEASUREMENT_SUFFIX"]= f"{protocol}_{profile}"
    os.environ.update(env)          # <-- critical: host process inherits the same env

    docker compose --profile <protocol> up -d          # only that protocol's services
    wait_for_service(env, protocol)
    run_protocol(protocol)                              # every file (+ QoS sweep for MQTT)
    docker compose down -v                              # always, in finally
```

- `COMPOSE_FILE=docker-compose.automated.yaml` selects the chaos stack for
  every docker call, including the ones `benchmark_manager` makes through
  `packet_capture.py`.
- `MEASUREMENT_SUFFIX={protocol}_{profile}` is what separates datasets
  (e.g. `pcap_measurementshttp_good.csv`). The `os.environ.update(env)` line is
  required so the **host-side** pcap writer (`output/write_csv.py`, which reads
  `MEASUREMENT_SUFFIX` from the process environment) writes to the same
  suffixed file as the client containers. Without it, every profile's pcap rows
  would pile into the plain `pcap_measurements.csv`.

### Reachability probe

```python
def wait_for_service(env, protocol, timeout=60):
    if protocol == "coap":
        time.sleep(COAP_SETTLE_SECONDS)        # UDP: no TCP connect to probe
        return
    # else: docker compose exec <client> python -c
    #   "import socket; socket.create_connection((<host>, <port>), timeout=2)"
    # retried every 1s until the 60s deadline (raises RuntimeError)
```

CoAP gets a fixed 8 s settle delay instead of a probe because it is UDP.

### CLI

```bash
python runner.py --protocols http mqtt --profiles good harsh satellite
# --protocols default: all (http mqtt coap)
# --profiles   default: [mobile]
```

`main()` first builds the images with
`docker compose -f docker-compose.automated.yaml --profile <p> build` for every
protocol, then iterates `itertools.product(protocols, profiles)`.

---

## 2. `scripts/network_chaos.sh` — the tc applicator

The entry point of every automated-stack service:

```sh
PROFILE=${NETWORK_PROFILE:-iot}
tc qdisc del dev eth0 root 2>/dev/null || true     # clean slate on restarts

case "$PROFILE" in good|iot|harsh|mobile|satellite) apply_$PROFILE ;;
esac

if [ -z "$APP_COMMAND" ]; then
    echo "applying tc only and staying idle."
    exec sleep infinity            # clients: wait for the harness to exec transfers
fi
exec sh -c "$APP_COMMAND"          # servers/receiver: apply tc, then run the app
```

Two layers of qdisc are added per profile:

1. **`netem`** (root) — delay, loss, duplicate, reorder (jitter distribution %).
2. **`tbf`** (child) — token-bucket rate cap (`rate`, `burst`, `latency`).

The **same profile is applied on both the client and the server/broker** `eth0`
(plus the capture sidecar, which shares the server namespace). This models an
end-to-end link, not a one-directional impairment.

### Profile parameters (exact tc values)

| Profile | `netem` | `tbf` | Models |
|---|---|---|---|
| `good` | `delay 40ms 10ms`, `loss 0.1%` | `rate 10mbit burst 64kbit latency 50ms` | clean Wi-Fi |
| `iot` | `delay 200ms 100ms 30%`, `loss 2% 25%`, `duplicate 0.5%`, `reorder 0.2% 50%` | `rate 512kbit burst 32kbit latency 400ms` | constrained IoT |
| `harsh` | `delay 300ms 200ms 50%`, `loss gemodel 1% 50% 90% 1%`, `duplicate 1%`, `reorder 1% 50%` | `rate 256kbit burst 16kbit latency 800ms` | industrial edge |
| `mobile` | `delay 150ms 150ms 60%`, `loss 3% 40%`, `reorder 0.5% 50%` | `rate 1mbit burst 32kbit latency 300ms` | unstable cellular |
| `satellite` | `delay 600ms 100ms 20%`, `loss 0.5%` | `rate 1mbit burst 64kbit latency 1000ms` | GEO satellite |

Notes on the syntax:

- `netem delay A B C%` — base delay A, uniform jitter ±B, applied to C% of packets.
- `loss X Y%` — X% base loss; the second term adds a 25/40% chance of further loss
  on top (stateful).
- `loss gemodel p r h k` — Gilbert–Elliott model (probabilities as %).
- `reorder P% 50%` — reorders P% of packets (50% correlation).

Unknown profiles exit 1.

---

## 3. How the chaos + capture interact

- Because tc is inside the namespace, the **capture sidecar sees post-tc
  traffic** (the frames that actually crossed the emulated link).
- Retransmission metrics become meaningful under loss profiles:
  - TCP (MQTT/HTTP) — `tcp.analysis.*` counts retransmits.
  - CoAP — repeated CON MIDs count retransmits (see pcap-analysis).
- On heavily throttled profiles (e.g. 50 MB under `harsh` at 256 kbit ≈ 26 min),
  capture completeness warnings may appear if the host can't keep up; the
  per-run pcap + CSV still land in suffixed files.

---

## 4. Reproducibility notes

- `docker compose down -v` removes **named volumes only**; `output/`,
  `output/pcap/` are bind mounts, so results survive between profiles.
- The compose project name is the **folder name** — a copied repo is a separate
  project. Since no host ports are bound, two projects can run concurrently.
- Payloads are `os.urandom`-based; copy `data/*.bin` between machines instead
  of regenerating them for byte-identical comparisons.