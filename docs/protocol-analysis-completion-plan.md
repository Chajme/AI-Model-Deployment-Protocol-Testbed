# Protocol analysis — completion plan and acceptance criteria

*Written 2026-11-22. It is based on the review in
`learning-iot-edge-ai-model-deployment/docs/thesis-review.md` §5 and on reading this
repository. Every path below is relative to the repo root, and every line number was
checked against the code on that date.*

## Goal

Make the existing measurements defensible for thesis goal 1: *compare protocols for
transferring files that represent AI models*. That needs:

- repeated runs over fairly shaped links;
- device-style downloads;
- one TLS variant;
- cellular profiles that match the field test (an ESP32 with a cellular modem and a SIM).

**Non-goals.** These are documented as limitations instead:

- re-running every legacy protocol × profile × size combination;
- rewriting CoAP/LwM2M to send blocks concurrently (NSTART > 1);
- AMQP pipelining;
- payloads below 250 KB. On most profiles the protocols barely differ at those sizes,
  and 250 KB already matches the ESP32-C6 256 KB model slot.

**Ground rule.** Runs made before this plan are archived as `legacy-v1`. They are
**never mixed** with new runs in the same table.

- Legacy **MQTT/AMQP** runs are invalid under the shaping model in Phase 1.
- Legacy HTTP, CoAP, gRPC and LwM2M runs already follow that model. They are
  superseded only because the new runs have n = 5.

---

## Phase 0: Freeze and make the results reproducible

### Step 0.1 Freeze the legacy results

- Tag the current commit `analysis-v1-legacy`.
- Note in `ISSUES.md` that all runs in `output/runs/` up to that tag use the legacy
  shaping, in which the MQTT/AMQP device link was unshaped (OPEN-5).

### Step 0.2 Pin dependencies

- In `requirements.txt` (and `requirements-charts.txt`), pin the versions currently in
  `.venv`: `paho-mqtt==2.1.0`, `aiocoap==0.4.17`, `flask==3.1.3`, `Werkzeug==3.1.8`,
  `requests==2.32.5`, `psutil==7.2.2` and `matplotlib==3.11.1`.
- Add `pika`, `grpcio` and `grpcio-tools` with the versions from `pip freeze`.
- Remove `uvicorn`, which nothing uses.
- Pin the images in `docker-compose.automated.yaml` and `docker-compose.yaml`:
  - `eclipse-mosquitto:latest` → a fixed 2.0.x tag;
  - `rabbitmq:3-alpine` → a fixed 3.13.x-alpine tag;
  - `nicolaka/netshoot` → a fixed tag. Also update the fallback in
    `common/pcap_analyzer.py:66`.

### Step 0.3 Record provenance in each run

`runner.py` passes a `meta` dict to `runs.new_run()` (`common/runs.py:147`) with:

- `pip_freeze`;
- the image digests, from `docker image inspect --format '{{json .RepoDigests}}'`;
- `git_commit`.

### Verify

- `docker compose -f docker-compose.automated.yaml build` succeeds.
- A new `run.json` contains `pip_freeze`, `images` and `git_commit`.

---

## Phase 1: Fair network shaping (closes OPEN-5)

### The shaping model: a bidirectional access link

There is exactly **one constrained link**: between the edge device (the side that
receives the model) and the endpoint it gets the data from. That link is constrained
**in both directions**. Every other link stays unconstrained, such as the backend or
the server/CI side publishing into the broker.

`tc` netem only shapes a container's outgoing traffic. So "both directions" means
shaping the outgoing traffic of **both endpoints of that link** with the same profile.
The profile values are therefore per direction, and the round-trip time is about
2 × the netem delay.

### Step 1.0 What the code does today (verified 2026-11-22)

| Protocol | Link(s) the data crosses | Shaped today | Matches the model? |
|---|---|---|---|
| HTTP, CoAP, gRPC, LwM2M | client ↔ server: one link, with its own network per protocol | Outgoing traffic of both client and server. Both run `network_chaos.sh` (for example `docker-compose.automated.yaml` lines 66-98). | **Yes.** Both directions are shaped, so no change is needed. |
| MQTT, AMQP | publisher (`client-a`) → broker → device (`client-b`) | `client-a`'s outgoing traffic (the data, but on the *backend* hop) and `client-b`'s (acknowledgements only). **The broker's outgoing traffic is not shaped**; the stock image has no `tc` (lines 6-13). | **No.** The data reaches the device over an unshaped link. Evidence: the receiver logged 1724 Mbps under `harsh` (OPEN-5). |

