import paho.mqtt.client as mqtt
import json
import time

from common.file_manager import get_file_path_input, output_directory_exists, get_file_path_output
from common.integrity_checker import compute_sha256_file
from output.write_csv import write_to_file_mqtt

BROKER = "mosquitto-broker"
TOPIC_CTRL = "file/control"
TOPIC_DATA = "file/data"

PORT = 1883
KEEPALIVE = 300

# Global state to keep track of the incoming file
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

_current_qos = "unknown"


def _connect_with_retries(client, host, port, attempts=15, delay=2):
    """Connect to the broker, retrying while it/DNS is still coming up at container start."""
    for attempt in range(1, attempts + 1):
        try:
            client.connect(host, port, KEEPALIVE)
            return
        except Exception as e:
            print(f"[client_b] Broker connect attempt {attempt}/{attempts} failed: {e}")
            if attempt == attempts:
                raise
            time.sleep(delay)


def _transfer_completed_handler():
    global start_latency, transfer_start_time, expected_checksum, _current_qos

    transfer_duration = time.perf_counter() - transfer_start_time
    file_size_mb = received_bytes / (1024 * 1024)

    actual_checksum = compute_sha256_file(get_file_path_output(current_filename))
    integrity_ok = (expected_checksum == actual_checksum)

    file_size_bytes = received_bytes
    goodput_mbps = (file_size_bytes * 8) / (transfer_duration * 1_000_000)

    if integrity_ok:
        print(f"File {current_filename} OK (checksum match)")
    else:
        print(f"File {current_filename} CORRUPTED (checksum mismatch)")
    print(f"Latency (First Chunk Lag): {start_latency:.4f}s")
    speed = (file_size_mb / transfer_duration) if transfer_duration > 0 else 0
    print(f"Receiver Time: {transfer_duration:.2f} seconds ({speed:.2f} MB/s)")

    measurements = [
        {
            "protocol": "mqtt",
            "qos": _current_qos,
            "side": "receiver",
            "file_size": file_size_mb,
            "sender_duration": "X",
            "receiver_duration": f"{transfer_duration:.2f}",
            "latency": f"{start_latency:.4f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "integrity_ok": integrity_ok,
        }
    ]
    write_to_file_mqtt(measurements)


def on_connect(client, userdata, flags, rc):
    print("Connected to broker. Listening for files...")
    # Set QoS to max, the resulting QoS should be the one from sender
    client.subscribe(TOPIC_CTRL, qos=2)
    client.subscribe(TOPIC_DATA, qos=2)


def on_message(client, userdata, msg):
    global current_file_handle, expected_chunks, received_chunks, \
        current_filename, start_latency, received_bytes, metadata_arrival_time, \
        first_chunk_received, transfer_start_time, expected_checksum, _current_qos

    # Handle Metadata Message
    if msg.topic == TOPIC_CTRL:
        metadata_arrival_time = time.perf_counter()
        first_chunk_received = False

        metadata = json.loads(msg.payload.decode())
        current_filename = metadata["filename"]
        expected_chunks = metadata["total_chunks"]
        received_chunks = 0
        received_bytes = 0

        start_latency = 0
        transfer_start_time = 0

        expected_checksum = metadata.get("checksum")

        # Read the QoS level from the control message.
        _current_qos = metadata.get("qos", "unknown")

        print(f"\nIncoming file: {current_filename} ({expected_chunks} chunks).")

        # Warn explicitly when a new transfer arrives before the
        # previous one completed, then close the stale handle so we don't
        # leak file descriptors or silently produce a corrupt file.
        if current_file_handle and not current_file_handle.closed:
            print(
                f"WARNING: Previous transfer of '{current_filename}' was incomplete "
                f"({received_chunks}/{expected_chunks} chunks received). Closing stale handle."
            )
            current_file_handle.close()

        current_file_handle = open(get_file_path_output(current_filename), "wb")

    # Handle Raw Binary Chunk Message
    elif msg.topic == TOPIC_DATA and current_file_handle is not None:
        if not first_chunk_received:
            start_latency = time.perf_counter() - metadata_arrival_time
            transfer_start_time = time.perf_counter()
            first_chunk_received = True
            print(f"First chunk arrived. Latency: {start_latency:.4f}s")

        current_file_handle.write(msg.payload)
        received_chunks += 1
        received_bytes += len(msg.payload)

        if received_chunks % 10 == 0 or received_chunks == expected_chunks:
            print(f"Received chunk {received_chunks}/{expected_chunks}")

        if received_chunks == expected_chunks:
            _transfer_completed_handler()

            received_bytes = 0
            current_file_handle.close()
            current_file_handle = None


if __name__ == '__main__':
    output_directory_exists()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    _connect_with_retries(client, BROKER, PORT)
    client.loop_forever()