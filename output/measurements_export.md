# Benchmark Measurements Export

Generated: 2026-11-22 11:48 UTC · analyzer at commit `d2426af` · payloads: 250 KB – 50 MB

Companion document: `measurements_comparison.md` (side-by-side protocol comparison).

## MQTT

### MQTT — good

_Run: `20261004T163448_mqtt_good`_

#### Client measurements

| Size | QoS | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | sender | 1.57 | 0.0777 | 1.304 | 0.13% | 23.91 MB | 0.0500 | — | — |
| 250 KB | qos 1 | receiver | N/A (single chunk)¹ | 1.6315 | N/A (single chunk)¹ | 0.15% | 22.61 MB | 0.0374 | — | True |
| 250 KB | qos 2 | sender | 0.62 | 0.1155 | 3.283 | 0.10% | 24.21 MB | 0.0249 | — | — |
| 250 KB | qos 2 | receiver | N/A (single chunk)¹ | 0.6786 | N/A (single chunk)¹ | 0.00% | 24.66 MB | 0.0000 | — | True |
| 1 MB | qos 1 | sender | 2.92 | 0.0657 | 2.873 | 0.13% | 27.17 MB | 0.0747 | — | — |
| 1 MB | qos 1 | receiver | N/A (single chunk)¹ | 3.0636 | N/A (single chunk)¹ | 0.11% | 24.04 MB | 0.0500 | — | True |
| 1 MB | qos 2 | sender | 1.84 | 0.1164 | 4.570 | 0.12% | 26.90 MB | 0.0500 | — | — |
| 1 MB | qos 2 | receiver | N/A (single chunk)¹ | 1.9286 | N/A (single chunk)¹ | 0.13% | 26.66 MB | 0.0374 | — | True |
| 5 MB | qos 1 | sender | 5.31 | 0.0400 | 7.896 | 0.18% | 28.06 MB | 0.1745 | — | — |
| 5 MB | qos 1 | receiver | 4.00 | 1.3832 | 10.493 | 0.18% | 26.36 MB | 0.1493 | — | True |
| 5 MB | qos 2 | sender | 6.26 | 0.0834 | 6.701 | 0.14% | 27.49 MB | 0.1492 | — | — |
| 5 MB | qos 2 | receiver | 3.93 | 2.3484 | 10.672 | 0.16% | 26.67 MB | 0.1500 | — | True |
| 20 MB | qos 1 | sender | 21.04 | 0.0373 | 7.972 | 0.15% | 27.84 MB | 0.5095 | — | — |
| 20 MB | qos 1 | receiver | 19.08 | 2.0368 | 8.791 | 0.18% | 26.38 MB | 0.5842 | — | True |
| 20 MB | qos 2 | sender | 22.20 | 0.0716 | 7.557 | 0.13% | 27.61 MB | 0.4553 | — | — |
| 20 MB | qos 2 | receiver | 20.14 | 2.1110 | 8.332 | 0.16% | 26.61 MB | 0.5470 | — | True |
| 50 MB | qos 1 | sender | 52.35 | 0.0412 | 8.012 | 0.14% | 28.34 MB | 1.1586 | — | — |
| 50 MB | qos 1 | receiver | 50.52 | 1.8976 | 8.302 | 0.18% | 26.57 MB | 1.3883 | — | True |
| 50 MB | qos 2 | sender | 50.29 | 0.0872 | 8.340 | 0.14% | 27.81 MB | 1.0483 | — | — |
| 50 MB | qos 2 | receiver | 48.21 | 2.1092 | 8.700 | 0.17% | 26.72 MB | 1.2654 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | 1.73 | 562 | 551,708 | 115.51 | 14 | 1.186 | 2.555 |
| 1 MB | qos 1 | 3.17 | 2,251 | 2,254,346 | 114.99 | 113 | 2.645 | 5.686 |
| 5 MB | qos 1 | 5.51 | 10,760 | 11,252,656 | 114.63 | 1123 | 7.608 | 16.329 |
| 20 MB | qos 1 | 21.39 | 42,550 | 44,998,702 | 114.57 | 4446 | 7.845 | 16.834 |
| 50 MB | qos 1 | 53.01 | 106,021 | 112,497,208 | 114.57 | 11338 | 7.912 | 16.977 |
| 250 KB | qos 2 | 0.85 | 572 | 553,388 | 116.17 | 51 | 2.413 | 5.217 |
| 1 MB | qos 2 | 2.84 | 2,212 | 2,258,576 | 115.39 | 171 | 2.951 | 6.357 |
| 5 MB | qos 2 | 6.49 | 10,634 | 11,235,964 | 114.31 | 979 | 6.467 | 13.860 |
| 20 MB | qos 2 | 22.60 | 42,507 | 44,989,044 | 114.52 | 4465 | 7.423 | 15.924 |
| 50 MB | qos 2 | 50.97 | 106,454 | 112,483,802 | 114.55 | 11535 | 8.230 | 17.656 |

### MQTT — iot

_Run: `20260831T064335_mqtt_iot`_

#### Client measurements

| Size | QoS | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | sender | 11.43 | 0.5019 | 0.179 | — | — | — | — | — |
| 250 KB | qos 1 | receiver | N/A (single chunk)¹ | 11.4753 | N/A (single chunk)¹ | — | — | — | — | True |
| 250 KB | qos 2 | sender | 11.16 | 0.6441 | 0.183 | — | — | — | — | — |
| 250 KB | qos 2 | receiver | N/A (single chunk)¹ | 11.3146 | N/A (single chunk)¹ | — | — | — | — | True |
| 1 MB | qos 1 | sender | 28.81 | 0.5058 | 0.291 | — | — | — | — | — |
| 1 MB | qos 1 | receiver | N/A (single chunk)¹ | 29.1605 | N/A (single chunk)¹ | — | — | — | — | True |
| 1 MB | qos 2 | sender | 50.57 | 0.6133 | 0.166 | — | — | — | — | — |
| 1 MB | qos 2 | receiver | N/A (single chunk)¹ | 50.8442 | N/A (single chunk)¹ | — | — | — | — | True |
| 5 MB | qos 1 | sender | 267.36 | 0.4576 | 0.157 | — | — | — | — | — |
| 5 MB | qos 1 | receiver | 214.87 | 52.9902 | 0.195 | — | — | — | — | True |
| 5 MB | qos 2 | sender | 270.65 | 0.5501 | 0.155 | — | — | — | — | — |
| 5 MB | qos 2 | receiver | 217.49 | 53.9148 | 0.193 | — | — | — | — | True |
| 20 MB | qos 1 | sender | 1096.60 | 0.4183 | 0.153 | — | — | — | — | — |
| 20 MB | qos 1 | receiver | 1044.37 | 53.2171 | 0.161 | — | — | — | — | True |
| 20 MB | qos 2 | sender | 1079.66 | 0.5181 | 0.155 | — | — | — | — | — |
| 20 MB | qos 2 | receiver | 1035.09 | 45.1387 | 0.162 | — | — | — | — | True |
| 50 MB | qos 1 | sender | 2718.77 | 0.1215 | 0.154 | — | — | — | — | — |
| 50 MB | qos 1 | receiver | 2693.61 | 26.3888 | 0.156 | — | — | — | — | True |
| 50 MB | qos 2 | sender | 910.18 | 0.3783 | 0.461 | — | — | — | — | — |
| 50 MB | qos 2 | receiver | 884.77 | 25.5957 | 0.474 | — | — | — | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | 11.99 | 599 | 555,610 | 117.04 | 7 | 0.171 | 0.371 |
| 1 MB | qos 1 | 29.44 | 2,499 | 2,281,650 | 117.60 | 35 | 0.285 | 0.620 |
| 5 MB | qos 1 | 268.30 | 11,143 | 11,300,034 | 115.53 | 175 | 0.156 | 0.337 |
| 20 MB | qos 1 | 1097.93 | 42,909 | 45,132,073 | 115.21 | 451 | 0.153 | 0.329 |
| 50 MB | qos 1 | 2720.60 | 107,912 | 112,856,078 | 115.26 | 1161 | 0.154 | 0.332 |
| 250 KB | qos 2 | 12.26 | 575 | 558,694 | 118.24 | 15 | 0.167 | 0.365 |
| 1 MB | qos 2 | 51.78 | 2,225 | 2,264,946 | 116.00 | 32 | 0.162 | 0.350 |
| 5 MB | qos 2 | 272.42 | 10,890 | 11,291,573 | 115.37 | 116 | 0.154 | 0.332 |
| 20 MB | qos 2 | 1081.14 | 43,016 | 45,113,778 | 115.12 | 434 | 0.155 | 0.334 |
| 50 MB | qos 2 | 911.28 | 110,142 | 113,819,202 | 117.09 | 1396 | 0.460 | 0.999 |