The "agreed target design" previously written in OPEN-5 (unshape the servers, shape
only the senders) is **dropped**. It would have reduced the correct HTTP/CoAP/gRPC
shaping to one direction, and it would still have shaped the wrong MQTT hop.

### The fix for MQTT/AMQP

This needs one network and no topology change:

- Shape `client-b`'s outgoing traffic (device → broker). This is already done.
- Shape the broker's outgoing traffic **towards `client-b` only** (broker → device).
- Leave `client-a` (the server/publisher) unshaped.

**Why "towards `client-b` only".** The broker has one network interface. Its outgoing
traffic goes to two places:

- to `client-b`: the model data, which must be constrained;
- to `client-a`: PUBACKs back to the server, which must stay fast if the
  server ↔ broker link is a good network.

A filter that matches only packets addressed to `client-b` keeps the second stream
clean.

### Step 1.1 Add destination-only shaping to the script

In `scripts/network_chaos.sh`:

1. Add a `none` arm to the profile `case` statement (lines 73-92) that applies no
   `tc`. `client-a` uses it.
2. Add an optional variable `SHAPE_DST=<hostname>`.
   - Without it, the script behaves as today and shapes all of `eth0`'s outgoing
     traffic.
   - With it, the script:
     1. resolves the IP with `getent hosts "$SHAPE_DST"`, retrying for up to 30 s
        until that container is up;
     2. installs a `prio` root that sends default traffic to an **unshaped** band;
     3. attaches the profile's netem + tbf under a separate band;
     4. adds a `u32` filter that sends only packets addressed to that IP to the
        shaped band:

     ```sh
     tc qdisc add dev eth0 root handle 1: prio bands 3 priomap 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
     tc qdisc add dev eth0 parent 1:3 handle 30: netem <profile netem args>
     tc qdisc add dev eth0 parent 30:1 handle 31: tbf <profile tbf args>
     tc filter add dev eth0 parent 1:0 protocol ip prio 1 u32 match ip dst "$DST_IP"/32 flowid 1:3
     ```

