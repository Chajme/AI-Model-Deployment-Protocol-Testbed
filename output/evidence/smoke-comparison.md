# Protocol Comparison — Benchmark Measurements

Generated: 2026-11-23 12:48 UTC · analyzer at commit `a1c51a4` · payloads: 250 KB – 5 MB

Companion to `measurements_export.md` — same runs, same re-analyzed pcaps; per-protocol detail, receiver-side views and per-row samples live there.

## Headline: client goodput (Mbps) at 5 MB

| Profile | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| good | — | — | — | — | — | — | — | — |
| iot | 0.473 n=1 100%† | 0.48 n=1 100%† | — | — | — | 0.48 n=1 50%† | — | — |
| ltem | — | — | — | — | — | — | — | — |
| nbiot | — | — | — | — | — | — | — | — |

## Headline: client goodput (Mbps) at 250 KB

| Profile | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| good | 5.657 n=1 100%† | — | 3.799 [3.718–3.84] n=3 100%† | 3.918 [3.824–4.001] n=3 100%† | 0.09 n=1 100%† | 5.654 n=1 100%† | 4.474 n=1 100%† | 0.067 n=1 100%† |
| iot | — | — | — | — | — | — | — | — |
| ltem | — | — | — | 0.268 n=1 100%† | — | — | — | — |
| nbiot | — | — | — | 0.022 n=1 100%† | — | — | — | — |

## Headline: wire overhead % at 5 MB (pcap)

| Profile | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| good | — | — | — | — | — | — | — | — |
| iot | 11.74 n=1 100%† | 10.98 n=1 100%† | — | — | — | 11.05 n=1 50%† | — | — |
| ltem | — | — | — | — | — | — | — | — |
| nbiot | — | — | — | — | — | — | — | — |

## Profile: good

### Transfer time (s)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 0.362 n=1 100%† | — | 0.539 [0.5335–0.551] n=3 100%† | 0.523 [0.5125–0.536] n=3 100%† | 22.78 n=1 100%† | 0.362 n=1 100%† | 0.458 n=1 100%† | 30.39 n=1 100%† |
| 1 MB | 2.211 n=1 100%† | — | 1.238 [1.227–1.267] n=3 100%† | 1.172 [1.171–1.193] n=3 100%† | 94.17 n=1 100%† | 1.043 n=1 100%† | 1.152 n=1 100%† | 93.6 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

### Client goodput (Mbps)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 5.657 n=1 100%† | — | 3.799 [3.718–3.84] n=3 100%† | 3.918 [3.824–4.001] n=3 100%† | 0.09 n=1 100%† | 5.654 n=1 100%† | 4.474 n=1 100%† | 0.067 n=1 100%† |
| 1 MB | 3.794 n=1 100%† | — | 6.774 [6.623–6.835] n=3 100%† | 7.158 [7.034–7.167] n=3 100%† | 0.089 n=1 100%† | 8.04 n=1 100%† | 7.282 n=1 100%† | 0.09 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

### Control round trip (s) ³ — protocol-specific, not comparable across protocols

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 0.0012 n=1 100%† | — | 0.08987 [0.08639–0.09448] n=3 100%† | 0.07388 [0.07097–0.07949] n=3 100%† | 0.1586 n=1 100%† | 0.001 n=1 100%† | 0.0858 n=1 100%† | 0.1414 n=1 100%† |
| 1 MB | 0.0006 n=1 100%† | — | 0.08256 [0.07814–0.08871] n=3 100%† | 0.07818 [0.0753–0.07949] n=3 100%† | 0.0943 n=1 100%† | 0.0011 n=1 100%† | 0.0808 n=1 100%† | 0.0655 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

### Avg CPU (%)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 0.25 n=1 100%† | — | 0.29 [0.225–0.3] n=3 100%† | 0.16 [0.16–0.23] n=3 100%† | 0.21 n=1 100%† | 0 n=1 100%† | 0.18 n=1 100%† | 0.18 n=1 100%† |
| 1 MB | 0.16 n=1 100%† | — | 0.2 [0.165–0.235] n=3 100%† | 0.2 [0.17–0.24] n=3 100%† | 0.2 n=1 100%† | 0.41 n=1 100%† | 0.22 n=1 100%† | 0.19 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

### Peak RAM (MB)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 23.83 n=1 100%† | — | 28.55 [28.53–28.7] n=3 100%† | 28.9 [28.7–29.2] n=3 100%† | 26.18 n=1 100%† | 28.22 n=1 100%† | 39.56 n=1 100%† | 26.7 n=1 100%† |
| 1 MB | 26.91 n=1 100%† | — | 28.75 [28.72–28.76] n=3 100%† | 29 [28.95–29.02] n=3 100%† | 26.94 n=1 100%† | 28.07 n=1 100%† | 41.79 n=1 100%† | 28.83 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

### Wire overhead % (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 9.375 n=1 100%† | — | 13.44 [13–13.6] n=3 100%† | 11.22 [11.17–11.52] n=3 100%† | 22.64 n=1 100%† | 9.908 n=1 100%† | 12.77 n=1 100%† | 22.4 n=1 100%† |
| 1 MB | 12.7 n=1 100%† | — | 11.63 [10.88–12.51] n=3 100%† | 12.35 [11.59–12.56] n=3 100%† | 22.16 n=1 100%† | 13.33 n=1 100%† | 11.29 n=1 100%† | 21.74 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

