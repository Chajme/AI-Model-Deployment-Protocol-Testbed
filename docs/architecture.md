# Architecture

The testbed runs three **isolated protocol networks** in Docker and measures
every transfer from two independent vantage points. This page describes the
containers, the networks, the two compose stacks, and the image build.

---

## 1. Container topology

Each protocol gets its own bridge network with three roles:

```
                     ┌──────────────────────────────────────────┐
                     │   <proto>-net  (bridge)                  │
                     │                                          │
   host harness ────►│  <proto>-client ──► <proto>-server/broker │
   (benchmark_       │        │                │                │
    manager.py)      │        │   traffic      │  (shares netns)│
                     │        ▼                ▼                │
                     │  <proto>-capture (netshoot, runs tcpdump) │
                     └──────────────────────────────────────────┘
```

| Role | Image | Network | Entry point | Notes |
|---|---|---|---|---|
| `mqtt-client-a` | app (built) | `mqtt-net` | `sleep infinity` (manual) / `network_chaos.sh` (automated) | sender |
| `mqtt-client-b` | app (built) | `mqtt-net` | `client_b` (manual) / `network_chaos.sh` | receiver, always running |
| `mosquitto-broker` | `eclipse-mosquitto:latest` | `mqtt-net` | broker | `listener 1883`, `allow_anonymous true` |
| `mqtt-capture` | `nicolaka/netshoot` | `network_mode: service:mosquitto-broker` | `sleep infinity` | tcpdump lives here |
| `http-client` | app (built) | `http-net` | `sleep infinity` / `network_chaos.sh` | PUT uploader |
| `http-server` | app (built) | `http-net` | `flask_server` / `network_chaos.sh` | Flask upload API |
| `http-capture` | `nicolaka/netshoot` | `network_mode: service:http-server` | `sleep infinity` | tcpdump lives here |
| `coap-client` | app (built) | `coap-net` | `sleep infinity` / `network_chaos.sh` | blockwise PUT uploader |
| `coap-server` | app (built) | `coap-net` | `coap_server` / `network_chaos.sh` | aiocoap resource |
| `coap-capture` | `nicolaka/netshoot` | `network_mode: service:coap-server` | `sleep infinity` | tcpdump lives here |

### Why the capture sidecar shares the server's network namespace

`network_mode: service:<server>` puts the sidecar **inside the server's network
namespace**, so `tcpdump -i eth0` in the sidecar sees the exact frames arriving
at and leaving the server — the same traffic the server processes. There is no
SPAN/port-mirroring trickery and no second hop to confuse the analysis.

### Why clients stay idle

Clients run `sleep infinity` (or `network_chaos.sh` with no `APP_COMMAND`, which
also ends in `sleep infinity`). The **host harness** execs one transfer at a
time into the client with `docker compose exec`. This makes each run
capturable in its own pcap (one tcpdump start/stop per transfer) instead of one
endless capture that would have to be sliced up later.

---

## 2. Networks

All three networks are plain Docker bridge drivers (`driver: bridge`):

```
networks:
  mqtt-net:  { driver: bridge }
  http-net:  { driver: bridge }
  coap-net:  { driver: bridge }
```

No host port bindings exist anymore (1883 / 8080 / 5683 are **not** published).
Traffic stays inside each bridge network. This is what allows two copies of the
repo (two compose projects) to run simultaneously without port conflicts.

---

## 3. The two compose stacks

Both stacks build the **same app image** from the Dockerfile and share service
names, so one `docker compose build` covers both.

### `docker-compose.yaml` — manual baseline

- Servers/broker **auto-start** (`command: python -m ...`); clients are idle.
- Capture sidecars are idle, waiting for tcpdump to be started per run.
- Client containers set `MEASUREMENT_SUFFIX=_testing`, so client CSV rows land
  in `output/<proto>_measurements_testing.csv`.
- No `tc` — a clean baseline network.

### `docker-compose.automated.yaml` — chaos sweep

- All services are **profile-gated**: `profiles: ["mqtt"]`, `["http"]`,
  `["coap"]`. Only the selected protocol's services are started.
- Every service runs `network_chaos.sh` as its entry point, which applies the
  `tc` profile to `eth0` before doing anything else.
- `NETWORK_PROFILE` and `MEASUREMENT_SUFFIX` are injected from the host env
  (set by `runner.py`).
- Servers/receiver get `APP_COMMAND` (the real program to start after tc);
  clients get neither, so they apply tc and stay idle.
- `CAP_NET_ADMIN` on every service (and `NET_RAW` on captures) is what allows
  `tc` and `tcpdump` to run inside the containers.

### `docker-compose.tc.yaml` — legacy scratch

A mostly commented-out scratch file for one-off manual chaos testing. It is not
used by the harness. Ignore it.

---

## 4. Image build

`Dockerfile`:

```dockerfile
FROM python:3.13.3-slim
WORKDIR /app
RUN apt-get update && apt-get install -y iproute2 ethtool && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
```

- `iproute2` provides `tc` (traffic control) for the chaos profiles.
- `ethtool` is used at capture time to disable segmentation offloads
  (GRO/GSO/TSO) — without this, the veth pair delivers multi-MB GSO
  super-frames and per-segment header overhead is invisible in the pcap.
- The pinned base image is `python:3.13.3-slim`; `eclipse-mosquitto:latest`
  and `nicolaka/netshoot` are intentionally unpinned.

`.dockerignore` keeps the image lean: `.venv`, `.idea`, `.git`, `__pycache__`,
`data`, `output`, `uploads`, `*.pcap` are excluded from the build context.
(The containers still *see* `data/`, `output/`, `uploads/` via bind mounts in
compose.)

**Volumes** are bind mounts, not named volumes:

| Host path | Mounted at | Used by |
|---|---|---|
| `./data` | `/app/data` | clients (payloads) |
| `./output` | `/app/output` | all containers (CSV rows) |
| `./output/pcap` | `/pcap` | capture sidecars (left-over mount; active pcaps go through `/tmp`) |
| `./uploads` | `/var/www/uploads/upload` | http/coap servers (received files) |
| `./` | `/app` | all app containers (code) |

Because they are bind mounts, `docker compose down -v` (used by `runner.py`)
removes **named volumes only** — CSVs and pcaps survive.

---

## 5. Who runs where

| Concern | Runs on |
|---|---|
| Protocol transfers | inside client containers (HTTP/MQTT/CoAP libs are container-only) |
| Packet capture | `tcpdump` inside the capture sidecar |
| Capture orchestration (start/stop/copy) | host — `common/packet_capture.py` via `docker compose exec` |
| pcap analysis | host — `common/pcap_analyzer.py` via local `tshark` |
| CSV writing | client containers for runtime metrics; host harness for pcap metrics |
| Resource sampling (CPU/RAM/energy) | inside the client process — `common/resource_monitor.py` |
| Chart generation | host — `common/charts.py` (matplotlib) |
