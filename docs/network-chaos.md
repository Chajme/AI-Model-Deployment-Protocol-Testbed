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
    "amqp": ("amqp-client-a", "rabbitmq-broker",  5672),
    "grpc": ("grpc-client",  "grpc-server",       50051),
}
UDP_SETTLE_SECONDS = {
    "coap": 8,
    "lwm2m": 8,
}
```

### Per experiment

```python
def run_experiment(protocol, profile):
    env = BASE_ENV.copy()
    env["COMPOSE_FILE"]      = "docker-compose.automated.yaml"
    env["COMPOSE_PROFILES"]  = protocol
    env["NETWORK_PROFILE"]   = profile
    env["RUN_ID"]            = run_id
    os.environ.update(env)          # <-- critical: host process inherits the same env

    docker compose --profile <protocol> up -d          # only that protocol's services
    wait_for_service(env, protocol)
    run_protocol(protocol)                              # every file (+ QoS sweep for MQTT)
    docker compose down -v                              # always, in finally
```

- `COMPOSE_FILE=docker-compose.automated.yaml` selects the chaos stack for
  every docker call, including the ones `benchmark_manager` makes through
  `packet_capture.py`.
- Each experiment gets a **fresh run directory**
  (`output/runs/<timestamp>_<proto>_<profile>/` via `common/runs.new_run`) so
  every profile's rows are cleanly separated without suffix parsing. The
  `os.environ.update(env)` line is still required so the host process inherits
  `RUN_ID` and the **host-side** pcap writer writes to the same run directory
  as the client containers. The `.active_run` marker in `output/` is how the
  containers (which lack `RUN_ID`) resolve the same run through the bind mount.

### Reachability probe

```python
def wait_for_service(env, protocol, timeout=60):
    if protocol in UDP_SETTLE_SECONDS:
        time.sleep(UDP_SETTLE_SECONDS[protocol])  # UDP: no TCP connect to probe
        return
    # else: docker compose exec <client> python -c
    #   "import socket; socket.create_connection((<host>, <port>), timeout=2)"
    # retried every 1s until the 60s deadline (raises RuntimeError)
```

CoAP and LwM2M get a fixed 8 s settle delay instead of a probe because they
are UDP.

### CLI

```bash
python runner.py --protocols http mqtt --profiles good harsh satellite
# --protocols default: all (http mqtt coap amqp grpc lwm2m)
# --profiles   default: [mobile]
```

`main()` first builds the images with
`docker compose -f docker-compose.automated.yaml --profile <p> build` for every
protocol, then iterates `itertools.product(protocols, profiles)`.

---

## 2. `scripts/network_chaos.sh` — the tc applicator

The entry point of every automated-stack app service, and of the MQTT/AMQP
capture sidecars:

```sh
PROFILE=${NETWORK_PROFILE:-iot}   # good|iot|harsh|mobile|satellite|ltem|nbiot|none
IFACE=${SHAPE_IFACE:-eth0}
tc qdisc del dev "$IFACE" root 2>/dev/null || true   # clean slate on restarts

set_profile "$PROFILE"            # sets $NETEM and $TBF for that profile
if   [ "$PROFILE" = none ];  then :          # no shaping
elif [ -n "$SHAPE_DST" ];    then apply_dst  # shape only traffic to $SHAPE_DST
else                              apply_root # shape all egress of $IFACE
fi

