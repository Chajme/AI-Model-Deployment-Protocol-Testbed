# Protocol transfer internals

Each protocol has a distinct on-the-wire behavior and a distinct latency
metric. This page documents the client and server code for all six.

---

## MQTT — chunked publish over a broker

### Sender: `protocols/MQTT/clients/client_a.py`

- Broker: `mosquitto-broker:1883` (mosquitto.conf: `listener 1883`,
  `allow_anonymous true`).
- Topics:
  - `file/control` — JSON metadata: `{filename, total_chunks, checksum, qos}`
  - `file/data` — raw 1 MiB binary chunks
- Chunk size: `CHUNK_SIZE = 1024 * 1024` (1 MiB); total chunks
  `ceil(file_size / CHUNK_SIZE)`.
- Flow (`send_file`):
  1. `make_client()` → connect → `loop_start()`.
  2. Compute SHA-256 of the file.
  3. `send_metadata()` publishes the control message at the requested QoS and
     records `metadata_sent_time` + the publish `mid`.
  4. **ACK latency** (outside the timed window): `on_publish` fires when the
     broker acknowledges the control message (`mid == metadata_mid`);
     `ack_latency = now - sent_time`. Waits up to 10 s
     (`metadata_ack_event.wait(timeout=10)`). The metadata round trip is
     recorded separately in `latency`, so a lost metadata ACK can no longer
     inject up to 10 s into `sender_duration`.
  5. `send_chunks()` publishes every 1 MiB chunk with
     `msg_info.wait_for_publish(timeout=60)` per chunk — one publish round-trip
     per chunk (this is why MQTT goodput is low for large files). An
     unacknowledged chunk now aborts the transfer (non-zero exit, counted as a
     failed attempt). With `--window N` (protocol key `mqtt-windowed`, N = 20)
     up to N chunks stay in flight (`max_inflight_messages_set`) and all
     acknowledgements are awaited at the end, which isolates the cost of the
     per-chunk wait.
  6. Duration is wall-clock across the chunk publishes only — the timer starts
     once the metadata ACK has arrived;
     `goodput_mbps = file_size × 8 / (duration × 1e6)`.
  7. Writes a `side=sender` row with CPU/RAM from `ResourceMonitor`
     (wrapping the metadata + chunk publish window).
- CLI: `--file <name> --qos <1|2>` (both required); sleeps 5 s on startup for
  the broker.

### Receiver: `protocols/MQTT/clients/client_b.py`

- Connects with retries (`_connect_with_retries`, 15 attempts × 2 s) and
  subscribes to both topics at `qos=2` (the effective QoS is whatever the
  sender used).
- On `file/control`: stores metadata, resets state, opens the output file, and
  starts a `ResourceMonitor`. Warns + closes the stale handle (and stops any
  stale monitor) if a previous transfer was incomplete.
- On `file/data`: writes payload, tracks bytes/chunks. **First-chunk latency** =
  `time.perf_counter() - metadata_arrival_time`.
- On the final chunk: computes duration, verifies the received file's SHA-256
  against the metadata checksum, stops the monitor, and writes a `side=receiver`
  row with `integrity_ok` plus the CPU/RAM columns.
- **Single-chunk transfers** (file ≤ 1 chunk) record `receiver_duration="X"`
  and `goodput_mbps="X"` — a single chunk spans no measurable arrival window
  (the old sub-millisecond windows produced fake 1500+ Mbps rows).
  First-chunk lag and integrity are still recorded.

### CSV rows produced

Two rows per transfer — one from the sender, one from the receiver — each with
its own `duration` and `latency` definition. `charts.py` selects the sender row
by default (`--side auto`).

---

## HTTP — streaming PUT upload (`http`) and device download (`http-get`)

Both protocol keys use the same client module and server; `http-get` passes
`--mode get` (see `RUNNERS` in `protocols/benchmark_manager.py`). With
`TLS=1` both switch to HTTPS on port 8443 (see the TLS section below).

### Client: `protocols/HTTP/client/http_client.py`

- Server: `http://http-server:8000` (`https://http-server:8443` with `TLS=1`).
- **Latency (TCP connect)** — `measure_network_latency()` opens a bare TCP
  socket to the server, times the connect, closes. No HTTP, no server
  processing. With TLS it also times the handshake on that socket and returns
  it separately (`tls_handshake_s`).