3. Refactor each `apply_<profile>()` (lines 11-71) so that it only sets its netem and
   tbf argument strings. One shared function then installs them, either at the root
   (today's behaviour) or under `1:3` (destination mode). That way the profile
   values aren't duplicated.

### Step 1.2 Run it from the existing capture sidecar

The broker images have no `tc` and no `NET_ADMIN`. The existing `mqtt-capture`
sidecar (`docker-compose.automated.yaml` lines 52-61) already shares the broker's
network namespace (`network_mode: "service:mosquitto-broker"`, `cap_add: NET_ADMIN`),
and netshoot ships `tc` and `getent`.

Give the sidecar:

- `volumes: ./scripts:/app/scripts:ro`;
- `entrypoint: ["/app/scripts/network_chaos.sh"]` instead of `sleep infinity`. The
  script already sleeps forever when `APP_COMMAND` is empty (lines 98-102).
- `environment: NETWORK_PROFILE=${NETWORK_PROFILE}`, `SHAPE_DST=mqtt-client-b`;
- `depends_on: mqtt-client-b`.

Then:

- Do the same for the AMQP capture sidecar, with `SHAPE_DST=amqp-client-b`.
- Add a compose comment: "this sidecar also shapes the broker's traffic to the
  device — don't remove it".

No new service is needed, and the broker image is unchanged.

### Step 1.3 Unshape the publisher

- Set `NETWORK_PROFILE=none` for `mqtt-client-a` (lines 31-32) and `amqp-client-a`.
  These stand for the server/CI side, which sits in a good network.
- `client-b` stays unchanged; it is the device.

### Step 1.4 Capture only the device leg

- Add an optional BPF filter argument to `start_capture_run()` in
  `common/packet_capture.py` (the tcpdump call at lines 85-89).
- For MQTT/AMQP, pass `host mqtt-client-b` (or `host amqp-client-b`).
- The pcap then contains only the device leg, so overhead is computed against one
  file size for one leg. The ~115 % two-leg artefact disappears.

### Step 1.5 Keep old runs out of the new tables

- The report generator (`scripts/export_measurements.py`, `load_runs()` at line 74)
  reads every run in `output/runs/`. It picks the newest complete run per protocol
  and profile.
- If the old MQTT/AMQP runs stay in that folder, a new table could mix old and new
  numbers.
- Before the first new run, move all existing runs to `output/runs-legacy-v1/`. If an
  appendix ever needs the old numbers, point the export at that folder explicitly.

### Step 1.6 Document it

- Rewrite the shaping section of `docs/network-chaos.md` (§2, from line 83) with the
  model above, including the table from Step 1.0.
- Update the export footnote about OPEN-5 (`scripts/export_measurements.py` around
  line 710).
- Move OPEN-5 to FIXED in `ISSUES.md`. Note that the earlier "agreed design" was
  dropped, and why.
- State the assumptions:
  - The same profile values apply in both directions; there is no uplink/downlink
    asymmetry.
  - For upload-style protocols (HTTP PUT, CoAP PUT, gRPC streaming) the shaping is
    symmetric, so the result doesn't depend on which end plays the device.

*Optional:* add `NETWORK_DIRECTION=up|down`, so the device's outgoing traffic uses the
uplink rate and the source's uses the downlink rate. This is needed only if the
cellular calibration (Phase 5) shows a clear asymmetry.

### Verify

Save all output to `output/evidence/shaping-check.txt`.

1. `docker compose -f docker-compose.automated.yaml config` shows
   `NETWORK_PROFILE=none` on both `client-a` services and `SHAPE_DST` on the capture
   sidecars.
2. In a running `mqtt` stack on the `iot` profile:
   - `docker compose exec mqtt-capture tc qdisc show dev eth0` shows `prio` with
     netem + tbf under `1:3`;
   - `docker compose exec mqtt-capture tc filter show dev eth0` shows a u32 match on
     `mqtt-client-b`'s IP.
3. Round-trip times from the broker's network namespace (the capture sidecar has
   `ping`), on the `good` profile (40 ms delay per direction):
   - `ping -c 20 mqtt-client-b` gives a median of about 80 ms;
   - `ping -c 20 mqtt-client-a` gives a median under 2 ms.
4. The same check for a direct protocol: from `http-capture`,
   `ping -c 20 http-client` gives about 80 ms.
5. A 1 MB MQTT transfer on `iot`: the goodput measured by the **receiver** is at most
   0.512 Mbit/s and close to the sender's. Before the fix it was hundreds or
   thousands of Mbit/s.
6. Repeat checks 2, 3 and 5 for AMQP.

---

## Phase 2: Payload sizes per profile

The existing payloads stay: 250 KB, 1 MB, 5 MB, 20 MB and 50 MB. No smaller files are
added.

### Step 2.1 Add a size filter to the runner

- Add `--sizes` to `runner.py` (for example `--sizes 250kb,1mb,5mb`).
- Pass it to `benchmark_manager.run_protocol()` (line 145), which today picks up
  every `data/*.bin`. The function already accepts a `files` argument.
- Slow profiles need this, because large files there take hours (see Phase 8 and
  OPEN-4).

### Step 2.2 Let the export accept runs that skip sizes

- Today `sizes_covered()` and `pick_canonical()` (`scripts/export_measurements.py`
  lines 115 and 125) count a run as complete only if it has all five sizes in
  `SIZE_ORDER` (line 49).
- Judge completeness against the run's own `file_sizes` from `run.json` instead. Then
  an `nbiot` run with only 250 KB and 1 MB counts as complete.

### Step 2.3 Precision

- Write durations with `.3f` everywhere.
- MQTT, AMQP and gRPC use `.2f` today (for example
  `protocols/MQTT/clients/client_a.py:131`). That is coarse for a 250 KB transfer on
  `good`, which takes about 0.3 s.

### Verify

- `runner.py --protocols http --profiles good --sizes 250kb,1mb` transfers only those
  two files.
- The export lists that run as complete.

---

## Phase 3: Device-style HTTP GET download with resume

### Step 3.1 Server

In `protocols/HTTP/server/flask_server.py`:

- Add `GET /download/<filename>`, returning
  `send_from_directory("/app/data", filename, conditional=True)`. Werkzeug handles
  `Range` requests and replies 206 itself, so no Range code is needed on the server.