### MQTT — harsh

_Run: `20260901T175347_mqtt_harsh`_

#### Client measurements

| Size | QoS | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | sender | 20.19 | 0.8583 | 0.101 | — | — | — | — | — |
| 250 KB | qos 1 | receiver | N/A (single chunk)¹ | 20.4213 | N/A (single chunk)¹ | — | — | — | — | True |
| 250 KB | qos 2 | sender | 18.47 | 1.0799 | 0.111 | — | — | — | — | — |
| 250 KB | qos 2 | receiver | N/A (single chunk)¹ | 18.6223 | N/A (single chunk)¹ | — | — | — | — | True |
| 1 MB | qos 1 | sender | 60.80 | 0.7954 | 0.138 | — | — | — | — | — |
| 1 MB | qos 1 | receiver | N/A (single chunk)¹ | 176.5147 | N/A (single chunk)¹ | — | — | — | — | True |
| 1 MB | qos 2 | sender | 60.81 | 0.7990 | 0.138 | — | — | — | — | — |
| 1 MB | qos 2 | receiver | N/A (single chunk)¹ | 103.4601 | N/A (single chunk)¹ | — | — | — | — | True |
| 5 MB | qos 1 | sender | 257.75 | 0.3997 | 0.163 | — | — | — | — | — |
| 5 MB | qos 1 | receiver | 176.97 | 82.0760 | 0.237 | — | — | — | — | True |
| 5 MB | qos 2 | sender | 250.44 | 0.6960 | 0.167 | — | — | — | — | — |
| 5 MB | qos 2 | receiver | 114.12 | 136.7496 | 0.368 | — | — | — | — | True |
| 20 MB | qos 1 | sender | 979.19 | 0.4411 | 0.171 | — | — | — | — | — |
| 20 MB | qos 1 | receiver | 929.68 | 96.3100 | 0.180 | — | — | — | — | True |
| 20 MB | qos 2 | sender | 849.51 | 0.5588 | 0.197 | — | — | — | — | — |
| 20 MB | qos 2 | receiver | 731.22 | 117.9901 | 0.229 | — | — | — | — | True |
| 50 MB | qos 1 | sender | 2187.69 | 0.1588 | 0.192 | — | — | — | — | — |
| 50 MB | qos 1 | receiver | 2093.59 | 95.2186 | 0.200 | — | — | — | — | True |
| 50 MB | qos 2 | sender | 2126.88 | 1.7776 | 0.197 | — | — | — | — | — |
| 50 MB | qos 2 | receiver | 2023.37 | 102.7377 | 0.207 | — | — | — | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | 20.75 | 633 | 568,326 | 122.00 | 11 | 0.099 | 0.219 |
| 1 MB | qos 1 | 176.81 | 2,691 | 2,313,706 | 120.65 | 25 | 0.047 | 0.105 |
| 5 MB | qos 1 | 259.37 | 11,753 | 11,496,576 | 119.28 | 251 | 0.162 | 0.355 |
| 20 MB | qos 1 | 1026.64 | 45,715 | 45,897,552 | 118.86 | 565 | 0.163 | 0.358 |
| 50 MB | qos 1 | 2189.70 | 114,910 | 115,109,448 | 119.55 | 1830 | 0.192 | 0.421 |
| 250 KB | qos 2 | 19.82 | 599 | 563,258 | 120.02 | 16 | 0.103 | 0.227 |
| 1 MB | qos 2 | 104.97 | 2,222 | 2,278,688 | 117.31 | 69 | 0.080 | 0.174 |
| 5 MB | qos 2 | 252.20 | 11,407 | 11,441,302 | 118.23 | 143 | 0.166 | 0.363 |
| 20 MB | qos 2 | 851.11 | 45,773 | 46,018,258 | 119.43 | 740 | 0.197 | 0.433 |
| 50 MB | qos 2 | 2128.41 | 115,181 | 114,918,945 | 119.19 | 1312 | 0.197 | 0.432 |

### MQTT — mobile

_Run: `20260903T162303_mqtt_mobile`_

#### Client measurements

| Size | QoS | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | sender | 9.67 | 0.2419 | 0.212 | — | — | — | — | — |
| 250 KB | qos 1 | receiver | N/A (single chunk)¹ | 9.5940 | N/A (single chunk)¹ | — | — | — | — | True |
| 250 KB | qos 2 | sender | 9.80 | 0.5839 | 0.209 | — | — | — | — | — |
| 250 KB | qos 2 | receiver | N/A (single chunk)¹ | 9.8687 | N/A (single chunk)¹ | — | — | — | — | True |
| 1 MB | qos 1 | sender | 45.27 | 0.4935 | 0.185 | — | — | — | — | — |
| 1 MB | qos 1 | receiver | N/A (single chunk)¹ | 45.1377 | N/A (single chunk)¹ | — | — | — | — | True |
| 1 MB | qos 2 | sender | 46.43 | 0.3982 | 0.181 | — | — | — | — | — |
| 1 MB | qos 2 | receiver | N/A (single chunk)¹ | 46.5812 | N/A (single chunk)¹ | — | — | — | — | True |
| 5 MB | qos 1 | sender | 232.36 | 0.5152 | 0.181 | — | — | — | — | — |
| 5 MB | qos 1 | receiver | 189.49 | 42.7441 | 0.221 | — | — | — | — | True |
| 5 MB | qos 2 | sender | 233.19 | 0.5253 | 0.180 | — | — | — | — | — |
| 5 MB | qos 2 | receiver | 186.00 | 47.0397 | 0.225 | — | — | — | — | True |
| 20 MB | qos 1 | sender | 913.72 | 0.4327 | 0.184 | — | — | — | — | — |
| 20 MB | qos 1 | receiver | 868.78 | 45.3129 | 0.193 | — | — | — | — | True |
| 20 MB | qos 2 | sender | 917.62 | 0.4418 | 0.183 | — | — | — | — | — |
| 20 MB | qos 2 | receiver | 872.21 | 45.3201 | 0.192 | — | — | — | — | True |
| 50 MB | qos 1 | sender | 2308.75 | 0.1838 | 0.182 | — | — | — | — | — |
| 50 MB | qos 1 | receiver | 2263.72 | 45.6516 | 0.185 | — | — | — | — | True |
| 50 MB | qos 2 | sender | 2311.14 | 0.1856 | 0.181 | — | — | — | — | — |
| 50 MB | qos 2 | receiver | 2264.81 | 46.6881 | 0.185 | — | — | — | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | 9.71 | 637 | 569,247 | 122.36 | 23 | 0.211 | 0.469 |
| 1 MB | qos 1 | 45.42 | 2,297 | 2,261,662 | 115.69 | 59 | 0.185 | 0.398 |
| 5 MB | qos 1 | 232.85 | 11,159 | 11,304,035 | 115.61 | 252 | 0.180 | 0.388 |
| 20 MB | qos 1 | 914.53 | 42,707 | 45,054,699 | 114.84 | 717 | 0.183 | 0.394 |
| 50 MB | qos 1 | 2310.21 | 107,154 | 112,589,598 | 114.75 | 4100 | 0.182 | 0.390 |
| 250 KB | qos 2 | 10.76 | 565 | 552,550 | 115.84 | 19 | 0.190 | 0.411 |
| 1 MB | qos 2 | 46.97 | 2,200 | 2,269,376 | 116.42 | 85 | 0.179 | 0.387 |
| 5 MB | qos 2 | 233.53 | 10,783 | 11,273,302 | 115.02 | 182 | 0.180 | 0.386 |
| 20 MB | qos 2 | 918.36 | 42,951 | 45,037,497 | 114.76 | 2922 | 0.183 | 0.392 |
| 50 MB | qos 2 | 2312.17 | 107,334 | 112,622,284 | 114.81 | 1667 | 0.181 | 0.390 |