- **PUT upload** (`transfer_file`, key `http`):
  1. Streams the file with `requests.put(BASE_URL + "/upload/" + filename,
     data=file_stream, headers={"X-Checksum": checksum}, hooks=...)`; memory
     stays flat regardless of file size.
  2. `integrity_ok = (put_response.status_code == 200)` — the *server* decided
     checksum equality. TTFB comes from a `requests` response hook.
  3. A failed upload still writes a row (`integrity_ok=False`) so success
     rates are honest.
- **GET download** (`download_file`, key `http-get`):
  1. `GET /download/<file>` with `stream=True`, read in 16 KiB chunks, SHA-256
     updated per chunk and compared with the source payload (the client
     container mounts the same `data/`).
  2. TTFB = time from request start to response headers.
  3. On `ConnectionError` / `ChunkedEncodingError` / timeout the client
     retries with `Range: bytes=<received>-` and requires `206`
     (`HTTP_MAX_RETRY_ATTEMPTS`, default 30, 1 s apart; a refused connect
     while the server restarts counts as a retry, not a resume). A stalled read
     is treated as broken after `HTTP_READ_TIMEOUT_S` (default 120 s).
  4. Writes an `http-get` row with `resumed` (number of 206 continuations) and
     `bytes_resumed` (bytes received after a resume).
- CLI: `--file <name> --mode put|get`; sleeps 5 s on startup.

### Server: `protocols/HTTP/server/flask_server.py`

- Served by **gunicorn** (`gthread`, 2 workers × 4 threads, `--timeout 3600`),
  not the Flask development server, for both the plain and the TLS variant,
  so the two differ only in TLS. `python -m protocols.HTTP.server.flask_server`
  execs gunicorn with the right bind/cert arguments.
- `PUT /upload/<file>` reads `request.stream` in 64 KiB chunks, hashing as the
  body arrives (no whole-body buffering), and returns 400 on a checksum
  mismatch.
- `GET /download/<file>` serves `data/<file>` with
  `send_from_directory(..., conditional=True)`: Werkzeug answers `Range`
  requests with `206 Partial Content`, which makes resume possible.
- A legacy `protocols/HTTP/server/nginx.conf` (WebDAV PUT variant) exists but is
  **not** wired into the current compose files.

### Latency vs. goodput semantics

- `latency_tcp_rtt` — TCP connect time (transport only).
- `tls_handshake_s` — TLS handshake on top of that connection (TLS runs only).
- `latency_ttfb` — time to first response byte (headers). For the PUT it
  includes server processing of the uploaded body; for the GET it is the
  request → first byte of the download.
- `goodput_mbps` — `file_size × 8 / transfer_time` where transfer_time spans
  request-start to the last byte (GET) or response-end (PUT).

---

## TLS variant (`runner.py --tls`) — HTTPS and MQTT over TLS

Implemented for `http`, `http-get` and `mqtt` (the minimum TLS set of the
v2 plan); other protocols reject `--tls`.

- **Certificates.** `scripts/gen_certs.sh` creates a self-signed test CA and one
  server certificate (SAN `http-server`, `mosquitto-broker`) in `certs/`
  (git-ignored). `runner.py --tls` runs it automatically in the pinned netshoot
  image when `certs/ca.crt` is missing. The CA carries explicit
  `basicConstraints`/`keyUsage`, because Python 3.13 verifies certificates
  strictly.
- **Switch.** `--tls` sets `TLS=1` for the stack and the harness, appends
  `_tls` to the run id and records `"tls": true` in `run.json`.
- **HTTP.** gunicorn binds `0.0.0.0:8443` with `server.crt/key`; the client
  uses `https://http-server:8443` verified against `certs/ca.crt`.
  `tls_handshake_s` = handshake time on a bare socket after the TCP connect.
- **MQTT.** `MOSQUITTO_CONF=mosquitto-tls.conf` makes the broker listen on 8883
  with the same certificate; both clients call `tls_set(ca_certs=...)`.
  Sender rows record the publisher's handshake (server side, clean link);
  receiver rows record the **device's** handshake over the constrained link,
  measured once at `client-b` startup (one persistent connection, so TLS setup
  is a per-connection cost, not a per-transfer one).
- **pcap analysis.** The payload protocol is encrypted, so
  `TLS_PROTOCOL_CONFIG` in `common/pcap_analyzer.py` selects frames by port
  (`tcp.port == 8443` / `8883`) and the frame-type breakdown reports
  `ENCRYPTED`.
