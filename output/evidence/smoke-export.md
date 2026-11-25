# Benchmark Measurements Export

Generated: 2026-11-23 12:48 UTC · analyzer at commit `a1c51a4` · payloads: 250 KB – 5 MB

Companion document: `measurements_comparison.md` (side-by-side protocol comparison).

## MQTT

### MQTT — good

_Run: `20261123T124706_mqtt_good_r1`_

#### Client measurements

| Size | QoS | Side | Duration s | PUBACK RTT s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | sender | 0.006 | 0.0012 | 316.341 | 0.25% | 23.83 MB | 99 | — |
| 250 KB | qos 1 | receiver | 0.362 | 0.3603 | 5.657 | 0.23% | 22.59 MB | 35 | True |
| 1 MB | qos 1 | sender | 0.016 | 0.0006 | 538.795 | 0.16% | 26.91 MB | 100 | — |
| 1 MB | qos 1 | receiver | 2.211 | 2.2056 | 3.794 | 0.23% | 26.04 MB | 217 | True |
| 5 MB | not run |  |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | 0.42 | 325 | 280,000 | 9.38 | 73 | 4.865 | 5.321 |
| 1 MB | qos 1 | 2.28 | 1,475 | 1,181,762 | 12.70 | 207 | 3.680 | 4.147 |
| 5 MB | not run |  |  |  |  |  |  |  |

### MQTT — iot

_Run: `20261123T122848_mqtt_iot_r1`_

#### Client measurements

| Size | QoS | Side | Duration s | PUBACK RTT s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | not run |  |  |  |  |  |  |  |  |
| 1 MB | not run |  |  |  |  |  |  |  |  |
| 5 MB | qos 1 | sender | 0.059 | 0.0006 | 707.269 | 0.30% | 27.25 MB | 104 | — |
| 5 MB | qos 1 | receiver | 88.653 | 17.7452 | 0.473 | 0.16% | 26.38 MB | 8647 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 5 MB | qos 1 | 88.59 | 7,027 | 5,858,438 | 11.74 | 1737 | 0.473 | 0.529 |
| 250 KB | not run |  |  |  |  |  |  |  |
| 1 MB | not run |  |  |  |  |  |  |  |

### MQTT — ltem

**Not run.**

### MQTT — nbiot

**Not run.**

## MQTT-WINDOWED

### MQTT-WINDOWED — good

**Not run.**

### MQTT-WINDOWED — iot

_Run: `20261123T123056_mqtt-windowed_iot_r1`_

#### Client measurements

| Size | QoS | Side | Duration s | PUBACK RTT s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | not run |  |  |  |  |  |  |  |  |
| 1 MB | not run |  |  |  |  |  |  |  |  |
| 5 MB | qos 1 | sender | 0.149 | 0.0007 | 280.941 | 0.50% | 27.97 MB | 112 | — |
| 5 MB | qos 1 | receiver | 87.434 | 18.3011 | 0.480 | 0.15% | 26.22 MB | 8533 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 5 MB | qos 1 | 87.67 | 6,898 | 5,818,512 | 10.98 | 1719 | 0.478 | 0.531 |
| 250 KB | not run |  |  |  |  |  |  |  |
| 1 MB | not run |  |  |  |  |  |  |  |

### MQTT-WINDOWED — ltem

**Not run.**

### MQTT-WINDOWED — nbiot

**Not run.**

## HTTP

### HTTP — good

_3 runs (sweep `smoke-good`): `20261123T115145_http_good_r1`, `20261123T115356_http_good_r2`, `20261123T115507_http_good_r3`_

#### Client measurements

| Size | Transfer s | TCP connect s | TTFB s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 0.539 [0.5335–0.551] | 0.08987 [0.08639–0.09448] | 0.5378 [0.5282–0.5502] | 3.799 [3.718–3.84] | 0.29 [0.225–0.3] | 28.55 [28.53–28.7] | 52 [52–53.5] | 3/3 |
| 1 MB | 1.238 [1.227–1.267] | 0.08256 [0.07814–0.08871] | 1.231 [1.222–1.263] | 6.774 [6.623–6.835] | 0.2 [0.165–0.235] | 28.75 [28.72–28.76] | 121 [119.5–123.5] | 3/3 |
| 5 MB | not run |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 0.4198 [0.4176–0.4263] n=3 | 380 [379.5–380.5] | 290,400 [289,291–290,828] | 13.44 [13–13.6] | 18 [15–21] | 4.878 [4.805–4.905] | 5.55 [5.438–5.572] |
| 1 MB |  | 1.104 [1.099–1.139] n=3 | 1,472 [1,423–1,477] | 1,170,495 [1,162,685–1,179,737] | 11.63 [10.88–12.51] | 215 [175–222.5] | 7.6 [7.373–7.635] | 8.447 [8.275–8.465] |
| 5 MB | not run |  |  |  |  |  |  |  |

### HTTP — iot