### MQTT — satellite

_Run: `20261120T150046_mqtt_satellite`_

#### Client measurements

| Size | QoS | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | sender | 6.26 | 1.1598 | 0.327 | 0.10% | 23.72 MB | 0.1249 | 827 | — |
| 250 KB | qos 1 | receiver | N/A (single chunk)¹ | 8.3904 | N/A (single chunk)¹ | 0.10% | 22.62 MB | 0.1248 | 824 | True |
| 250 KB | qos 2 | sender | 3.90 | 1.9294 | 0.526 | 0.12% | 23.62 MB | 0.1250 | 669 | — |
| 250 KB | qos 2 | receiver | N/A (single chunk)¹ | 5.9510 | N/A (single chunk)¹ | 0.11% | 29.26 MB | 0.0998 | 583 | True |
| 1 MB | qos 1 | sender | 14.25 | 1.0819 | 0.589 | 0.10% | 26.74 MB | 0.2375 | 1603 | — |
| 1 MB | qos 1 | receiver | N/A (single chunk)¹ | 17.3960 | N/A (single chunk)¹ | 0.10% | 26.07 MB | 0.2623 | 1708 | True |
| 1 MB | qos 2 | sender | 16.16 | 1.9445 | 0.519 | 0.12% | 26.67 MB | 0.3373 | 1871 | — |
| 1 MB | qos 2 | receiver | N/A (single chunk)¹ | 19.8475 | N/A (single chunk)¹ | 0.12% | 30.27 MB | 0.3498 | 1944 | True |
| 5 MB | qos 1 | sender | 62.95 | 1.0861 | 0.666 | 0.10% | 27.73 MB | 0.9873 | 6382 | — |
| 5 MB | qos 1 | receiver | 40.39 | 26.1622 | 1.038 | 0.10% | 26.28 MB | 1.0362 | 6531 | True |
| 5 MB | qos 2 | sender | 62.06 | 1.7800 | 0.676 | 0.11% | 26.75 MB | 1.1111 | 6351 | — |
| 5 MB | qos 2 | receiver | 47.78 | 17.7995 | 0.878 | 0.12% | 29.80 MB | 1.1737 | 6422 | True |
| 20 MB | qos 1 | sender | 248.37 | 1.2287 | 0.675 | 0.12% | 28.82 MB | 4.4400 | 24533 | — |
| 20 MB | qos 1 | receiver | 228.13 | 23.7552 | 0.735 | 0.12% | 27.72 MB | 4.6234 | 24656 | True |
| 20 MB | qos 2 | sender | 261.56 | 1.6342 | 0.641 | 0.12% | 28.57 MB | 4.6590 | 25864 | — |
| 20 MB | qos 2 | receiver | 248.96 | 16.0862 | 0.674 | 0.12% | 30.07 MB | 4.7813 | 25947 | True |
| 50 MB | qos 1 | sender | 613.42 | 0.9233 | 0.684 | 0.14% | 31.73 MB | 12.6783 | 60093 | — |
| 50 MB | qos 1 | receiver | 599.22 | 17.5150 | 0.700 | 0.14% | 30.71 MB | 13.0476 | 60229 | True |
| 50 MB | qos 2 | sender | 695.56 | 1.4760 | 0.603 | 0.12% | 32.24 MB | 12.0507 | 68360 | — |
| 50 MB | qos 2 | receiver | 666.76 | 32.0072 | 0.629 | 0.12% | 31.64 MB | 12.3598 | 68431 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB | qos 1 | 16.09 | 676 | 561,161 | 119.20 | 35 | 0.127 | 0.279 |
| 1 MB | qos 1 | 18.66 | 2,575 | 2,289,326 | 118.33 | 164 | 0.450 | 0.982 |
| 5 MB | qos 1 | 67.73 | 11,543 | 11,324,742 | 116.00 | 629 | 0.619 | 1.338 |
| 20 MB | qos 1 | 253.26 | 43,114 | 45,221,498 | 115.63 | 2835 | 0.662 | 1.428 |
| 50 MB | qos 1 | 618.18 | 109,454 | 113,208,786 | 115.93 | 6678 | 0.678 | 1.465 |
| 250 KB | qos 2 | 8.40 | 594 | 557,532 | 117.79 | 22 | 0.244 | 0.531 |
| 1 MB | qos 2 | 22.35 | 2,200 | 2,288,344 | 118.23 | 183 | 0.375 | 0.819 |
| 5 MB | qos 2 | 68.03 | 10,641 | 11,297,230 | 115.48 | 713 | 0.617 | 1.329 |
| 20 MB | qos 2 | 267.43 | 43,978 | 45,314,534 | 116.08 | 2924 | 0.627 | 1.356 |
| 50 MB | qos 2 | 701.43 | 108,435 | 113,280,475 | 116.07 | 6531 | 0.598 | 1.292 |

## HTTP

### HTTP — good

_Run: `20261120T135139_http_good`_

#### Client measurements

| Size | Transfer s | TCP RTT s | TTFB s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 0.714 | 0.07723 | 0.70046 | 2.868 | 0.23% | 29.23 MB | 0.0250 | 70 | True |
| 1 MB | 1.193 | 0.07781 | 1.18796 | 7.032 | 0.14% | 29.36 MB | 0.0248 | 118 | True |
| 5 MB | 5.901 | 0.08232 | 5.88880 | 7.107 | 0.14% | 29.09 MB | 0.1247 | 578 | True |
| 20 MB | 22.643 | 0.07676 | 22.64203 | 7.410 | 0.15% | 29.46 MB | 0.5091 | 2213 | True |
| 50 MB | 58.544 | 0.09286 | 58.53454 | 7.164 | 0.17% | 29.60 MB | 1.4450 | 5708 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 0.61 | 390 | 292,515 | 14.26 | 19 | 3.374 | 3.855 |
| 1 MB |  | 1.08 | 1,407 | 1,162,184 | 10.83 | 131 | 7.761 | 8.601 |
| 5 MB |  | 5.78 | 6,776 | 5,788,062 | 10.40 | 463 | 7.257 | 8.012 |
| 20 MB |  | 22.52 | 26,778 | 22,978,818 | 9.57 | 922 | 7.449 | 8.162 |
| 50 MB |  | 58.44 | 66,182 | 57,268,880 | 9.23 | 2163 | 7.178 | 7.840 |

