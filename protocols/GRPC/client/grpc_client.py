"""
    gRPC sender: streams a file in 1 MB chunks to the upload server.
    / used by docker-compose.yaml & docker-compose.automated.yaml

    Mirrors the MQTT chunking contract: chunk 1 carries JSON-like metadata
    (filename, size, chunk count, checksum) inside the protobuf oneof, every
    following chunk carries raw bytes. The server's UploadResult reports
    integrity + receiver-side duration.
"""
import argparse
import math
import os
import sys
import time

import grpc

# Generated stubs live in /opt/grpc_stubs inside the container (compiled
# during the docker build, outside the bind-mounted /app). Locally they can
# be generated next to the proto file instead.
if os.path.isdir("/opt/grpc_stubs"):
    sys.path.insert(0, "/opt/grpc_stubs")
else:
    sys.path.insert(
        0,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "proto")),
    )

import file_transfer_pb2 as pb
import file_transfer_pb2_grpc as pb_grpc

from common.file_manager import get_file_path_input
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_grpc

SERVER = "grpc-server:50051"

CHUNK_SIZE = 1024 * 1024

# A fixed whole-RPC deadline truncates legitimate transfers on bandwidth-limited
# network profiles, so scale the deadline with the payload against a
# conservative throughput floor (~256 kbit/s, the harsh profile's TBF egress).
# Both values can be overridden from the environment.
GRPC_BASE_TIMEOUT_S = float(os.getenv("GRPC_BASE_TIMEOUT_S", "120"))
GRPC_MIN_THROUGHPUT_BPS = int(os.getenv("GRPC_MIN_THROUGHPUT_BPS", "32000"))


def measure_latency(channel):
    """Unary Ping round-trip (mirrors HTTP TCP-RTT style latency probe)."""
    stub = pb_grpc.FileTransferStub(channel)
    t0 = time.perf_counter()
    stub.Ping(pb.PingRequest(client_timestamp_ms=int(time.time() * 1000)), timeout=10)
    return time.perf_counter() - t0


def send_file(filename):
    filepath = os.path.join(get_file_path_input(filename))
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    channel = grpc.insecure_channel(SERVER)
    grpc.channel_ready_future(channel).result(timeout=30)

    stub = pb_grpc.FileTransferStub(channel)

    file_size = os.path.getsize(filepath)
    total_chunks = math.ceil(file_size / CHUNK_SIZE)
    print(f"\n--- Starting transfer: {filename} ({file_size / 1024 / 1024:.2f} MB) ---")

    checksum = compute_sha256_file(filepath)
    latency = measure_latency(channel)

    def chunk_iterator():
        # Chunk 1: metadata
        yield pb.Chunk(
            metadata=pb.Metadata(
                filename=filename,
                total_size=file_size,
                total_chunks=total_chunks,
                checksum=checksum,
            )
        )
        with open(filepath, "rb") as f:
            for chunk_num in range(total_chunks):
                data = f.read(CHUNK_SIZE)
                yield pb.Chunk(data=data)
                if chunk_num % 10 == 0 or chunk_num == total_chunks - 1:
                    print(f"Sent chunk {chunk_num + 1}/{total_chunks}")

    monitor = ResourceMonitor(sample_interval=0.01)
    monitor.start()

    deadline_s = max(
        600.0,
        GRPC_BASE_TIMEOUT_S + (file_size * 8) / GRPC_MIN_THROUGHPUT_BPS,
    )

    start_time = time.time()
    integrity_ok = False
    receiver_duration_field = "X"
    rpc_error = None
    try:
        result = stub.Upload(chunk_iterator(), timeout=deadline_s)
        integrity_ok = result.integrity_ok
        receiver_duration_field = f"{result.receiver_duration_s:.2f}"
    except grpc.RpcError as e:
        rpc_error = f"{e.code().name}: {e.details()}"
        print(f"  -> gRPC transfer failed: {rpc_error}")
    finally:
        duration = time.time() - start_time
        resource_stats = monitor.stop()

    goodput_mbps = (file_size * 8) / (duration * 1_000_000)

    measurements = [
        {
            "protocol": "grpc",
            "side": "sender",
            "file_size": file_size / (1024 * 1024),
            "sender_duration": f"{duration:.2f}",
            "receiver_duration": receiver_duration_field,
            "latency": f"{latency:.4f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "integrity_ok": integrity_ok,
            "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
            "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
            "energy_est": f"{resource_stats['energy_j']:.4f}",
        }
    ]
    write_to_file_grpc(measurements)

    channel.close()

    print("Finished sending file.")
    print(f"Latency (Ping RTT): {latency:.4f}s | Sender Time: {duration:.2f}s")
    print(f"Integrity OK: {integrity_ok}")
    if rpc_error:
        print(f"RPC error: {rpc_error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)

    args = parser.parse_args()

    time.sleep(5)  # Wait for server

    send_file(args.file)
