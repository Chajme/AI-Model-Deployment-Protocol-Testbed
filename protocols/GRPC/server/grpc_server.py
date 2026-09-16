"""
    gRPC upload server: reassembles client-streamed chunks and verifies
    the SHA-256 checksum of the whole file.
    / used by docker-compose.yaml & docker-compose.automated.yaml

    The generated protobuf modules are compiled into protocols/GRPC/proto/
    during the docker build (see Dockerfile).
"""
import os
import sys
import time
from concurrent import futures

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

from common.file_manager import get_file_path_output, output_directory_exists
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_grpc

CHUNK_SIZE_LIMIT = 4 * 1024 * 1024  # gRPC default max message size


class FileTransferServicer(pb_grpc.FileTransferServicer):

    def Ping(self, request, context):
        return pb.PingReply(
            client_timestamp_ms=request.client_timestamp_ms,
            server_timestamp_ms=int(time.time() * 1000),
        )

    def Upload(self, request_iterator, context):
        metadata = None
        received_chunks = 0
        received_bytes = 0
        transfer_start_time = None
        file_handle = None
        monitor = None
        tmp_path = None

        try:
            for chunk in request_iterator:
                if chunk.WhichOneof("payload") == "metadata":
                    metadata = chunk.metadata
                    print(
                        f"\nIncoming file: {metadata.filename} "
                        f"({metadata.total_chunks} chunks)."
                    )
                    # Write to a temp file and only publish the final name once
                    # the checksum matches, so an aborted transfer can never
                    # leave a truncated file that looks complete.
                    tmp_path = get_file_path_output(metadata.filename) + ".part"
                    file_handle = open(tmp_path, "wb")
                    monitor = ResourceMonitor(sample_interval=0.01)
                    monitor.start()
                    continue

                if metadata is None:
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                                  "first chunk must carry metadata")

                if transfer_start_time is None:
                    transfer_start_time = time.perf_counter()

                file_handle.write(chunk.data)
                received_chunks += 1
                received_bytes += len(chunk.data)

                if received_chunks % 10 == 0:
                    print(f"Received chunk {received_chunks}/{metadata.total_chunks}")

            if metadata is None or file_handle is None:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "no metadata received")

            receiver_duration = time.perf_counter() - (
                transfer_start_time or time.perf_counter()
            )
            file_handle.close()
            file_handle = None
            resource_stats = monitor.stop() if monitor else {}
            monitor = None
        except Exception:
            if file_handle is not None:
                file_handle.close()
                file_handle = None
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
                tmp_path = None
            raise
        finally:
            # Always release resources even if the client cancels the stream.
            if file_handle is not None:
                file_handle.close()
            if monitor is not None:
                monitor.stop()

        integrity_ok = False
        if received_bytes != metadata.total_size:
            print(
                f"Size mismatch for {metadata.filename}: "
                f"{received_bytes} != {metadata.total_size}"
            )
        else:
            actual_checksum = compute_sha256_file(tmp_path)
            integrity_ok = actual_checksum == metadata.checksum

        final_path = get_file_path_output(metadata.filename)
        if integrity_ok:
            os.replace(tmp_path, final_path)
            tmp_path = None
            print(f"File {metadata.filename} OK (checksum match)")
        else:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            tmp_path = None
            print(f"File {metadata.filename} CORRUPTED (checksum mismatch)")
        print(f"Receiver Time: {receiver_duration:.2f} seconds")

        write_to_file_grpc(
            [
                {
                    "protocol": "grpc",
                    "side": "receiver",
                    "file_size": received_bytes / (1024 * 1024),
                    "sender_duration": "X",
                    "receiver_duration": f"{receiver_duration:.2f}",
                    "latency": "X",
                    "goodput_mbps": f"{(received_bytes * 8) / (receiver_duration * 1_000_000):.3f}",
                    "integrity_ok": integrity_ok,
                    "avg_cpu_usage": f"{resource_stats.get('avg_cpu_pct', 0):.2f}%",
                    "peak_ram_usage": f"{resource_stats.get('peak_rss_mb', 0):.2f} MB",
                    "energy_est": f"{resource_stats.get('energy_j', 0):.4f}",
                }
            ]
        )

        return pb.UploadResult(
            integrity_ok=integrity_ok,
            receiver_duration_s=receiver_duration,
        )


def serve():
    output_directory_exists()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        options=[
            ("grpc.max_receive_message_length", CHUNK_SIZE_LIMIT),
            ("grpc.max_send_message_length", CHUNK_SIZE_LIMIT),
        ],
    )
    pb_grpc.add_FileTransferServicer_to_server(FileTransferServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("gRPC Server starting on TCP 50051...")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