**Not run.**

### HTTP — ltem

**Not run.**

### HTTP — nbiot

**Not run.**

## HTTP-GET

### HTTP-GET — good

_3 runs (sweep `smoke-good`): `20261123T115040_http-get_good_r1`, `20261123T115251_http-get_good_r2`, `20261123T115624_http-get_good_r3`_

#### Client measurements

| Size | Transfer s | TCP connect s | TLS handshake s | TTFB s | Goodput Mbps | Resumed | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 0.523 [0.5125–0.536] | 0.07388 [0.07097–0.07949] | — | 0.1753 [0.171–0.1763] | 3.918 [3.824–4.001] | 0 [0–0] | 0.16 [0.16–0.23] | 28.9 [28.7–29.2] | 52 [51–53] | 3/3 |
| 1 MB | 1.172 [1.171–1.193] | 0.07818 [0.0753–0.07949] | — | 0.1495 [0.1493–0.1649] | 7.158 [7.034–7.167] | 0 [0–0] | 0.2 [0.17–0.24] | 29 [28.95–29.02] | 115 [115–117] | 3/3 |
| 5 MB | not run |  |  |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 0.3896 [0.3851–0.409] n=3 | 374 [373.5–374] | 284,734 [284,599–285,500] | 11.22 [11.17–11.52] | 27 [20.5–29] | 5.256 [5.019–5.319] | 5.846 [5.597–5.913] |
| 1 MB |  | 1.062 [1.062–1.072] n=3 | 1,409 [1,408–1,411] | 1,178,095 [1,170,090–1,180,259] | 12.35 [11.59–12.56] | 260 [250.5–310.5] | 7.901 [7.825–7.902] | 8.757 [8.731–8.835] |
| 5 MB | not run |  |  |  |  |  |  |  |

### HTTP-GET — iot

**Not run.**

### HTTP-GET — ltem

_Run: `20261123T122531_http-get_ltem_r1`_

#### Client measurements

| Size | Transfer s | TCP connect s | TLS handshake s | TTFB s | Goodput Mbps | Resumed | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 7.632 | 0.14886 | — | 0.48256 | 0.268 | 0 | 0.13% | 28.62 MB | 747 | True |
| 1 MB | not run |  |  |  |  |  |  |  |  |  |
| 5 MB | not run |  |  |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 7.38 | 330 | 286,399 | 11.87 | 12 | 0.278 | 0.311 |
| 1 MB | not run |  |  |  |  |  |  |  |
| 5 MB | not run |  |  |  |  |  |  |  |

### HTTP-GET — nbiot

_Run: `20261123T122623_http-get_nbiot_r1`_

#### Client measurements

| Size | Transfer s | TCP connect s | TLS handshake s | TTFB s | Goodput Mbps | Resumed | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 91.348 | 1.68340 | — | 4.38777 | 0.022 | 0 | 0.15% | 29.14 MB | 8904 | True |
| 1 MB | not run |  |  |  |  |  |  |  |  |  |
| 5 MB | not run |  |  |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 88.60 | 400 | 289,223 | 12.98 | 8 | 0.023 | 0.026 |
| 1 MB | not run |  |  |  |  |  |  |  |
| 5 MB | not run |  |  |  |  |  |  |  |

## COAP

### COAP — good

_Run: `20261123T123916_coap_good_r1`_

#### Client measurements

| Size | Transfer s | Discovery GET s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|
| 250 KB | 22.778 | 0.1586 | 0.090 | 0.21% | 26.18 MB | 2217 | True |
| 1 MB | 94.165 | 0.0943 | 0.089 | 0.20% | 26.94 MB | 9176 | True |
| 5 MB | not run |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 22.81 | 507 | 313,967 | 22.64 | 1 | 0.090 | 0.110 |
| 1 MB |  | 94.20 | 2,064 | 1,280,949 | 22.16 | 2 | 0.089 | 0.109 |
| 5 MB | not run |  |  |  |  |  |  |  |

### COAP — iot

**Not run.**

### COAP — ltem

**Not run.**

### COAP — nbiot

**Not run.**

## AMQP

### AMQP — good

_Run: `20261123T124603_amqp_good_r1`_

#### Client measurements

| Size | Side | Duration s | Confirm RTT s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 0.005 | 0.0010 | 384.079 | 0.00% | 28.22 MB | 20 | — |
| 250 KB | receiver | 0.362 | 0.3608 | 5.654 | 0.00% | 26.61 MB | 36 | True |
| 1 MB | sender | 0.014 | 0.0011 | 610.554 | 0.41% | 28.07 MB | 20 | — |
| 1 MB | receiver | 1.043 | 1.0377 | 8.040 | 0.24% | 27.43 MB | 102 | True |
| 5 MB | not run |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 0.49 | 336 | 281,365 | 9.91 | 84 | 4.178 | 4.592 |
| 1 MB |  | 1.11 | 1,490 | 1,188,363 | 13.33 | 256 | 7.558 | 8.566 |
| 5 MB | not run |  |  |  |  |  |  |  |