### HTTP — iot

_Run: `20260831T083408_http_iot`_

#### Client measurements

| Size | Transfer s | TCP RTT s | TTFB s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 5.502 | 0.46150 | 5.36526 | 0.372 | 0.11% | 29.08 MB | 0.0073 | — | True |
| 1 MB | 18.718 | 0.48351 | 18.60070 | 0.448 | 0.10% | 29.48 MB | 0.0240 | — | True |
| 5 MB | 92.365 | 0.30828 | 92.36404 | 0.454 | 0.10% | 29.83 MB | 0.1175 | — | True |
| 20 MB | 350.283 | 0.30224 | 350.16915 | 0.479 | 0.13% | 31.47 MB | 0.5665 | — | True |
| 50 MB | 879.969 | 0.32213 | 879.96086 | 0.477 | 0.13% | 35.86 MB | 1.4211 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 5.05 | 399 | 299,894 | 17.15 | 32 | 0.405 | 0.475 |
| 1 MB |  | 18.17 | 1,528 | 1,196,442 | 14.10 | 122 | 0.462 | 0.527 |
| 5 MB |  | 92.17 | 6,944 | 5,879,594 | 12.14 | 364 | 0.455 | 0.510 |
| 20 MB |  | 349.59 | 27,255 | 23,268,834 | 10.95 | 1368 | 0.480 | 0.532 |
| 50 MB |  | 879.43 | 68,085 | 58,319,390 | 11.24 | 3516 | 0.477 | 0.531 |

### HTTP — harsh

_Run: `20260901T195341_http_harsh`_

#### Client measurements

| Size | Transfer s | TCP RTT s | TTFB s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 12.245 | 0.22284 | 12.24364 | 0.167 | 0.12% | 29.07 MB | 0.0188 | — | True |
| 1 MB | 42.088 | 0.42105 | 42.08688 | 0.199 | 0.11% | 29.33 MB | 0.0593 | — | True |
| 5 MB | 213.625 | 0.49823 | 213.46991 | 0.196 | 0.11% | 30.74 MB | 0.2867 | — | True |
| 20 MB | 812.617 | 0.36775 | 812.61597 | 0.206 | 0.11% | 35.28 MB | 1.1127 | — | True |
| 50 MB | 1940.995 | 0.36169 | 1940.98945 | 0.216 | 0.13% | 45.10 MB | 3.1560 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 11.60 | 430 | 319,915 | 24.97 | 38 | 0.177 | 0.221 |
| 1 MB |  | 41.35 | 1,576 | 1,228,402 | 17.15 | 109 | 0.203 | 0.238 |
| 5 MB |  | 212.97 | 7,680 | 6,049,322 | 15.38 | 444 | 0.197 | 0.227 |
| 20 MB |  | 811.83 | 30,537 | 24,125,284 | 15.04 | 1953 | 0.207 | 0.238 |
| 50 MB |  | 1940.19 | 76,048 | 60,043,374 | 14.52 | 4698 | 0.216 | 0.248 |

### HTTP — mobile

_Run: `20260903T081214_http_mobile`_

#### Client measurements

| Size | Transfer s | TCP RTT s | TTFB s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 3.612 | 0.40108 | 3.61111 | 0.567 | 0.12% | 29.11 MB | 0.0052 | — | True |
| 1 MB | 14.182 | 0.29830 | 14.18105 | 0.592 | 0.10% | 29.44 MB | 0.0177 | — | True |
| 5 MB | 53.827 | 0.44092 | 53.82622 | 0.779 | 0.11% | 29.45 MB | 0.0718 | — | True |
| 20 MB | 184.715 | 0.13113 | 184.71409 | 0.908 | 0.10% | 30.34 MB | 0.2395 | — | True |
| 50 MB | 472.203 | 0.42034 | 472.09258 | 0.888 | 0.10% | 32.97 MB | 0.5946 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 3.07 | 414 | 310,743 | 21.38 | 33 | 0.667 | 0.809 |
| 1 MB |  | 14.20 | 1,488 | 1,193,358 | 13.81 | 54 | 0.591 | 0.672 |
| 5 MB |  | 53.30 | 6,872 | 5,894,746 | 12.43 | 457 | 0.787 | 0.885 |
| 20 MB |  | 184.16 | 27,037 | 23,396,104 | 11.56 | 1736 | 0.911 | 1.016 |
| 50 MB |  | 472.16 | 67,588 | 58,644,710 | 11.86 | 4505 | 0.888 | 0.994 |

### HTTP — satellite

_Run: `20261120T153705_http_satellite`_

#### Client measurements

| Size | Transfer s | TCP RTT s | TTFB s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | 8.679 | 1.10092 | 8.67839 | 0.236 | 0.12% | 28.86 MB | 0.1499 | 851 | True |
| 1 MB | 13.676 | 1.12454 | 13.67584 | 0.613 | 0.12% | 28.62 MB | 0.2498 | 1340 | True |
| 5 MB | 62.829 | 1.29520 | 62.82070 | 0.668 | 0.12% | 29.21 MB | 1.0841 | 6154 | True |
| 20 MB | 228.382 | 1.15683 | 228.38130 | 0.735 | 0.12% | 30.25 MB | 3.9328 | 22367 | True |
| 50 MB | 611.047 | 1.20869 | 611.04607 | 0.686 | 0.11% | 33.61 MB | 10.2188 | 59870 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 6.89 | 390 | 288,552 | 12.72 | 82 | 0.297 | 0.335 |
| 1 MB |  | 11.94 | 1,448 | 1,157,678 | 10.40 | 159 | 0.702 | 0.775 |
| 5 MB |  | 61.08 | 6,541 | 5,774,120 | 10.13 | 790 | 0.687 | 0.756 |
| 20 MB |  | 226.70 | 25,700 | 23,144,276 | 10.36 | 2909 | 0.740 | 0.817 |
| 50 MB |  | 609.29 | 64,390 | 57,718,606 | 10.09 | 6129 | 0.688 | 0.758 |

## COAP

### COAP — good

_Run: `20260830T125026_coap_good`_

#### Client measurements

| Size | Transfer s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 64.21 | 0.5876 | 0.032 | 0.11% | 26.91 MB | 0.0916 | — | True |
| 1 MB | 250.47 | 0.1668 | 0.033 | 0.13% | 28.06 MB | 0.3940 | — | True |
| 5 MB | 1271.21 | 0.1781 | 0.033 | 0.15% | 39.15 MB | 2.3697 | — | True |
| 20 MB | 5167.06 | 0.3370 | 0.032 | 0.14% | 83.68 MB | 9.0300 | — | True |
| 50 MB | 13443.05 | 0.3175 | 0.031 | 0.13% | 175.95 MB | 21.3140 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 64.43 | 511 | 312,989 | 22.26 | 0 | 0.032 | 0.039 |
| 1 MB |  | 250.57 | 2,081 | 1,279,405 | 22.01 | 0 | 0.033 | 0.041 |
| 5 MB |  | 1271.28 | 10,414 | 6,399,327 | 22.06 | 0 | 0.033 | 0.040 |
| 20 MB |  | 5167.12 | 41,633 | 25,642,749 | 22.27 | 1 | 0.032 | 0.040 |
| 50 MB |  | 13442.82 | 104,197 | 64,210,443 | 22.47 | 3 | 0.031 | 0.038 |