- Evidence: `output/evidence/tls-checks.txt` (ClientHello present, 0
  plaintext `http`/`mqtt` frames, strict certificate verification OK).

---

## CoAP — blockwise PUT (aiocoap)

### Client: `protocols/CoAP/client/coap_client.py`

- Server: `coap://coap-server/upload` (UDP 5683).
- **Latency** — `get_latency()` issues `GET /.well-known/core` (a standard
  discovery endpoint every server serves) and times the round-trip. This avoids
  a GET to a PUT-only resource that would answer `4.05 Method Not Allowed`.
- **Transfer** (`transfer_file`):
  1. Reads the **entire file into memory** (`payload = f.read()`) — aiocoap
     requires the full payload for automatic blockwise transfer. This is the
     primary RAM cost for large files (comment in the source).
  2. `Message(code=PUT, payload=payload, uri=...+"?file=<name>&checksum=<hex>")`.
  3. aiocoap negotiates **blockwise** (RFC 7959) automatically: the request
     carries a `Block1` option and the server answers `2.31 Continue` per block
     until the last one, which gets the final response.
  4. `MAX_RETRIES = 3` application-level attempts with exponential back-off
     `sleep(2 ** attempt)` on exceptions.
  5. `integrity_ok = response.code.is_successful()` — the server returns
     `2.04 Changed` only when it saved the file with a matching checksum.
  6. Writes a CoAP row.
- CLI: `--file <name>`; sleeps 5 s on startup.

### Server: `protocols/CoAP/server/coap_server.py`

- `BinaryUploadResource.render_put` parses `file=` and `checksum=` from the
  URI query (`split("=", 1)` so filenames containing `=` still work), computes
  SHA-256 of the assembled payload, returns `4.00 Bad Request` on mismatch or
  `2.04 Changed` on success, and saves via `common/file_manager.save_file`.
- Bound to `("0.0.0.0", 5683)`.

### Retransmissions and why they matter