### AMQP — iot

_2 runs (sweep `smoke-iot-broker2`, `smoke-iot-broker3`): `20261123T123306_amqp_iot_r1`, `20261123T123652_amqp_iot_r1`_

#### Client measurements

| Size | Side | Duration s | Confirm RTT s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | not run |  |  |  |  |  |  |  |
| 1 MB | not run |  |  |  |  |  |  |  |
| 5 MB | sender | 0.0525 [0.05175–0.05325] | 0.0009 [0.00085–0.00095] | 801.6 [788.7–814.5] | 1.21 [1.205–1.215] | 29.71 [29.63–29.79] | 20 [20–20] | — |
| 5 MB | receiver | 87.319 | 17.7768 | 0.480 | 0.14% | 28.48 MB | 8530 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 5 MB |  | 93.63 | 6,906 | 5,822,138 | 11.05 | 1694 | 0.448 | 0.497 |
| 250 KB | not run |  |  |  |  |  |  |  |
| 1 MB | not run |  |  |  |  |  |  |  |

### AMQP — ltem

**Not run.**

### AMQP — nbiot

**Not run.**

## GRPC

### GRPC — good

_Run: `20261123T124221_grpc_good_r1`_

#### Client measurements

| Size | Side | Duration s | Ping RPC s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 0.458 | 0.0858 | 4.474 | 0.18% | 39.56 MB | 45 | True |
| 250 KB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.23% | 38.35 MB | 35 | True |
| 1 MB | sender | 1.152 | 0.0808 | 7.282 | 0.22% | 41.79 MB | 113 | True |
| 1 MB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.24% | 41.25 MB | 103 | True |
| 5 MB | not run |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 0.66 | 369 | 288,697 | 12.77 | 22 | 3.112 | 3.509 |
| 1 MB |  | 1.36 | 1,350 | 1,166,988 | 11.29 | 239 | 6.167 | 6.863 |
| 5 MB | not run |  |  |  |  |  |  |  |

### GRPC — iot

**Not run.**

### GRPC — ltem

**Not run.**

### GRPC — nbiot

**Not run.**

## LWM2M

### LWM2M — good

_Run: `20261123T124313_lwm2m_good_r1`_

#### Client measurements

| Size | Download s | Registration s | Goodput Mbps | Avg CPU | Peak RAM | Samples | Integrity |
|---|---|---|---|---|---|---|---|
| 250 KB | 30.3929 | 0.1414 | 0.067 | 0.18% | 26.70 MB | 2966 | True |
| 1 MB | 93.5984 | 0.0655 | 0.090 | 0.19% | 28.83 MB | 9143 | True |
| 5 MB | not run |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 30.68 | 522 | 313,338 | 22.40 | 2 | 0.067 | 0.082 |
| 1 MB |  | 93.89 | 2,075 | 1,276,544 | 21.74 | 1 | 0.089 | 0.109 |
| 5 MB | not run |  |  |  |  |  |  |  |

### LWM2M — iot

**Not run.**

### LWM2M — ltem

**Not run.**

### LWM2M — nbiot

**Not run.**

---

**How to read this document**

- **Statistics.** Every cell aggregates all runs of the selected sweep(s):
  `median [Q1–Q3]` over the repetitions (inclusive quartiles). A single
  value means one run. **Integrity** shows verified transfers / rows.
- All pcap time metrics (`Duration s²`, `Pcap goodput`, `Wire Mbps`) are
  re-analyzed from the stored pcaps with the analyzer at commit a1c51a4.
  `n=` after the pcap duration is the number of captures aggregated;
  ⚠N counts captures left out because they dropped frames.
- ¹ **N/A (single chunk)**: a file that fits in one 1 MB chunk spans no
  measurable receiver-side arrival window. MQTT/AMQP **receiver** rows show
  the device-side delivery time instead (metadata arrival → file verified),
  which is defined for single-chunk files too.
- ² see the second bullet.
- **Shaping model** (docs/network-chaos.md, ISSUES.md FIXED-15): exactly one
  constrained link, between the device and its data source, shaped in both
  directions with the same per-direction values (RTT ≈ 2 × delay). MQTT/AMQP:
  the publisher (server side) is unshaped, the broker → device direction is
  shaped by the capture sidecar, and only the device leg is captured.
- The **latency columns** are named after what each protocol times (PUBACK,
  TCP connect, discovery GET, publish confirm, Ping RPC, registration); they
  are not comparable across protocols. `TLS handshake s` is the handshake on
  top of the TCP connect (TLS runs only).
- **Samples** is the CPU/RAM sample count behind the averages. CPU and RAM
  are host-side process metrics of the containerised clients.
- Sender-side **Integrity** is — for MQTT/AMQP by design: the sender hands
  the file to the broker; the receiver row carries the checksum result.