### COAP — iot

_Run: `20260831T085853_coap_iot`_

#### Client measurements

| Size | Transfer s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 100.16 | 0.9401 | 0.020 | 0.14% | 27.03 MB | 0.1715 | — | True |
| 1 MB | 415.88 | 0.5143 | 0.020 | 0.15% | 29.32 MB | 0.7824 | — | True |
| 5 MB | 2068.26 | 0.2826 | 0.020 | 0.13% | 45.16 MB | 3.2698 | — | True |
| 20 MB | 8404.35 | 0.4086 | 0.020 | 0.14% | 107.93 MB | 14.7823 | — | True |
| 50 MB | 21499.70 | 0.5398 | 0.020 | 0.13% | 236.13 MB | 35.3967 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 100.35 | 518 | 313,283 | 22.38 | 0 | 0.020 | 0.025 |
| 1 MB |  | 416.14 | 2,107 | 1,287,500 | 22.79 | 6 | 0.020 | 0.025 |
| 5 MB |  | 2068.32 | 10,561 | 6,437,044 | 22.78 | 27 | 0.020 | 0.025 |
| 20 MB |  | 8404.03 | 42,251 | 25,796,024 | 23.01 | 110 | 0.020 | 0.025 |
| 50 MB |  | 21499.14 | 105,649 | 64,508,024 | 23.04 | 253 | 0.020 | 0.024 |

### COAP — harsh

_Run: `20260901T204603_coap_harsh`_ — *partial run: some sizes were attempted but never completed/recorded client-side (large files struggle under this profile, ISSUES.md OPEN-4); missing client sizes are marked 'not run' and the packet-side table may still list their (degraded) captures.*

#### Client measurements

| Size | Transfer s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 134.65 | 1.0019 | 0.015 | 0.15% | 27.41 MB | 0.2579 | — | True |
| 1 MB | 635.95 | 0.4223 | 0.013 | 0.15% | 30.87 MB | 1.2066 | — | True |
| 5 MB | 3119.24 | 0.6877 | 0.013 | 0.12% | 53.28 MB | 4.6432 | — | True |
| 20 MB | not run |  |  |  |  |  |  |  |
| 50 MB | not run |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 134.78 | 531 | 319,655 | 24.87 | 5 | 0.015 | 0.019 |
| 1 MB |  | 636.04 | 2,148 | 1,293,887 | 23.39 | 10 | 0.013 | 0.016 |
| 5 MB |  | 3119.34 | 10,673 | 6,461,424 | 23.24 | 44 | 0.013 | 0.017 |
| 20 MB |  | 7982.84 ⚠ | 26,952 | 16,290,192 | -22.32 | 130 | 0.021 | 0.016 |
| 50 MB |  | 22761.12 ⚠ | 79,218 | 47,993,121 | -8.46 | 357 | 0.018 | 0.017 |

### COAP — mobile

_Run: `20260903T082615_coap_mobile`_

#### Client measurements

| Size | Transfer s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 86.60 | 0.7888 | 0.024 | 0.11% | 26.93 MB | 0.1166 | — | True |
| 1 MB | 369.83 | 0.3567 | 0.023 | 0.11% | 28.80 MB | 0.5019 | — | True |
| 5 MB | 1798.28 | 0.5400 | 0.023 | 0.11% | 43.46 MB | 2.5100 | — | True |
| 20 MB | 7346.98 | 0.3406 | 0.023 | 0.11% | 100.19 MB | 10.1335 | — | True |
| 50 MB | 18887.83 | 0.2303 | 0.022 | 0.11% | 216.77 MB | 25.9862 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 86.78 | 512 | 313,041 | 22.28 | 0 | 0.024 | 0.029 |
| 1 MB |  | 369.94 | 2,096 | 1,280,085 | 22.08 | 0 | 0.023 | 0.028 |
| 5 MB |  | 1798.43 | 10,492 | 6,406,799 | 22.20 | 0 | 0.023 | 0.028 |
| 20 MB |  | 7346.89 | 41,902 | 25,655,329 | 22.33 | 2 | 0.023 | 0.028 |
| 50 MB |  | 18887.23 | 104,891 | 64,153,079 | 22.36 | 2 | 0.022 | 0.027 |

### COAP — satellite

**Not run.**

## AMQP

### AMQP — good

_Run: `20260830T182924_amqp_good`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 1.35 | 0.1055 | 1.517 | 0.12% | 28.09 MB | 0.0021 | — | — |
| 250 KB | receiver | N/A (single chunk)¹ | 1.3821 | N/A (single chunk)¹ | 0.12% | 26.88 MB | 0.0021 | — | True |
| 1 MB | sender | 1.51 | 0.0471 | 5.565 | 0.17% | 28.31 MB | 0.0031 | — | — |
| 1 MB | receiver | N/A (single chunk)¹ | 1.6557 | N/A (single chunk)¹ | 0.20% | 28.94 MB | 0.0042 | — | True |
| 5 MB | sender | 6.42 | 0.0507 | 6.529 | 0.12% | 28.38 MB | 0.0094 | — | — |
| 5 MB | receiver | 3.68 | 2.8019 | 11.407 | 0.13% | 28.83 MB | 0.0104 | — | True |
| 20 MB | sender | 21.82 | 0.0461 | 7.689 | 0.11% | 28.52 MB | 0.0302 | — | — |
| 20 MB | receiver | 18.99 | 2.9057 | 8.836 | 0.13% | 28.91 MB | 0.0364 | — | True |
| 50 MB | sender | 53.32 | 0.0504 | 7.866 | 0.11% | 28.57 MB | 0.0718 | — | — |
| 50 MB | receiver | 50.81 | 2.6873 | 8.255 | 0.13% | 28.98 MB | 0.0895 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 1.82 | 590 | 554,949 | 116.78 | 14 | 1.128 | 2.445 |
| 1 MB |  | 2.02 | 2,350 | 2,264,725 | 115.98 | 150 | 4.149 | 8.962 |
| 5 MB |  | 7.90 | 10,903 | 11,255,827 | 114.69 | 996 | 5.311 | 11.403 |
| 20 MB |  | 22.47 | 43,118 | 45,065,764 | 114.89 | 4481 | 7.466 | 16.045 |
| 50 MB |  | 54.56 | 107,962 | 112,667,971 | 114.90 | 11379 | 7.687 | 16.519 |

### AMQP — iot

_Run: `20260831T180248_amqp_iot`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 10.87 | 0.2733 | 0.188 | 0.15% | 28.01 MB | 0.0208 | — | — |
| 250 KB | receiver | N/A (single chunk)¹ | 11.2477 | N/A (single chunk)¹ | 0.16% | 26.77 MB | 0.0229 | — | True |
| 1 MB | sender | 55.16 | 0.2820 | 0.152 | 0.14% | 28.31 MB | 0.0999 | — | — |
| 1 MB | receiver | N/A (single chunk)¹ | 55.7371 | N/A (single chunk)¹ | 0.14% | 27.68 MB | 0.1009 | — | True |
| 5 MB | sender | 278.42 | 0.2996 | 0.151 | 0.13% | 30.31 MB | 0.4651 | — | — |
| 5 MB | receiver | 221.51 | 57.2991 | 0.189 | 0.13% | 30.67 MB | 0.4685 | — | True |
| 20 MB | sender | 367.52 | 0.2854 | 0.457 | 0.13% | 30.60 MB | 0.6162 | — | — |
| 20 MB | receiver | 339.09 | 29.0623 | 0.495 | 0.14% | 31.36 MB | 0.6297 | — | True |
| 50 MB | sender | 2711.78 | 0.2984 | 0.155 | 0.14% | 49.43 MB | 4.5745 | — | — |
| 50 MB | receiver | 2662.16 | 50.1845 | 0.158 | 0.14% | 50.23 MB | 4.5984 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 19.26 | 666 | 563,376 | 120.07 | 6 | 0.106 | 0.234 |
| 1 MB |  | 58.15 | 2,543 | 2,288,959 | 118.29 | 36 | 0.144 | 0.315 |
| 5 MB |  | 280.79 | 12,001 | 11,367,747 | 116.82 | 145 | 0.149 | 0.324 |
| 20 MB |  | 370.16 | 45,530 | 45,622,300 | 117.54 | 586 | 0.453 | 0.986 |
| 50 MB |  | 2714.48 | 114,950 | 113,379,754 | 116.25 | 1175 | 0.155 | 0.334 |

