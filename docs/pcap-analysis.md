# pcap analysis — `common/pcap_analyzer.py`

`analyze_pcap()` turns one pcap into the 16 metrics logged to
`pcap_measurements*.csv`. It shells out to `tshark` (Wireshark's CLI) four
times. This page documents every query, the per-protocol config, and the
retransmission logic in detail.

---

## 1. tshark resolution and invocation

```python
def resolve_tshark():
    # 1. PATH lookup
    # 2. fallback candidates:
    #    C:\Program Files\Wireshark\tshark.exe
    #    C:\Program Files (x86)\Wireshark\tshark.exe
    #    /usr/bin/tshark
    #    /usr/sbin/tshark
    # raises FileNotFoundError if none found
```

Every query uses the same base flags:

```bash
tshark -r <pcap> -T fields -E separator=, -E quote=d -E header=y \
       [-Y <display filter>] [-e field ...]
```

- `-T fields` → machine-readable output.
- `-E separator=,` + `-E quote=d` → CSV with double-quoted fields.
- `-E header=y` → first line is the field names (the parser skips it).
- `-Y` applies a display filter; `-e` selects one field per flag.

---

## 2. Per-protocol configuration

```python
PROTOCOL_CONFIG = {
    "mqtt": {"filter": "mqtt",
             "type_fields": ["mqtt.msgtype"],         # frame-type breakdown
             "is_tcp": True},                         # TCP retransmission path
    "http": {"filter": "http",
             "type_fields": ["http.request.method", "http.response.code"],
             "is_tcp": True},
    "coap": {"filter": "coap",
             "type_fields": ["coap.code"],            # 1 = GET, 3 = PUT, 69 = 4.05, 95 = 2.31, ...
             "is_tcp": False},                        # UDP → CoAP retransmission path
}
```

---

## 3. The four tshark passes

### Pass A — all frames

```
fields: frame.number, frame.len, frame.time_relative, ip.proto
```

Accumulates `total_packets`, `total_wire_bytes` (sum of `frame.len`), and
`duration = last frame.time_relative`.

### Pass B — protocol frames

```
-Y <filter>  fields: frame.number, frame.len, <type_fields...>
```

Accumulates `protocol_packets`, `protocol_wire_bytes`, and a per-type histogram
`packet_types` (e.g. HTTP method/code pairs, MQTT msgtypes, CoAP codes). Frame
type is the first non-empty type field (`_parse_frame_type` reads the column at
`2 + field_idx` because `frame.number, frame.len` are the first two columns).

### Pass C — retransmissions

TCP protocols:

```
-Y "tcp.analysis.retransmission or tcp.analysis.fast_retransmission
    or tcp.analysis.spurious_retransmission"   fields: frame.number
```

`retransmissions` = number of matching frames. This is Wireshark's own
`tcp.analysis.*` tracking (based on sequence-number heuristics).

CoAP (UDP) — custom, see §4.

### Pass D — derived metrics

```python
total_overhead_bytes = total_wire_bytes - file_size_bytes
overhead_percentage  = total_overhead_bytes / file_size_bytes * 100
wire_throughput_mbps = total_wire_bytes * 8 / (duration * 1e6)
goodput_mbps         = file_size_bytes * 8 / (duration * 1e6)
```

Plus the completeness warning when `total_wire_bytes < file_size_bytes`.

---

## 4. CoAP retransmission detection (the subtle one)

CoAP is UDP, so there is no `tcp.analysis.*`; retransmissions must be inferred
from the traffic itself.

### The two pitfalls

1. **A normal exchange has one MID in two frames** — the request is a
   Confirmable (CON) message, and per RFC 7252 the piggybacked **ACK echoes the
   request's MID**. So "same MID appears twice" is *not* a retransmission.
2. **Duplicate ACKs can appear** (e.g. a lost ACK, or a server that processes a
   retransmitted CON twice) — MID counts above 2 are not all retransmissions
   either.

### The rule used

Only **CON messages are ever retransmitted** (NON/RST/ACK are not), and a
retransmitted CON reuses the same MID **from the same source**. Therefore:

```
retransmissions = Σ over (MID, ip.src) of max(0, #frames with coap.type == CON − 1)
```

Implementation:

```python
con_output = run_tshark(pcap_file,
                        display_filter="coap",
                        fields=["coap.type", "coap.mid", "ip.src"])

con_counts = {}
for line in ...:
    msg_type, mid, src = parts            # 0 = CON
    if msg_type == "0" and mid and src:
        con_counts[(mid, src)] += 1

tcp_retransmissions = sum(c - 1 for c in con_counts.values() if c > 1)
```

`coap.type` values: `0` = CON, `1` = NON, `2` = ACK, `3` = RST.

### Worked example (real capture, 250 KB file)

| MID occurrences | Interpretation | Contribution |
|---|---|---|
| 399 MIDs × (1 CON + 1 ACK) | normal exchanges | 0 each |
| 7 MIDs × (2 CON + 1–2 ACK) | one CON retransmitted each | 1 each → **7** |
| 1 MID × (1 CON + 2 ACK) | duplicate ACK only | **0** (CON count = 1) |

Total: **7 retransmissions**, whereas a naive "count MID occurrences − 1" would
have reported ~412. (This was a real bug before the fix: the code parsed the
output as 3 columns when only 2 were requested, so the value was **always 0**.)

---

## 5. What a "PCAP ANALYSIS" console block shows

```
========== PCAP ANALYSIS ==========
Protocol:              coap
File:                  binary_file_250kb.bin
QoS:                   (only for MQTT)

--- Traffic ---
File size:             N B
Captured packets:      N
Captured bytes:        N B
Protocol packets:      N
Protocol frame bytes:  N B

--- Overhead ---
Total overhead:        N B
Overhead percentage:   N%

--- Performance ---
Duration:              N s
Goodput:               N Mbps
Wire throughput:       N Mbps
Retransmissions:       N

--- Protocol packet types ---
<type>                 <count>        (e.g. "2.31 Continue  391")
===================================
```

---

## 6. `print_result` vs CSV

`print_result()` is purely cosmetic. The authoritative record is the dict
returned by `analyze_pcap`, which `benchmark_manager` passes to
`write_to_file_pcap()`. Column semantics are in [metrics-schema.md](metrics-schema.md).