CoAP runs over UDP, so reliability comes from the **CoAP layer**: Confirmable
(CON) requests are retransmitted with the same Message ID (MID) until the ACK
arrives, up to `MAX_RETRANSMIT` times (aiocoap `messagemanager.py`). Under the
lossy chaos profiles these retransmissions are real and measurable — see
[pcap-analysis.md](pcap-analysis.md) for how the analyzer detects them (the
subtlety: an ACK **echoes the request's MID**, so raw MID counting over-counts).

---

## AMQP — chunked publish over RabbitMQ with publisher confirms

### Sender: `protocols/AMQP/client/amqp_client.py`

- Broker: `rabbitmq-broker:5672` (`rabbitmq:3-alpine`).
- Queues (same contract as MQTT topics):
  - `file/control` — JSON metadata: `{filename, total_chunks, checksum}`
  - `file/data` — raw 1 MiB binary chunks
- **Reliability**: `channel.confirm_delivery()` — every `basic_publish` blocks
  until the broker confirms (at-least-once, analogous to MQTT QoS 1). pika ≥1.1
  raises `UnroutableError`/`NackError` on failure; success returns `None`.
- **ACK latency**: timing the blocking metadata `basic_publish` yields a real
  broker round-trip, recorded separately in `latency`.
- **Timing**: the timed sender window covers only the chunk publishes — the
  metadata publish+confirm happens before the timer starts, so a lost metadata
  confirm can no longer inflate `sender_duration`.

### Receiver: `protocols/AMQP/receiver/amqp_receiver.py`

- Persistent consumer on both queues with `basic_qos(prefetch_count=32)` to
  bound memory during large transfers.
- Reassembles chunks into `OUTPUT_DIR/<filename>` and verifies the SHA-256;
  appends its own receiver row (`integrity_ok`) to `amqp_measurements.csv`.
- **Single-chunk transfers** (file ≤ 1 chunk) record `receiver_duration="X"`
  and `goodput_mbps="X"` — a single chunk spans no measurable arrival window
  (the old sub-millisecond windows produced fake 1500+ Mbps rows).

### Wire notes

- tshark dissects AMQP natively (`-Y amqp`); the frame-type breakdown uses
  `amqp.type`. RabbitMQ negotiates `frame_max` (131072 by default), so large
  chunks are split into multiple body frames on the wire.
- TCP-based: retransmission metrics come from the standard
  `tcp.analysis.*` filter.

> **Reading broker-topology overhead numbers:** for MQTT and AMQP the capture
> sidecar shares the *broker's* network namespace, so each pcap contains both
> data legs (publish + delivery) plus confirm/ack traffic. Wire bytes of
> roughly **2x the file size (~114% overhead)** at large sizes are therefore
> expected and consistent across both protocols. Client/server-topology
> protocols (HTTP, gRPC) only carry one data leg through their capture point,
> so their overhead percentages are not directly comparable to broker-based
> ones without normalizing for the topology difference.

---

## gRPC — client-streaming upload over plaintext HTTP/2

### Schema: `protocols/GRPC/proto/file_transfer.proto`

- `Upload(stream Chunk) returns UploadResult` — client-streaming RPC.
- `Chunk` is a `oneof { Metadata metadata | bytes data }`: chunk 1 carries
  `{filename, total_size, total_chunks, checksum}`, the rest carry raw bytes.
- `Ping(PingRequest) returns PingReply` — unary round-trip latency probe
  (mirrors the HTTP TCP-RTT measurement).

### Server: `protocols/GRPC/server/grpc_server.py`

- Reassembles the stream into `OUTPUT_DIR/<filename>`, checks size + SHA-256,
  and returns `UploadResult{integrity_ok, receiver_duration_s}` so both sides
  log rows (`grpc_measurements.csv`).

### Stub generation

- Compiled during the docker build (`grpc_tools.protoc`) into `/opt/grpc_stubs`
  — deliberately **outside** `/app`, because the compose stacks bind-mount
  `./:/app` at runtime and would shadow stubs generated inside the image's
  `/app`. Both server and client prepend that directory to `sys.path`
  (falling back to `protocols/GRPC/proto/` for local runs).

### Wire notes

- Plaintext h2c is not auto-detected by tshark on custom ports (only via
  HTTP-upgrade or TLS ALPN), so `PROTOCOL_CONFIG["grpc"]` adds
  `decode_as: ["-d", "tcp.port==50051,http2"]`; the frame-type breakdown then
  shows HTTP/2 frame types (`0` DATA, `1` HEADERS, `4` SETTINGS, `6` PING,
  `8` WINDOW_UPDATE).

---

## LwM2M — firmware-update flow emulator over CoAP

**This is a flow-level emulation**, not a full OMA LwM2M stack: it reproduces
the wire patterns of an LwM2M firmware update using aiocoap (RFC 7252 +
blockwise RFC 7959), without DTLS or the OMA TLV/CBOR serialization. It exists
to measure the management-layer overhead *delta* against the raw CoAP blockwise
benchmark above.

### Flow (one run = one file)

| Step | Message | Notes |
|---|---|---|
| 1 | Client → `POST coap://lwm2m-server/rd?ep=...&lt=86400` | registration; server answers `2.01 Created` with `Location: /rd/1` |
| 2 | Client → `POST coap://lwm2m-server/update?file=...&checksum=...` | benchmark trigger |
| 3 | Server → `PUT coap://<client>/5/0/1` | Package URI write (**server-initiated**) |
| 4 | Client → `GET <package uri>` | blockwise pull of the model object |
| 5 | Client → `PUT /rd/1/5/0/3` payload `"2"` | state report: Downloaded |
| 6 | Server → `POST coap://<client>/5/0/2` | Update Execute |
| 7 | Client → `PUT /rd/1/5/0/3` payload `"1"` | final result report |

### Implementation notes

- Both endpoints use one aiocoap context that serves their site **and**
  originates requests, so server-initiated writes arrive on the device's
  well-known UDP port 5683.
- The firmware repository lives at `coap://lwm2m-server/fw?name=<filename>`
  — a query parameter, not a path segment, because aiocoap's `Site` dispatches
  unknown child paths to 4.04 before a plain `Resource` ever sees them.
- Metrics (client-side row in `lwm2m_measurements.csv`): registration RTT,
  blockwise download duration, goodput, integrity of the pulled object.

---

## Shared helpers

| Helper | Purpose |
|---|---|
| `common/integrity_checker.py` | `sha256(bytes)` and streaming `compute_sha256_file(path)` (1 MiB read chunks) |
| `common/file_manager.py` | `DATA_DIR`/`OUTPUT_DIR` from env (defaults `./data`, `./output`); `load_binary_files()` sorted by size; `save_file()`; `get_file_path_input/output`; `output_directory_exists()` |
| `common/resource_monitor.py` | CPU/RAM sampler (see [metrics-schema.md](metrics-schema.md)) |