### AMQP — harsh

_Run: `20260902T062746_amqp_harsh`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 22.65 | 0.4092 | 0.090 | 0.10% | 28.33 MB | 0.0292 | — | — |
| 250 KB | receiver | N/A (single chunk)¹ | 22.8009 | N/A (single chunk)¹ | 0.10% | 27.00 MB | 0.0292 | — | True |
| 1 MB | sender | 84.46 | 0.3832 | 0.099 | 0.10% | 28.22 MB | 0.1062 | — | — |
| 1 MB | receiver | N/A (single chunk)¹ | 84.8710 | N/A (single chunk)¹ | 0.10% | 28.87 MB | 0.1057 | — | True |
| 5 MB | sender | 233.95 | 0.3258 | 0.179 | 0.10% | 29.56 MB | 0.2947 | — | — |
| 5 MB | receiver | 161.28 | 73.8187 | 0.260 | 0.10% | 30.57 MB | 0.2969 | — | True |
| 20 MB | sender | 885.04 | 0.4202 | 0.190 | 0.11% | 34.97 MB | 1.2442 | — | — |
| 20 MB | receiver | 789.83 | 95.8210 | 0.212 | 0.11% | 36.25 MB | 1.2562 | — | True |
| 50 MB | sender | 2134.80 | 0.4270 | 0.196 | 0.14% | 45.11 MB | 3.6521 | — | — |
| 50 MB | receiver | 2059.37 | 76.2581 | 0.204 | 0.14% | 46.08 MB | 3.6863 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 31.93 | 749 | 568,802 | 122.19 | 6 | 0.064 | 0.142 |
| 1 MB |  | 88.25 | 2,716 | 2,304,565 | 119.78 | 58 | 0.095 | 0.209 |
| 5 MB |  | 237.51 | 12,386 | 11,523,869 | 119.80 | 124 | 0.177 | 0.388 |
| 20 MB |  | 888.46 | 48,383 | 46,077,290 | 119.71 | 533 | 0.189 | 0.415 |
| 50 MB |  | 2139.26 | 121,233 | 115,292,441 | 119.90 | 1826 | 0.196 | 0.431 |

### AMQP — mobile

_Run: `20260904T011847_amqp_mobile`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 10.82 | 0.2681 | 0.189 | 0.11% | 27.93 MB | 0.0146 | — | — |
| 250 KB | receiver | N/A (single chunk)¹ | 10.8438 | N/A (single chunk)¹ | 0.10% | 26.81 MB | 0.0135 | — | True |
| 1 MB | sender | 45.17 | 0.1350 | 0.186 | 0.10% | 28.11 MB | 0.0571 | — | — |
| 1 MB | receiver | N/A (single chunk)¹ | 45.2383 | N/A (single chunk)¹ | 0.16% | 28.60 MB | 0.0905 | — | True |
| 5 MB | sender | 234.75 | 0.2984 | 0.179 | 0.11% | 29.39 MB | 0.3221 | — | — |
| 5 MB | receiver | 189.26 | 45.9457 | 0.222 | 0.10% | 29.86 MB | 0.2936 | — | True |
| 20 MB | sender | 920.22 | 0.1773 | 0.182 | 0.10% | 35.56 MB | 1.1362 | — | — |
| 20 MB | receiver | 874.08 | 46.7865 | 0.192 | 0.10% | 36.39 MB | 1.1424 | — | True |
| 50 MB | sender | 2305.25 | 0.2660 | 0.182 | 0.10% | 46.61 MB | 2.8451 | — | — |
| 50 MB | receiver | 2260.65 | 44.9812 | 0.186 | 0.10% | 47.34 MB | 2.8629 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 18.29 | 680 | 560,968 | 119.13 | 34 | 0.112 | 0.245 |
| 1 MB |  | 47.06 | 2,428 | 2,272,417 | 116.71 | 110 | 0.178 | 0.386 |
| 5 MB |  | 236.69 | 11,292 | 11,291,069 | 115.36 | 1023 | 0.177 | 0.382 |
| 20 MB |  | 925.36 | 43,992 | 45,126,183 | 115.18 | 2441 | 0.181 | 0.390 |
| 50 MB |  | 2307.34 | 109,352 | 112,769,928 | 115.09 | 1741 | 0.182 | 0.391 |

### AMQP — satellite

_Run: `20261120T155429_amqp_satellite`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 9.77 | 0.6377 | 0.210 | 0.11% | 27.73 MB | 0.1747 | 1019 | — |
| 250 KB | receiver | N/A (single chunk)¹ | 11.8905 | N/A (single chunk)¹ | 0.13% | 26.71 MB | 0.2250 | 1164 | True |
| 1 MB | sender | 14.36 | 0.6353 | 0.584 | 0.11% | 28.16 MB | 0.2502 | 1470 | — |
| 1 MB | receiver | N/A (single chunk)¹ | 17.4863 | N/A (single chunk)¹ | 0.12% | 27.66 MB | 0.3123 | 1713 | True |
| 5 MB | sender | 67.39 | 0.6496 | 0.622 | 0.12% | 28.26 MB | 1.2492 | 6657 | — |
| 5 MB | receiver | 48.13 | 22.6089 | 0.872 | 0.13% | 29.03 MB | 1.3726 | 6919 | True |
| 20 MB | sender | 260.59 | 0.6671 | 0.644 | 0.12% | 29.42 MB | 4.7892 | 25557 | — |
| 20 MB | receiver | 242.04 | 22.0317 | 0.693 | 0.13% | 30.66 MB | 5.0049 | 25831 | True |
| 50 MB | sender | 636.75 | 0.6450 | 0.659 | 0.15% | 32.70 MB | 14.0244 | 62161 | — |
| 50 MB | receiver | 611.78 | 28.5055 | 0.686 | 0.15% | 33.94 MB | 14.5087 | 62439 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 24.19 | 645 | 560,506 | 118.95 | 14 | 0.085 | 0.185 |
| 1 MB |  | 24.89 | 2,293 | 2,115,548 | 101.75 | 108 | 0.337 | 0.680 |
| 5 MB |  | 79.50 | 11,487 | 11,359,816 | 116.67 | 753 | 0.528 | 1.143 |
| 20 MB |  | 268.26 | 44,459 | 45,101,003 | 115.06 | 2468 | 0.625 | 1.345 |
| 50 MB |  | 644.64 | 111,172 | 113,151,455 | 115.82 | 6741 | 0.651 | 1.404 |

## GRPC

### GRPC — good

