# Protocol transfer internals

Each protocol has a distinct on-the-wire behavior and a distinct latency
metric. This page documents the client and server code for all three.

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
  4. **ACK latency**: `on_publish` fires when the broker acknowledges the
     control message (`mid == metadata_mid`); `ack_latency = now - sent_time`.
     Waits up to 10 s (`metadata_ack_event.wait(timeout=10)`).
  5. `send_chunks()` publishes every 1 MiB chunk with
     `msg_info.wait_for_publish(timeout=60)` per chunk — one publish round-trip
     per chunk (this is why MQTT goodput is low for large files).
  6. Duration is wall-clock from before the control message to after the last
     chunk; `goodput_mbps = file_size × 8 / (duration × 1e6)`.
  7. Writes a `side=sender` row (no CPU/RAM/energy columns for MQTT).
- CLI: `--file <name> --qos <1|2>` (both required); sleeps 5 s on startup for
  the broker.

### Receiver: `protocols/MQTT/clients/client_b.py`

- Connects with retries (`_connect_with_retries`, 15 attempts × 2 s) and
  subscribes to both topics at `qos=2` (the effective QoS is whatever the
  sender used).
- On `file/control`: stores metadata, resets state, opens the output file.
  Warns + closes the stale handle if a previous transfer was incomplete.
- On `file/data`: writes payload, tracks bytes/chunks. **First-chunk latency** =
  `time.perf_counter() - metadata_arrival_time`.
- On the final chunk: computes duration, verifies the received file's SHA-256
  against the metadata checksum, and writes a `side=receiver` row with
  `integrity_ok`.

### CSV rows produced

Two rows per transfer — one from the sender, one from the receiver — each with
its own `duration` and `latency` definition. `charts.py` defaults to the sender
row (`--mqtt-side sender`).

---

## HTTP — streaming PUT with server-side checksum

### Client: `protocols/HTTP/client/http_client.py`

- Server: `http://http-server:8000` (Flask).
- **Latency (TCP RTT)** — `measure_network_latency()` opens a bare TCP socket
  to `http-server:8000`, times the connect, closes. No HTTP, no server
  processing — a clean RTT.
- **TTFB** — a `requests` response hook (`record_ttfb`) fires as soon as the
  response headers arrive and records `elapsed from request_start`.
- **Transfer** (`transfer_file`):
  1. Streams the file with `requests.put(BASE_URL + "/upload/" + filename,
     data=file_stream, headers={"X-Checksum": checksum}, hooks=...)`.
     The file is streamed from disk (`open(..., "rb")` as the body), so memory
     stays flat regardless of file size.
  2. `integrity_ok = (put_response.status_code == 200)` — the *server* decided
     checksum equality.
  3. `ResourceMonitor(sample_interval=0.01)` wraps the transfer for CPU/RAM/energy.
  4. Writes an HTTP row.
- CLI: `--file <name>`; sleeps 5 s on startup.

### Server: `protocols/HTTP/server/flask_server.py`

```python
@app.route("/upload/<filename>", methods=["PUT"])
def upload(filename):
    actual = sha256(request.data)          # whole-body checksum
    if expected != actual: return 400
    save_file(filename, data=request.data)
    return 200
```

- `request.data` buffers the full body in memory on the server (the client
  streams, but the Flask dev server reads it whole — noted as a server-side RAM
  cost for very large files).
- A legacy `protocols/HTTP/server/nginx.conf` (WebDAV PUT variant) exists but is
  **not** wired into the current compose files.

### Latency vs. goodput semantics

- `latency_tcp_rtt` — connection-setup RTT (transport only).
- `latency_ttfb` — time to first response byte (headers), includes server
  processing of the uploaded body.
- `goodput_mbps` — `file_size × 8 / transfer_time` where transfer_time spans
  request-start to response-end.

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

## Shared helpers

| Helper | Purpose |
|---|---|
| `common/integrity_checker.py` | `sha256(bytes)` and streaming `compute_sha256_file(path)` (1 MiB read chunks) |
| `common/file_manager.py` | `DATA_DIR`/`OUTPUT_DIR` from env (defaults `./data`, `./output`); `load_binary_files()` sorted by size; `save_file()`; `get_file_path_input/output`; `output_directory_exists()` |
| `common/resource_monitor.py` | CPU/RAM/energy sampler (see [metrics-schema.md](metrics-schema.md)) |