- Replace the development server (`app.run`, line 27) with `waitress.serve(...)`, and
  add `waitress` to `requirements.txt`.
- Make the upload stream from `request.stream` and hash as it goes, instead of
  buffering the whole body in `request.data` (line 10).

### Step 3.2 Client

In `protocols/HTTP/client/http_client.py`, add a download mode:

- Call `requests.get(url, stream=True)` and read with `iter_content(16384)`, hashing
  on the fly and writing to `/tmp`.
- Record:
  - time to first byte (reuse the hook at lines 64-70);
  - total time;
  - the SHA-256, compared with the source file.
- On `ConnectionError` or `ChunkedEncodingError`, retry with
  `Range: bytes=<offset>-` and expect 206. Allow at most 5 resumes.
- Record `resumed` and `bytes_resumed`.

### Step 3.3 Register `http-get` as its own protocol key

The reports need a separate column for it. Add the key to these registries:

- `RUNNERS` in `protocols/benchmark_manager.py` (line 42);
- `CAPTURE_SERVICES` / `OFFLOAD_CONTAINERS` in `common/packet_capture.py`;
- `PROTOCOL_CONFIG` in `common/pcap_analyzer.py` (the `tcp.port == 8000` filter still
  works);
- `PROBE` in `runner.py` (line 34);
- `common/charts.py`.

Also add a CSV writer with the columns `direction`, `resumed` and `bytes_resumed`,
next to `write_to_file_http` in `output/write_csv.py`.

### Step 3.4 Shaping

No special handling is needed. Client and server are both already shaped, so the
link is constrained in both directions (Phase 1.0).

### Verify

1. In the running stack, this command prints `206 100`:
   `curl -s -r 0-99 http://http-server:8000/download/binary_file_250kb.bin -o /dev/null -w "%{http_code} %{size_download}"`
2. An `http-get` run on `good` at all sizes gives `integrity_ok=True`.
3. Resume test:
   1. Start a 1 MB download on `iot`.
   2. Restart the server mid-transfer: `docker compose restart http-server`.
   3. The CSV must show `resumed ≥ 1`, `bytes_resumed` smaller than the file size,
      and `integrity_ok=True`.

   Save the log to `output/evidence/resume-test.txt`.

---

## Phase 4: One TLS variant (HTTPS download and MQTT over TLS)

### Step 4.1 Certificates

- Add `scripts/gen_certs.sh`: an openssl self-signed CA, plus server certificates with
  the SANs `http-server` and `mosquitto-broker`.
- Write them to `certs/` and add that folder to `.gitignore`.

### Step 4.2 Switch

- The environment variable `TLS=1` (runner flag `--tls`) selects the TLS variant.
- Record it in `run.json` as `tls: true`.
- Add a `_tls` suffix to the run id.

### Step 4.3 HTTPS

- **Server.** Waitress has no TLS support. For the TLS variant use
  `gunicorn --certfile/--keyfile`, or Werkzeug's `ssl_context` as a minimum.
- **Client.** Use `https://http-server:8443` with `verify=certs/ca.pem` (`BASE_URL`
  at line 13; the port at line 30).
- **Handshake time.** Measure the time from TCP connect until the TLS wrap finishes,
  in `measure_network_latency()` (lines 22-42). Record it as `tls_handshake_s`.

### Step 4.4 MQTT over TLS

- `protocols/MQTT/mosquitto-broker/mosquitto.conf`: add `listener 8883` with
  `cafile`, `certfile` and `keyfile`. Mount `certs/` in both compose files.
- `client_a.py` `make_client()` (lines 38-42) and `client_b.py` (`PORT` at line 14):
  call `tls_set(ca_certs=...)` and read the port from the environment.
- Update the probe ports in `runner.py` (lines 35-36).

### Step 4.5 pcap analysis

- In `common/pcap_analyzer.py`, use a port-based filter (`tcp.port == 8443` or
  `8883`) when `tls: true`.
- Document that the packet-type breakdown is empty for TLS runs.

### Verify

1. `docker compose exec http-client openssl s_client -connect http-server:8443 -CAfile /app/certs/ca.pem`
   reports `Verify return code: 0`.
2. `tshark -r <pcap> -Y tls.handshake.type==1` shows a ClientHello.
3. `tshark -r <pcap> -Y mqtt` and `-Y http` show **0** plaintext frames.
4. TLS runs give `integrity_ok=True`, and `tls_handshake_s` is present.

