"""
    AMQP sender: publishes a file in 1 MB chunks to RabbitMQ queues.
    / used by docker-compose.yaml & docker-compose.automated.yaml

    Mirrors the MQTT chunking contract:
      - JSON metadata message on the file/control queue
        (filename, total_chunks, checksum)
      - raw binary chunk messages on the file/data queue

    Publisher confirms (channel.confirm_delivery()) give at-least-once
    semantics analogous to MQTT QoS 1: every basic_publish blocks until
    the broker acks it.
"""
import argparse
import json
import math
import os
import time

import pika
from pika.adapters.blocking_connection import BlockingConnection
from pika.connection import ConnectionParameters

from common.file_manager import get_file_path_input
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_amqp

BROKER = "rabbitmq-broker"
PORT = 5672
QUEUE_CTRL = "file/control"
QUEUE_DATA = "file/data"

CHUNK_SIZE = 1024 * 1024


def connect_with_retries(attempts=15, delay=2) -> BlockingConnection:
    """Connect to RabbitMQ, retrying while the broker is still coming up."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return BlockingConnection(
                ConnectionParameters(BROKER, PORT, connection_attempts=1)
            )
        except Exception as e:  # AMQPConnectionError incl. DNS failures
            last_error = e
            print(f"[amqp_client] Broker connect attempt {attempt}/{attempts} failed: {e}")
            time.sleep(delay)
    raise last_error


def calculate_total_chunks(filepath):
    file_size = os.path.getsize(filepath)
    total_chunks = math.ceil(file_size / CHUNK_SIZE)
    return file_size, total_chunks


def _publish_confirmed(channel, routing_key, body, properties) -> bool:
    """Publish one message and block until the broker confirms it.

    With confirms enabled pika blocks inside basic_publish; on failure it
    raises instead of returning a falsy value (success returns None), so
    reaching here without an exception means the message was acked.
    """
    try:
        channel.basic_publish(
            exchange="", routing_key=routing_key, body=body, properties=properties
        )
        return True
    except pika.exceptions.UnroutableError:
        print(f"WARNING: message to {routing_key} was unroutable.")
        return False
    except pika.exceptions.NackError:
        print(f"WARNING: message to {routing_key} was nacked by the broker.")
        return False


def send_metadata(filename, total_chunks, checksum, channel):
    metadata = {
        "filename": filename,
        "total_chunks": total_chunks,
        "checksum": checksum,
    }

    payload = json.dumps(metadata).encode("utf-8")
    properties = pika.BasicProperties(content_type="application/json")

    # With confirms enabled basic_publish blocks until the broker acks,
    # so timing the call yields a real broker round-trip latency.
    sent_time = time.perf_counter()
    confirmed = _publish_confirmed(channel, QUEUE_CTRL, payload, properties)
    ack_latency = time.perf_counter() - sent_time
    if not confirmed:
        print("WARNING: metadata publish failed.")
    print(f"Metadata ACK received in {ack_latency:.4f}s")
    return ack_latency


def send_chunks(filepath, total_chunks, channel):
    properties = pika.BasicProperties(content_type="application/octet-stream")

    with open(filepath, "rb") as f:
        for chunk_num in range(total_chunks):
            chunk = f.read(CHUNK_SIZE)
            confirmed = _publish_confirmed(channel, QUEUE_DATA, chunk, properties)
            if not confirmed:
                print(f"WARNING: chunk {chunk_num + 1} failed confirmation.")

            if chunk_num % 10 == 0 or chunk_num == total_chunks - 1:
                print(f"Sent chunk {chunk_num + 1}/{total_chunks}")


def send_file(filename):
    filepath = os.path.join(get_file_path_input(filename))
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    connection = connect_with_retries()
    channel = connection.channel()

    # Declare the same queues as the receiver so either side can start first.
    channel.queue_declare(queue=QUEUE_CTRL)
    channel.queue_declare(queue=QUEUE_DATA)

    # At-least-once delivery analog to MQTT QoS 1.
    channel.confirm_delivery()

    file_size, total_chunks = calculate_total_chunks(filepath)
    print(f"\n--- Starting transfer: {filename} ({file_size / 1024 / 1024:.2f} MB) ---")

    checksum = compute_sha256_file(filepath)

    monitor = ResourceMonitor(sample_interval=0.01)
    monitor.start()

    start_time = time.time()
    ack_latency = send_metadata(filename, total_chunks, checksum, channel)
    send_chunks(filepath, total_chunks, channel)
    end_time = time.time()
    resource_stats = monitor.stop()

    connection.close()
    duration = end_time - start_time
    goodput_mbps = (file_size * 8) / (duration * 1_000_000)

    measurements = [
        {
            "protocol": "amqp",
            "side": "sender",
            "file_size": file_size / (1024 * 1024),
            "sender_duration": f"{duration:.2f}",
            "receiver_duration": "X",
            "latency": f"{ack_latency:.4f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
            "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
            "energy_est": f"{resource_stats['energy_j']:.4f}",
        }
    ]
    write_to_file_amqp(measurements)

    print("Finished sending file.")
    print(f"Latency: {ack_latency:.4f}s | Sender Time: {duration:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)

    args = parser.parse_args()

    time.sleep(5)  # Wait for broker

    send_file(args.file)
