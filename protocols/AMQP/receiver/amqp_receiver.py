"""
    AMQP receiver: consumes file/control + file/data queues from RabbitMQ,
    reassembles chunks and verifies the SHA-256 checksum.
    / used by docker-compose.yaml & docker-compose.automated.yaml

    Mirrors protocols/MQTT/clients/client_b.py.
"""
import json
import time

import pika
from pika.adapters.blocking_connection import BlockingConnection
from pika.connection import ConnectionParameters

from common.file_manager import get_file_path_output, output_directory_exists
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_amqp

BROKER = "rabbitmq-broker"
PORT = 5672
QUEUE_CTRL = "file/control"
QUEUE_DATA = "file/data"

# Incoming-transfer state (single in-flight transfer at a time)
current_file_handle = None
expected_chunks = 0
received_chunks = 0
current_filename = ""
received_bytes = 0
first_chunk_received = False

# Measurements
start_latency = 0
metadata_arrival_time = 0
transfer_start_time = 0
expected_checksum = None

monitor = None


def connect_with_retries(attempts=15, delay=2) -> BlockingConnection:
    """Connect to RabbitMQ, retrying while the broker is still coming up."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return BlockingConnection(
                ConnectionParameters(BROKER, PORT, connection_attempts=1)
            )
        except Exception as e:
            last_error = e
            print(f"[amqp_receiver] Broker connect attempt {attempt}/{attempts} failed: {e}")
            time.sleep(delay)
    raise last_error


def _transfer_completed_handler():
    global current_filename, received_bytes, expected_checksum, start_latency, transfer_start_time, monitor

    transfer_duration = time.perf_counter() - transfer_start_time
    file_size_mb = received_bytes / (1024 * 1024)

    resource_stats = monitor.stop() if monitor else {}
    monitor = None

    actual_checksum = compute_sha256_file(get_file_path_output(current_filename))
    integrity_ok = (expected_checksum == actual_checksum)

    goodput_mbps = (received_bytes * 8) / (transfer_duration * 1_000_000)

    if integrity_ok:
        print(f"File {current_filename} OK (checksum match)")
    else:
        print(f"File {current_filename} CORRUPTED (checksum mismatch)")
    print(f"Latency (First Chunk Lag): {start_latency:.4f}s")
    speed = (file_size_mb / transfer_duration) if transfer_duration > 0 else 0
    print(f"Receiver Time: {transfer_duration:.2f} seconds ({speed:.2f} MB/s)")

    measurements = [
        {
            "protocol": "amqp",
            "side": "receiver",
            "file_size": file_size_mb,
            "sender_duration": "X",
            "receiver_duration": f"{transfer_duration:.2f}",
            "latency": f"{start_latency:.4f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "integrity_ok": integrity_ok,
            "avg_cpu_usage": f"{resource_stats.get('avg_cpu_pct', 0):.2f}%",
            "peak_ram_usage": f"{resource_stats.get('peak_rss_mb', 0):.2f} MB",
            "energy_est": f"{resource_stats.get('energy_j', 0):.4f}",
        }
    ]
    write_to_file_amqp(measurements)


def on_control(channel, method, properties, body):
    global current_file_handle, expected_chunks, received_chunks, \
        current_filename, start_latency, received_bytes, metadata_arrival_time, \
        first_chunk_received, transfer_start_time, expected_checksum, monitor

    metadata_arrival_time = time.perf_counter()
    first_chunk_received = False

    metadata = json.loads(body.decode())
    current_filename = metadata["filename"]
    expected_chunks = metadata["total_chunks"]
    received_chunks = 0
    received_bytes = 0

    start_latency = 0
    transfer_start_time = 0
    expected_checksum = metadata.get("checksum")

    print(f"\nIncoming file: {current_filename} ({expected_chunks} chunks).")

    # Warn on overlapping transfers and close the stale handle so we neither
    # leak descriptors nor silently corrupt the previous file.
    if current_file_handle and not current_file_handle.closed:
        print(
            f"WARNING: Previous transfer of '{current_filename}' was incomplete "
            f"({received_chunks}/{expected_chunks} chunks received). Closing stale handle."
        )
        current_file_handle.close()

    current_file_handle = open(get_file_path_output(current_filename), "wb")
    monitor = ResourceMonitor(sample_interval=0.01)
    monitor.start()
    channel.basic_ack(delivery_tag=method.delivery_tag)


def on_data(channel, method, properties, body):
    global current_file_handle, expected_checksum
    global received_chunks, received_bytes, start_latency, first_chunk_received, transfer_start_time

    if current_file_handle is None or current_file_handle.closed:
        # Chunks without metadata are dropped; the broker acks them so they
        # do not redeliver forever.
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    if not first_chunk_received:
        start_latency = time.perf_counter() - metadata_arrival_time
        transfer_start_time = time.perf_counter()
        first_chunk_received = True
        print(f"First chunk arrived. Latency: {start_latency:.4f}s")

    current_file_handle.write(body)
    received_chunks += 1
    received_bytes += len(body)

    if received_chunks % 10 == 0 or received_chunks == expected_chunks:
        print(f"Received chunk {received_chunks}/{expected_chunks}")

    if received_chunks == expected_chunks:
        _transfer_completed_handler()
        current_file_handle.close()
        current_file_handle = None

    channel.basic_ack(delivery_tag=method.delivery_tag)


def main():
    output_directory_exists()

    connection = connect_with_retries()
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_CTRL)
    channel.queue_declare(queue=QUEUE_DATA)
    channel.basic_qos(prefetch_count=32)  # keep memory bounded on large files

    channel.basic_consume(queue=QUEUE_CTRL, on_message_callback=on_control)
    channel.basic_consume(queue=QUEUE_DATA, on_message_callback=on_data)

    print("Connected to RabbitMQ. Listening for files...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