---

## Phase 5: Cellular profiles (LTE-M and NB-IoT)

### Step 5.1 Add the profiles

Add `apply_ltem()` and `apply_nbiot()` to `scripts/network_chaos.sh`, plus case arms.
The starting values below come from the literature; recalibrate them once the field
modem exists.

| Profile | netem | tbf | Basis |
|---|---|---|---|
| `ltem` | `delay 75ms 25ms 25%`, `loss 0.5%` | `rate 300kbit burst 16kbit latency 1500ms` | Cat-M1 realistic throughput of about 300 kbit/s (3GPP TS 36.306, UE category M1); RTTs of about 100–200 ms on live networks |
| `nbiot` | `delay 800ms 150ms 25%`, `loss 1%` | `rate 25kbit burst 16kbit latency 8000ms` (burst must be ≥ one full frame) | Cat-NB1 downlink peak of about 26 kbit/s (TS 36.306); 3GPP TR 45.820 latency target ≤ 10 s; field RTTs of about 1–2 s are commonly reported |

Notes:

- Both ends of the link are shaped (Phase 1), so the netem delay is **one-way**. The
  RTT is about 2 × delay: about 150 ms for `ltem` and about 1.6 s for `nbiot`. Loss
  also applies in each direction.
- Keep the jitter moderate. With large jitter, netem reorders packets, which would
  penalise TCP unrealistically.
- Check the sources yourself before citing them in the thesis.
- Recalibrate later on the real SIM by measuring:
  - the `ping` RTT;
  - a 250 KB HTTP download over PPPoS.

### Step 5.2 Wire them in

- Add `ltem` and `nbiot` to `PROFILES` in `scripts/export_measurements.py` (line 45).
- Add them, with their sources, to the profile table in `docs/network-chaos.md`
  ("Profile parameters", line 120).

### Step 5.3 Size limits (also addresses OPEN-4)

Use `--sizes` for these limits; don't build them into code.

| Profile | TCP-based protocols | CoAP / LwM2M | Why |
|---|---|---|---|
| `ltem` | up to 5 MB | up to 1 MB | 5 MB at 300 kbit/s is about 2.5 min |
| `nbiot` | 250 KB and 1 MB | 250 KB only | 1 MB at about 25 kbit/s is about 6 min. CoAP needs about 250 blocks × 1.6 s ≈ 7 min for 250 KB; 1 MB would be about 27 min per transfer. |

### Step 5.4 Check client timeouts

- gRPC already scales its deadline with size and expected throughput
  (`grpc_client.py` lines 45-46, `GRPC_MIN_THROUGHPUT_BPS = 32000`). Lower this to
  16000 for `nbiot` through an environment variable.
- When a transfer fails, the CoAP client resends the **whole** file, up to
  `MAX_RETRIES` times (`coap_client.py:15`). Set it to 1 for `nbiot` and record the
  failures.

### Verify

Save the output to `output/evidence/cellular-calibration.txt`.

1. From `http-client`, `ping -c 20 http-server` gives a median RTT within ±20 % of
   150 ms on `ltem` and 1600 ms on `nbiot`.
2. A 250 KB `http-get` reaches about 0.26 Mbit/s goodput or less on `ltem`, and about
   0.024 Mbit/s or less on `nbiot`. If goodput is above the configured rate, the
   shaping isn't working.

---

## Phase 6: Repetitions and statistics

### Step 6.1 Add repetitions to the runner

- Add `--repeat N` and `--sweep-id` to `runner.py` `main()` (line 141).
- For each repetition, shuffle the order of the (protocol, profile) combinations with
  a recorded seed. That way drift over time doesn't favour one protocol.
- Add an `_r{i}` suffix to the run id.
- Record `sweep_id`, `repeat_index` and `seed` in `run.json`.

### Step 6.2 Count failures

- A failed transfer must still write a row. gRPC already does (`grpc_client.py`
  lines 108-110); check the other clients.
- Report the success rate. Don't drop failures silently.

### Step 6.3 Aggregate in the export

In `scripts/export_measurements.py`:

1. Replace `pick_canonical()` (line 125) with "all runs of `--sweep-id`".
2. Make `key_rows()` (line 138) and `pcap_results` map each key to a list of values.
3. Make `make_client_field` and `make_pcap_field` (lines 584 and 602) return lists.
4. Render each cell as **median [Q1–Q3], n, success %**, using
   `statistics.quantiles(n=4)`.