_Run: `20260913T090042_grpc_good`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 0.44 | 0.0905 | 4.613 | 0.37% | 39.83 MB | 0.0020 | — | True |
| 250 KB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.25% | 37.42 MB | 0.0010 | — | True |
| 1 MB | sender | 1.18 | 0.0918 | 7.104 | 0.21% | 42.24 MB | 0.0031 | — | True |
| 1 MB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.24% | 40.25 MB | 0.0031 | — | True |
| 5 MB | sender | 4.67 | 0.0721 | 8.991 | 0.14% | 45.28 MB | 0.0083 | — | True |
| 5 MB | receiver | 3.51 | — | 11.936 | 0.33% | 46.05 MB | 0.0188 | — | True |
| 20 MB | sender | 24.99 | 0.0933 | 6.714 | 0.17% | 45.03 MB | 0.0528 | — | True |
| 20 MB | receiver | 23.65 | — | 7.095 | 0.33% | 47.49 MB | 0.1020 | — | True |
| 50 MB | sender | 58.79 | 0.0873 | 7.134 | 0.16% | 45.48 MB | 0.1155 | — | True |
| 50 MB | receiver | 54.70 | — | 7.668 | 0.32% | 49.41 MB | 0.2332 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 0.65 | 357 | 284,519 | 11.14 | 9 | 3.137 | 3.486 |
| 1 MB |  | 1.41 | 1,375 | 1,183,033 | 12.82 | 202 | 5.965 | 6.730 |
| 5 MB |  | 4.90 | 6,729 | 5,743,798 | 9.55 | 323 | 8.568 | 9.387 |
| 20 MB |  | 25.32 | 26,380 | 22,926,267 | 9.32 | 931 | 6.626 | 7.244 |
| 50 MB |  | 59.28 | 66,343 | 57,260,002 | 9.21 | 1593 | 7.076 | 7.728 |

### GRPC — iot

_Run: `20260831T190129_grpc_iot`_ — *partial run: some sizes were attempted but never completed/recorded client-side (large files struggle under this profile, ISSUES.md OPEN-4); missing client sizes are marked 'not run' and the packet-side table may still list their (degraded) captures.*

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 5.98 | 0.4620 | 0.342 | 0.14% | 39.15 MB | 0.0104 | — | True |
| 250 KB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.15% | 38.48 MB | 0.0104 | — | True |
| 1 MB | sender | 17.81 | 0.3577 | 0.471 | 0.13% | 41.83 MB | 0.0291 | — | True |
| 1 MB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.15% | 43.07 MB | 0.0322 | — | True |
| 5 MB | sender | 89.46 | 0.5068 | 0.469 | 0.15% | 45.57 MB | 0.1631 | — | True |
| 5 MB | receiver | 70.20 | — | 0.598 | 0.17% | 46.01 MB | 0.1903 | — | True |
| 20 MB | sender | 352.59 | 0.4219 | 0.476 | 0.15% | 47.84 MB | 0.6811 | — | True |
| 20 MB | receiver | 334.43 | — | 0.502 | 0.17% | 51.84 MB | 0.7607 | — | True |
| 50 MB | not run |  |  |  |  |  |  |  |  |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 6.88 | 420 | 296,739 | 15.91 | 32 | 0.298 | 0.345 |
| 1 MB |  | 18.68 | 1,465 | 1,164,700 | 11.07 | 55 | 0.449 | 0.499 |
| 5 MB |  | 90.50 | 6,921 | 5,808,473 | 10.79 | 340 | 0.463 | 0.513 |
| 20 MB |  | 353.79 | 27,247 | 23,312,151 | 11.16 | 1385 | 0.474 | 0.527 |
| 50 MB | not run |  |  |  |  |  |  |  |

### GRPC — harsh

_Run: `20261120T140930_grpc_harsh`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 10.02 | 0.5995 | 0.204 | 0.12% | 39.82 MB | 0.1750 | 982 | True |
| 250 KB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.13% | 38.00 MB | 0.1751 | 886 | True |
| 1 MB | sender | 44.33 | 0.9597 | 0.189 | 0.12% | 42.27 MB | 0.7986 | 4344 | True |
| 1 MB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.13% | 42.14 MB | 0.8742 | 4266 | True |
| 5 MB | sender | 186.92 | 0.6487 | 0.224 | 0.15% | 47.25 MB | 4.1069 | 18254 | True |
| 5 MB | receiver | 148.90 | — | 0.282 | 0.17% | 47.83 MB | 4.6821 | 18157 | True |
| 20 MB | sender | 765.88 | 0.8668 | 0.219 | 0.13% | 51.87 MB | 14.6770 | 74970 | True |
| 20 MB | receiver | 728.00 | — | 0.230 | 0.15% | 55.57 MB | 16.7392 | 74862 | True |
| 50 MB | sender | 1971.97 | 0.5206 | 0.213 | 0.14% | 61.95 MB | 41.3276 | 192713 | True |
| 50 MB | receiver | 1929.84 | — | 0.217 | 0.16% | 66.12 MB | 47.3626 | 192620 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 11.56 | 445 | 318,388 | 24.37 | 29 | 0.177 | 0.220 |
| 1 MB |  | 45.87 | 1,603 | 1,221,321 | 16.47 | 87 | 0.183 | 0.213 |
| 5 MB |  | 187.87 | 7,565 | 5,959,892 | 13.68 | 360 | 0.223 | 0.254 |
| 20 MB |  | 768.09 | 29,986 | 23,846,894 | 13.71 | 1548 | 0.218 | 0.248 |
| 50 MB |  | 1973.71 | 75,296 | 59,845,094 | 14.15 | 4103 | 0.213 | 0.243 |

### GRPC — mobile

**Not run.**

### GRPC — satellite

_Run: `20261120T161301_grpc_satellite`_

#### Client measurements

| Size | Side | Duration s | Latency s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|---|
| 250 KB | sender | 7.80 | 1.1733 | 0.263 | 0.18% | 39.41 MB | 0.2120 | 759 | True |
| 250 KB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.18% | 38.10 MB | 0.1751 | 627 | True |
| 1 MB | sender | 14.86 | 1.2702 | 0.565 | 0.21% | 41.57 MB | 0.4618 | 1440 | True |
| 1 MB | receiver | N/A (single chunk)¹ | — | N/A (single chunk)¹ | 0.61% | 42.98 MB | 1.2395 | 1318 | True |
| 5 MB | sender | 52.78 | 1.1872 | 0.795 | 0.26% | 45.83 MB | 2.0156 | 5134 | True |
| 5 MB | receiver | 39.04 | — | 1.074 | 0.22% | 45.85 MB | 1.6714 | 5017 | True |
| 20 MB | sender | 213.08 | 5.1138 | 0.787 | 0.21% | 46.88 MB | 6.6117 | 20703 | True |
| 20 MB | receiver | 199.69 | — | 0.840 | 0.22% | 51.80 MB | 7.0331 | 20562 | True |
| 50 MB | sender | 593.18 | 1.1120 | 0.707 | 0.14% | 50.27 MB | 12.7155 | 57968 | True |
| 50 MB | receiver | 564.92 | — | 0.742 | 0.17% | 56.72 MB | 14.8025 | 57793 | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 17.82 | 367 | 284,175 | 11.01 | 3 | 0.115 | 0.128 |
| 1 MB |  | 16.79 | 1,369 | 1,152,313 | 9.89 | 145 | 0.500 | 0.549 |
| 5 MB |  | 55.73 | 6,564 | 5,745,242 | 9.58 | 507 | 0.753 | 0.825 |
| 20 MB |  | 219.95 | 25,778 | 23,099,930 | 10.15 | 2391 | 0.763 | 0.840 |
| 50 MB |  | 596.04 | 64,073 | 57,815,535 | 10.27 | 6841 | 0.704 | 0.776 |

