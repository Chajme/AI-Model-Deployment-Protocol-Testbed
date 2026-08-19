# Documentation — AI-Model-Deployment-Protocol-Testbed

Code-level documentation for the MQTT / HTTP / CoAP transfer benchmark testbed.
Start with [architecture.md](architecture.md) for the big picture, then follow
the pipeline through the rest of the docs.

| Page | Contents |
|---|---|
| [architecture.md](architecture.md) | networks, containers, compose stacks, image build, data flow overview |
| [measurement-pipeline.md](measurement-pipeline.md) | one transfer end-to-end: capture → transfer → analysis → CSV |
| [protocol-transfers.md](protocol-transfers.md) | per-protocol internals: MQTT chunking/QoS, HTTP streaming, CoAP blockwise |
| [pcap-analysis.md](pcap-analysis.md) | `common/pcap_analyzer.py`: tshark filters, fields, metrics, retransmission detection |
| [metrics-schema.md](metrics-schema.md) | exact CSV schemas and column semantics for every producer |
| [network-chaos.md](network-chaos.md) | `runner.py` sweep + `tc` profiles (netem/tbf parameters) |
| [charts.md](charts.md) | `common/charts.py`: metric catalog, auto line/bar, series, aggregation, flags |
| [cli-reference.md](cli-reference.md) | CLI references and environment variables for every entry point |
| [troubleshooting.md](troubleshooting.md) | symptom → root cause → fix, with code pointers |

## How the pieces fit together

```
data/binary_file_generator.py  ──►  data/*.bin          (payloads)

docker-compose.yaml  /  docker-compose.automated.yaml   (containers + networks)

protocols/benchmark_manager.py  ─►  common/packet_capture.py   (tcpdump in sidecar)
   │                                protocols/<proto>/client   (transfer)
   │                                common/packet_capture.py   (pcap copied out)
   └──► common/pcap_analyzer.py     (tshark analysis)
          └──► output/write_csv.py  (pcap_measurements.csv)

protocols/<proto>/client  ─►  output/write_csv.py  (…_measurements.csv)
                                  │          every row + run.json land in
                                  ▼          output/runs/<run_id>/  (common/runs.py)
                           common/charts.py  ─►  <run>/charts/*.png  (--run <run_id>)
```

**Quick orientation for new readers**

- The **host harness** (`protocols/benchmark_manager.py`, driven directly or by
  `runner.py`) is the only thing that talks to Docker from the host. Every
  protocol-specific behavior lives inside the client containers.
- Two **capture-critical details** are handled before each run:
  segmentation offloads (GRO/GSO/TSO) are disabled so the pcap shows real
  MTU-sized frames, and tcpdump uses an 8 MiB kernel buffer so bursts don't
  drop frames (see [pcap-analysis.md](pcap-analysis.md)).
- Every measurement is written **twice**: client-side runtime metrics (from the
  sender/receiver process) and packet-side metrics (from tshark). The two views
  are intentionally independent and both include an integrity verdict.