5. Flag cells with n < 5 or success below 100 %.

### Step 6.4 Charts

Add an `iqr` mode to `_error_bounds` in `common/charts.py` (line 238).

### Step 6.5 Unit tests

- Add a minimal `tests/` folder with pytest (pinned in requirements).
- Test the aggregation, the median/IQR formatting and `sizes_covered`, using known
  inputs.

### Verify

1. `pytest tests/` passes.
2. A smoke sweep
   (`--protocols http,http-get --profiles good --sizes 250kb,1mb --repeat 3`)
   produces 3 runs per combination.
3. The export shows n = 3 and IQR brackets.

---

## Phase 7: Honest metrics

### Step 7.1 Remove the energy metric

Remove it from the measurements entirely. It was the host CPU share × an assumed
15 W TDP, which says nothing about a device.

- `common/resource_monitor.py`: delete `DEFAULT_TDP_WATTS` (line 27) and the energy
  calculation in `stop()` (lines 99-100). Keep CPU % and peak RSS.
- `output/write_csv.py`: drop the `energy_est` column from every client schema
  (lines 110, 129, 145, 163, 181 and 198).
- `scripts/export_measurements.py` and `common/charts.py`: drop the energy rows,
  columns and charts.
- `docs/metrics-schema.md` §8 (line 215): remove the energy part, with one line saying
  it was dropped and why.

Device energy is measured only in the field test, on the real ESP32 with a USB or
INA219 meter.

### Step 7.2 Latency