## LWM2M

### LWM2M — good

_Run: `20260830T183513_lwm2m_good`_

#### Client measurements

| Size | Download s | Reg. RTT s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 23.0229 | 0.1549 | 0.089 | 0.14% | 27.83 MB | 0.0406 | — | True |
| 1 MB | 87.5407 | 0.0772 | 0.096 | 0.15% | 29.35 MB | 0.1683 | — | True |
| 5 MB | 451.8463 | 0.0765 | 0.093 | 0.35% | 39.74 MB | 1.9557 | — | True |
| 20 MB | 1907.2252 | 0.0766 | 0.088 | 0.69% | 105.52 MB | 16.4097 | — | True |
| 50 MB | 5542.2769 | 0.0988 | 0.076 | 0.83% | 153.34 MB | 57.5085 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 23.32 | 517 | 313,000 | 22.27 | 1 | 0.088 | 0.107 |
| 1 MB |  | 87.84 | 2,069 | 1,276,292 | 21.72 | 1 | 0.095 | 0.116 |
| 5 MB |  | 452.13 | 10,302 | 6,380,212 | 21.69 | 6 | 0.093 | 0.113 |
| 20 MB |  | 1907.54 | 41,180 | 25,562,677 | 21.89 | 16 | 0.088 | 0.107 |
| 50 MB |  | 5542.65 | 103,083 | 63,928,844 | 21.93 | 53 | 0.076 | 0.092 |

### LWM2M — iot

_Run: `20260831T194430_lwm2m_iot`_

#### Client measurements

| Size | Download s | Reg. RTT s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 100.7867 | 0.9699 | 0.020 | 0.13% | 28.08 MB | 0.1633 | — | True |
| 1 MB | 411.5706 | 0.4235 | 0.020 | 0.15% | 31.79 MB | 0.7527 | — | True |
| 5 MB | 2057.9846 | 0.4320 | 0.020 | 0.19% | 53.27 MB | 4.9857 | — | True |
| 20 MB | 8399.1565 | 0.3344 | 0.020 | 0.26% | 143.63 MB | 26.9546 | — | True |
| 50 MB | 21662.2129 | 0.3259 | 0.019 | 0.26% | 257.39 MB | 69.9343 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 102.35 | 531 | 317,728 | 24.11 | 1 | 0.020 | 0.025 |
| 1 MB |  | 412.96 | 2,116 | 1,283,693 | 22.42 | 3 | 0.020 | 0.025 |
| 5 MB |  | 2059.61 | 10,546 | 6,434,272 | 22.72 | 25 | 0.020 | 0.025 |
| 20 MB |  | 8399.38 | 42,289 | 25,859,984 | 23.31 | 118 | 0.020 | 0.025 |
| 50 MB |  | 21663.05 | 105,596 | 64,585,511 | 23.19 | 239 | 0.019 | 0.024 |

### LWM2M — harsh

**Not run.**

### LWM2M — mobile

_Run: `20260903T182303_lwm2m_mobile`_

#### Client measurements

| Size | Download s | Reg. RTT s | Goodput Mbps | Avg CPU | Peak RAM | Energy J | Samples | Integrity |
|---|---|---|---|---|---|---|---|---|
| 250 KB | 75.5116 | 0.3314 | 0.027 | 0.15% | 27.81 MB | 0.1389 | — | True |
| 1 MB | 307.0065 | 0.4388 | 0.027 | 0.17% | 31.18 MB | 0.6471 | — | True |
| 5 MB | 1555.6378 | 0.3009 | 0.027 | 0.21% | 48.78 MB | 4.0587 | — | True |
| 20 MB | 6400.9069 | 0.4539 | 0.026 | 0.30% | 120.09 MB | 23.9023 | — | True |
| 50 MB | 16533.6890 | 0.2238 | 0.025 | 0.31% | 214.38 MB | 64.4435 | — | True |

#### Packet-side measurements (pcap, re-analyzed)

| Size | QoS | Duration s² | Packets | Wire bytes | Overhead % | Retrans | Pcap goodput Mbps | Wire Mbps |
|---|---|---|---|---|---|---|---|---|
| 250 KB |  | 76.38 | 522 | 313,082 | 22.30 | 0 | 0.027 | 0.033 |
| 1 MB |  | 308.11 | 2,090 | 1,277,048 | 21.79 | 0 | 0.027 | 0.033 |
| 5 MB |  | 1557.05 | 10,434 | 6,385,000 | 21.78 | 0 | 0.027 | 0.033 |
| 20 MB |  | 6402.06 | 41,698 | 25,582,250 | 21.99 | 0 | 0.026 | 0.032 |
| 50 MB |  | 16534.32 | 104,355 | 63,988,356 | 22.05 | 0 | 0.025 | 0.031 |

### LWM2M — satellite

**Not run.**

---

**How to read this document**

- All pcap time metrics (`Duration s²`, `Pcap goodput`, `Wire Mbps`) are
  **re-analyzed from the stored pcaps** with the current analyzer (commit
  d2426af): duration spans the first to the last frame of the
  protocol's own traffic window, so idle startup and ARP/ICMPv6 noise no
  longer inflate it (ISSUES.md FIXED-9). Byte-derived columns (packets, wire
  bytes, overhead, retransmissions) are identical to the run CSVs.
- ¹ **N/A (single chunk)**: a file that fits in one 1 MB chunk spans no
  measurable receiver-side arrival window; pre-fix runs recorded misleading
  ~0.00 s / 1500+ Mbps cells there, which are shown as N/A (ISSUES.md
  FIXED-13).
- ² see the first bullet.
- Under high-latency profiles (`satellite`, `harsh`) the pcap window also
  includes protocol control traffic around the data transfer itself --
  connection/channel setup, keepalive/BDP pings, and broker-receiver QoS
  retransmissions -- so `Duration s²` can exceed the client-side transfer
  window. The client-side columns are the transfer-only view.
- ⚠ marks captures that dropped frames (captured wire bytes below the
  verified file size): the overhead/throughput columns of that row are
  unreliable (see docs/troubleshooting.md -- re-running the transfer is the
  remedy, which was not done for the historical coap harsh 20/50 MB rows).
- **MQTT/AMQP sender duration**: runs recorded before commit d2426af include
  the metadata-ACK round trip inside `Duration s`; runs after it (all runs
  dated 2026-11-20) time chunk transmission only (ISSUES.md FIXED-12).
- **Samples** is the CPU/RAM sample count behind the averages
  (ISSUES.md FIXED-10). Pre-fix runs did not record it (—) and their
  CPU/energy can read 0 on very fast transfers.
- Sender-side **Integrity** is — for MQTT/AMQP by design: the sender hands
  the file to the broker and cannot observe the receiver's checksum result.
  gRPC sender rows show the server-reported result from the Upload reply.
- **"not run"** combinations were never executed: gRPC under `mobile`,
  LwM2M under `harsh` (blockwise pull at 300 ms RTT takes hours, ISSUES.md
  OPEN-4) and CoAP/LwM2M under `satellite`.
- Per protocol × profile the newest **complete** run is used; older
  partial runs (e.g. the aborted gRPC harsh sweep) are superseded.
- **Network scenario asymmetry** (ISSUES.md OPEN-5): the brokers are stock
  images and are not tc-shaped, so MQTT/AMQP face one constrained link
  while HTTP/CoAP/gRPC/LwM2M face shaping on both ends. Keep this in mind
  when comparing protocols under the same profile.