[ -z "$APP_COMMAND" ] && exec sleep infinity  # clients/sidecars: stay idle
exec sh -c "$APP_COMMAND"                     # servers/receivers: run the app
```

Two layers of qdisc are added per profile:

1. **`netem`** — delay, loss, duplicate, reorder (jitter distribution %).
2. **`tbf`** (child of netem) — token-bucket rate cap (`rate`, `burst`, `latency`).

`apply_dst` puts a `prio` qdisc at the root whose default traffic goes to an
unshaped band (`1:2`), hangs the netem + tbf pair under band `1:3`, and adds a
`u32` filter that sends only packets addressed to `$SHAPE_DST`'s IP to `1:3`.

### Shaping model: a bidirectional access link

There is exactly **one constrained link**: between the edge device (the side
that receives the model) and the endpoint it gets the data from. It is
constrained **in both directions**; every other link (backend, server/CI side)
is clean. `tc` shapes egress only, so both endpoints of that link shape their
own egress with the same profile. Profile values are therefore **per
direction**, and the round-trip time is about **2 × delay**.

| Protocol | Data path | Shaped |
|---|---|---|
| HTTP, HTTP GET, CoAP, gRPC, LwM2M | client ↔ server (one link, own network per protocol) | client egress and server egress |
| MQTT, AMQP | publisher `client-a` (server side) → broker → device `client-b` | `client-b` egress, and broker egress **towards `client-b` only** (applied by the capture sidecar in the broker's namespace, `SHAPE_DST`). `client-a` runs `NETWORK_PROFILE=none`. |

Assumptions to state when reporting results:

- the same profile values apply in both directions (no uplink/downlink
  asymmetry);
- for upload-style transfers (HTTP PUT, CoAP PUT, gRPC streaming) the shaping
  is symmetric, so the result does not depend on which end plays the device.

The MQTT/AMQP sidecars also capture only the device leg (`host <client-b>`
BPF filter), so wire overhead is reported for one leg. Runs made before this
model (tag `analysis-v1-legacy`) live in `output/runs-legacy-v1/`; see
ISSUES.md FIXED-15.

### Profile parameters (exact tc values)

| Profile | `netem` | `tbf` | Models |
|---|---|---|---|
| `good` | `delay 40ms 10ms`, `loss 0.1%` | `rate 10mbit burst 64kbit latency 50ms` | clean Wi-Fi |
| `iot` | `delay 200ms 100ms 30%`, `loss 2% 25%`, `duplicate 0.5%`, `reorder 0.2% 50%` | `rate 512kbit burst 32kbit latency 400ms` | constrained IoT |
| `harsh` | `delay 300ms 200ms 50%`, `loss gemodel 1% 50% 90% 1%`, `duplicate 1%`, `reorder 1% 50%` | `rate 256kbit burst 16kbit latency 800ms` | industrial edge |
| `mobile` | `delay 150ms 150ms 60%`, `loss 3% 40%`, `reorder 0.5% 50%` | `rate 1mbit burst 32kbit latency 300ms` | unstable cellular |
| `satellite` | `delay 600ms 100ms 20%`, `loss 0.5%` | `rate 1mbit burst 64kbit latency 1000ms` | GEO satellite |
| `ltem` | `delay 75ms 25ms 25%`, `loss 0.5%` | `rate 300kbit burst 16kbit latency 1500ms` | LTE-M (Cat-M1): ~300 kbit/s realistic throughput (3GPP TS 36.306, UE category M1); RTT ≈ 150 ms |
| `nbiot` | `delay 800ms 150ms 25%`, `loss 1%` | `rate 25kbit burst 4kbit latency 8000ms` | NB-IoT (Cat-NB1): ~26 kbit/s downlink peak (3GPP TS 36.306); latency target ≤ 10 s (3GPP TR 45.820); RTT ≈ 1.6 s |

The delays are **one-way**: both ends of the constrained link are shaped, so
the RTT is about 2 × delay. The cellular values (`ltem`, `nbiot`) are starting
points from the literature and must be recalibrated on the field SIM (median
`ping` RTT and a 250 KB HTTP download over PPPoS). Verify the cited 3GPP
sources before quoting them. On `nbiot`, the gRPC deadline floor drops to
16 kbit/s and CoAP allows only one (whole-file) retry; both can be
overridden with `GRPC_MIN_THROUGHPUT_BPS` / `COAP_MAX_RETRIES`.

Notes on the syntax:

- `netem delay A B C%` — base delay A, uniform jitter ±B, applied to C% of packets.
- `loss X Y%` — X% base loss; the second term adds a 25/40% chance of further loss
  on top (stateful).
- `loss gemodel p r h k` — Gilbert–Elliott model (probabilities as %).
- `reorder P% 50%` — reorders P% of packets (50% correlation).

Unknown profiles exit 1. `none` applies no shaping (used by the MQTT/AMQP publishers).

---

## 3. How the chaos + capture interact

- Because tc is inside the namespace, the **capture sidecar sees post-tc
  traffic** (the frames that actually crossed the emulated link).
- Retransmission metrics become meaningful under loss profiles:
  - TCP (MQTT/HTTP/AMQP/gRPC) — `tcp.analysis.*` counts retransmits.
  - CoAP/LwM2M — repeated CON MIDs count retransmits (see pcap-analysis).
- On heavily throttled profiles (e.g. 50 MB under `harsh` at 256 kbit ≈ 26 min),
  capture completeness warnings may appear if the host can't keep up; the
  per-run pcap + CSV still land in the run directory.

---

## 4. Reproducibility notes

- `docker compose down -v` removes **named volumes only**; `output/` is a bind
  mount, so runs survive between profiles (each profile writes to its own
  `output/runs/<run_id>/`).
- The compose project name is the **folder name** — a copied repo is a separate
  project. Since no host ports are bound, two projects can run concurrently.
- Payloads are `os.urandom`-based; copy `data/*.bin` between machines instead
  of regenerating them for byte-identical comparisons.