### Retransmissions (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 73 n=1 100%† | — | 18 [15–21] n=3 100%† | 27 [20.5–29] n=3 100%† | 1 n=1 100%† | 84 n=1 100%† | 22 n=1 100%† | 2 n=1 100%† |
| 1 MB | 207 n=1 100%† | — | 215 [175–222.5] n=3 100%† | 260 [250.5–310.5] n=3 100%† | 2 n=1 100%† | 256 n=1 100%† | 239 n=1 100%† | 1 n=1 100%† |
| 5 MB | — | — | — | — | — | — | — | — |

## Profile: iot

### Transfer time (s)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 88.65 n=1 100%† | 87.43 n=1 100%† | — | — | — | 87.32 n=1 50%† | — | — |

### Client goodput (Mbps)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 0.473 n=1 100%† | 0.48 n=1 100%† | — | — | — | 0.48 n=1 50%† | — | — |

### Control round trip (s) ³ — protocol-specific, not comparable across protocols

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 0.0006 n=1 100%† | 0.0007 n=1 100%† | — | — | — | 0.0009 [0.00085–0.00095] n=2 50%† | — | — |

### Avg CPU (%)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 0.3 n=1 100%† | 0.5 n=1 100%† | — | — | — | 1.21 [1.205–1.215] n=2 50%† | — | — |

### Peak RAM (MB)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 27.25 n=1 100%† | 27.97 n=1 100%† | — | — | — | 29.71 [29.63–29.79] n=2 50%† | — | — |

### Wire overhead % (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 11.74 n=1 100%† | 10.98 n=1 100%† | — | — | — | 11.05 n=1 50%† | — | — |

### Retransmissions (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | — | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | 1,737 n=1 100%† | 1,719 n=1 100%† | — | — | — | 1,694 n=1 50%† | — | — |

## Profile: ltem

### Transfer time (s)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 7.632 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Client goodput (Mbps)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 0.268 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Control round trip (s) ³ — protocol-specific, not comparable across protocols

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 0.1489 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Avg CPU (%)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 0.13 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Peak RAM (MB)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 28.62 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Wire overhead % (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 11.87 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Retransmissions (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 12 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

## Profile: nbiot

### Transfer time (s)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 91.35 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Client goodput (Mbps)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 0.022 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Control round trip (s) ³ — protocol-specific, not comparable across protocols

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 1.683 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Avg CPU (%)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 0.15 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Peak RAM (MB)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 29.14 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Wire overhead % (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 12.98 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

### Retransmissions (pcap)

| Size | MQTT QoS 1 | MQTT QoS 1 windowed | HTTP PUT | HTTP GET | CoAP | AMQP | gRPC | LwM2M |
|---|---|---|---|---|---|---|---|---|
| 250 KB | — | — | — | 8 n=1 100%† | — | — | — | — |
| 1 MB | — | — | — | — | — | — | — | — |
| 5 MB | — | — | — | — | — | — | — | — |

---

**How to read the comparison document**

- Each cell: `median [Q1–Q3] n=N S%` over the runs of the selected
  sweep(s). `n` counts the values behind the median; `S%` is verified
  transfers / attempts recorded in run.json, so a transfer that crashed
  without writing a row still counts as a failure. † marks cells with
  n < 5 or a success rate below 100 %. `failed (0/N)` means every
  attempt failed.
- Transfer time and goodput are the **device-side** view wherever the
  device receives the data: MQTT/AMQP use the receiver's delivery time
  (metadata arrival → file verified; the publisher sits on the clean
  server-side link, so its own time is not the constrained transfer), HTTP GET
  and LwM2M the download. HTTP PUT, CoAP and gRPC are uploads over the single
  shaped link and use the client measurement. The round-trip and CPU/RAM
  tables use the sender/client rows. Success rates use the row that carries
  the integrity verdict (MQTT/AMQP receiver, gRPC sender, others the client).
- ³ **Round-trip definitions differ per protocol**: MQTT = metadata PUBACK;
  AMQP = publish confirm; HTTP = bare TCP connect; CoAP = discovery GET;
  gRPC = Ping RPC; LwM2M = registration. Not comparable across protocols;
  compare transfer time, goodput, overhead and success rate instead.
- ⁴ **TLS handshake**: on top of the TCP connect, on a bare socket. For
  MQTT it is the device's (client-b) handshake over the constrained link,
  measured once per connection; for HTTP GET it is measured per transfer.
- **Shaping model**: one constrained link between the device and its data
  source, shaped in both directions (RTT ≈ 2 × netem delay); see
  docs/network-chaos.md. Wire overhead for MQTT/AMQP covers the device leg
  only.
- CPU and RAM are host-side process metrics of the containerised clients,
  not device measurements; device energy is measured in the field test.
- Library limitations behind some results (aiocoap stop-and-wait with 1 KB
  blocks, paho waiting per 1 MB chunk, synchronous AMQP confirms, LwM2M
  emulator without DTLS) are listed in docs/measurement-pipeline.md §5.