- Rename the latency column of each protocol to what it actually measures (the
  export's `LATENCY_FIELD`, line 572):

  | Protocol | What the "latency" column measures |
  |---|---|
  | HTTP | TCP connect |
  | MQTT | PUBACK |
  | AMQP | publish confirm |
  | CoAP | discovery GET |
  | gRPC | Ping RPC |
  | LwM2M | registration |

- Add a note that these values are **not** comparable across protocols.
- The primary comparison metrics are:
  - transfer time;
  - goodput;
  - wire bytes and overhead;
  - success rate;
  - for downloads, time to first byte and TLS handshake time.

### Step 7.3 MQTT/AMQP overhead per leg

Phase 1.4 covers this: the `host <client-b>` capture filter records only the device
leg. Note in `docs/pcap-analysis.md` that MQTT/AMQP pcaps contain only the device
leg from v2 onwards, while legacy pcaps contain both legs.

### Step 7.4 (optional, small) MQTT windowed publish

- In `client_a.py` `send_chunks()` (line 69), the client currently waits with
  `wait_for_publish()` after every chunk (line 77). Replace that with
  `max_inflight_messages_set(20)` and a single wait on the last message.
- Check the return value of the wait.
- Run it as a separate variant, `mqtt-windowed`. It shows how much of MQTT's plateau
  of about 0.16 Mbps comes from the client implementation.

### Step 7.5 Write the limitations down

Put these in `docs/measurement-pipeline.md` §5 and in the thesis:

- aiocoap sends one block at a time (NSTART = 1), uses 1 KB blocks, and holds the
  whole file in RAM (`coap_client.py` lines 46-47);
- the paho client waits after every 1 MB chunk;
- AMQP confirms each publish synchronously;
- LwM2M is a hand-written emulator without DTLS;
- the same profile values apply in both directions of the access link.

### Verify

1. Running the export against `output/runs-legacy-v1/` reproduces the old numbers.
   Only the column labels change, and the energy column is gone.
2. A new MQTT run on `good` (device-leg capture) shows an overhead in the
   single-digit-to-low-tens % range, instead of about 115 %.

---

## Phase 8: The re-run matrix (minimum set, n = 5, fixed shaping)

The TCP-based protocols are http (PUT), http-get, mqtt (QoS 1), grpc and amqp. CoAP
and LwM2M need one round trip per 1 KB block, so they get smaller size limits
(OPEN-4).

| Profile | TCP-based protocols | CoAP / LwM2M |
|---|---|---|
| good | 250 KB, 1, 5, 20, 50 MB | 250 KB, 1, 5 MB |
| iot, mobile, harsh | 250 KB, 1, 5 MB | 250 KB, 1 MB |
| ltem | 250 KB, 1, 5 MB | 250 KB, 1 MB |
| nbiot | 250 KB, 1 MB | 250 KB |
| TLS rows (good, ltem, nbiot) | http-get + TLS and mqtt + TLS, same sizes as the profile | — |
| *(optional)* good, iot, ltem | mqtt-windowed, same sizes as the profile | — |

**Dropped from the main tables:**

- satellite, which isn't relevant to a cellular field test;
- MQTT QoS 2;
- 20 MB and 50 MB on impaired profiles.

Their legacy results stay in an appendix (`output/runs-legacy-v1/`). The large sizes
are still measured on `good`, where they show the protocol differences best. On
impaired links they would take hours per transfer, and they are far above any ESP32
model.

**Missing results from the old runs:** the gaps in gRPC `mobile` and gRPC `iot` 50 MB
came from an old fixed 600 s deadline. The current code already scales the deadline,
and the new matrix covers both.

**Runtime:** NB-IoT and CoAP/LwM2M dominate. Expect roughly 15–25 hours unattended
(one weekend). Run each profile as its own `--sweep-id` batch, so a crash loses only
that batch.

---

## Phase 9: Write-up

1. Regenerate `output/measurements_comparison.md` and `output/measurements_export.md`
   from the new sweep ids only.
2. **Re-check the conclusion.** Does "HTTP(S) download for artifacts + MQTT for
   control" still hold on `ltem` and `nbiot` with TLS? If CoAP or LwM2M are
   competitive at 250 KB on NB-IoT, make the thesis recommendation depend on the link
   type. That is still a valid result.
3. The thesis chapter "Analýza protokolov" should contain:
   - **Method:**
     - the topology;
     - the bidirectional access-link shaping model (one constrained link between the
       device and its data source; all other links clean);
     - the profiles, with sources;
     - n and the statistics used;
     - the pinned versions.
   - **Results:** tables with median [IQR] and success rate.
   - **Overhead:** per leg.
   - **TLS cost.**
   - **Library caveats.**
   - **Threats to validity.**
4. Tag the final state `analysis-v2`.

---

## Definition of done

Tick every box; each one names its evidence.

- [ ] The `analysis-v1-legacy` tag exists. Dependencies and images are pinned.
      `run.json` contains `pip_freeze`, `images` and `git_commit`.
- [ ] OPEN-5 is moved to FIXED: the bidirectional access-link model is in place, and
      the earlier "agreed design" is recorded as dropped.
- [ ] All pre-fix runs are moved to `output/runs-legacy-v1/`.
- [ ] MQTT/AMQP broker traffic is shaped towards `client-b` only (prio + u32 from the
      capture sidecar), and the publishers are unshaped.
- [ ] `output/evidence/shaping-check.txt` holds the `tc qdisc show` output and the RTT
      checks: device link ≈ 2 × delay, backend link < 2 ms.
- [ ] `runner.py --sizes` exists, the export accepts runs with fewer sizes, and
      durations are written with three decimals.
- [ ] `http-get` results exist for every profile in the matrix.
- [ ] The `206 100` curl check and the resume test are saved in `output/evidence/`.
- [ ] TLS rows exist for http-get and mqtt on good, ltem and nbiot, including
      `tls_handshake_s`.
- [ ] The tshark check shows 0 plaintext frames in TLS runs.
- [ ] `ltem` and `nbiot` are in `network_chaos.sh` and in `docs/network-chaos.md`,
      with cited sources.
- [ ] The ping and goodput calibration is saved in
      `output/evidence/cellular-calibration.txt`.
- [ ] Every main-table cell shows median [IQR], n ≥ 5 and success %.
- [ ] `pytest tests/` passes.
- [ ] The energy metric is removed from code, CSVs, reports and docs.
- [ ] The latency columns are renamed.
- [ ] MQTT/AMQP overhead is reported for the device leg only.
- [ ] The library and shaping limitations are written in
      `docs/measurement-pipeline.md` and in the thesis chapter.
- [ ] The reports are regenerated from the v2 sweeps only.
- [ ] The conclusion has been re-checked against `ltem` and `nbiot`.
- [ ] The `analysis-v2` tag exists.
- [ ] I have checked the sources behind the cellular profile values myself.

**Effort:** about 5–7 days of code changes (Phases 0–7), plus one weekend of
unattended runs (Phase 8). This fits December, before the January exam period.

---

## Implementation status (2026-11-23, branch `feat/protocol-analysis-v2`)

Phases 0–7 are implemented and smoke-tested. Phase 8 (the full n = 5 matrix,
about 15–25 h unattended) and Phase 9 (the thesis write-up) are still to do.
Run the matrix with `python scripts/run_v2_matrix.py` (it prints its commands
with `--dry-run`), then
`python scripts/export_measurements.py --sweep-id v2-good v2-iot v2-mobile v2-harsh v2-ltem v2-nbiot`.

### Definition of done — current state

| Item | State | Evidence |
|---|---|---|
| Legacy tag, pinned dependencies/images, provenance in run.json | Done (tag `analysis-v1-legacy` is local, not pushed) | any new `run.json` (`git_commit`, `images`, `pip_freeze`) |
| OPEN-5 fixed, legacy runs moved, broker shaped towards `client-b`, publishers unshaped | Done | `output/evidence/shaping-check.txt`, `output/evidence/broker-delivery-check.txt`, ISSUES.md FIXED-15 |
| `--sizes`, export accepts fewer sizes, 3-decimal durations | Done | `tests/test_export.py`, `tests/test_runner_sizes.py` |
| `http-get` results for every matrix profile | Code done; good, ltem, nbiot smoke-tested; full matrix pending (Phase 8) | `output/evidence/smoke-comparison.md` |
| `206 100` check and resume test | Done | `output/evidence/http-get-checks.txt` |
| TLS rows for http-get and mqtt on good, ltem, nbiot | Code done; good tested; ltem/nbiot pending (Phase 8) | `output/evidence/tls-checks.txt` |
| 0 plaintext frames in TLS runs | Done | `output/evidence/tls-checks.txt` |
| `ltem`/`nbiot` profiles documented with sources | Done; **sources still need your check** | `docs/network-chaos.md` |
| Ping and goodput calibration | Done | `output/evidence/cellular-calibration.txt` |
| Every main-table cell median [IQR], n ≥ 5, success % | Report done (n = 3 smoke sweep verified); n = 5 needs Phase 8 | `output/evidence/smoke-comparison.md` |
| `pytest tests/` passes | Done (25 tests) | `python -m pytest tests` |
| Energy removed; latency columns renamed; device-leg overhead | Done | `output/evidence/export-legacy-check.txt` (legacy numbers unchanged), `broker-delivery-check.txt` (~11 % overhead) |
| Limitations in `docs/measurement-pipeline.md` | Done; thesis chapter is yours | `docs/measurement-pipeline.md` §5 |
| Reports from v2 sweeps only, conclusion re-checked, `analysis-v2` tag | Pending (Phases 8–9) | — |
| Cellular source check | Pending (yours) | — |

### Deviations from the plan

- **HTTP server:** gunicorn serves both the plain and the TLS variant (the plan
  said waitress for plain). The two variants then differ only in TLS.
- **Certificate check:** the strict Python `ssl` verification from
  `http-client` replaces `openssl s_client` (the client image has no openssl
  CLI). It applies Python 3.13's strict X.509 rules, which is stricter.
- **Legacy separation:** runs moved to `output/runs-legacy-v1/` (Step 1.5).
  `shaping_model: access-link-bidir-v2` is still recorded in each new run.json.
- **MQTT/AMQP transfer view (new).** The publisher sits on the clean link, so
  its own time (~0.06 s for 5 MB) is not the constrained transfer. The harness
  now waits for the device's verified row, and the v2 report uses the
  receiver's delivery time (metadata arrival → verified) for MQTT/AMQP.
- **RabbitMQ settings (new):** `send_timeout` and `heartbeat` raised to 600 s.
  RabbitMQ otherwise resets a slow consumer on the shaped device link.
- **`nbiot` tbf burst:** 16kbit instead of 4kbit. 4kbit (512 B) is smaller than
  one frame, so every full-size segment was dropped.
- **MQTT TLS handshake:** also recorded on the device side (`client-b`, once per
  connection), because the publisher's handshake is on the clean link.
- **Optional `mqtt-windowed`:** implemented. Smoke result on iot: same delivery
  goodput as plain MQTT (0.480 vs 0.473 Mbit/s). Under the v2 model the
  device link, not the client's per-chunk wait, limits MQTT.
