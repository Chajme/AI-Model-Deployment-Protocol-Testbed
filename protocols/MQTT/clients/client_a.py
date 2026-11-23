"""
    Basic functionality and measurements
    / used by docker-compose.yaml & docker-compose-automated.yaml
"""
import argparse

import paho.mqtt.client as mqtt
import time
import os
import json
import math
import socket
import ssl
import threading

from common.file_manager import get_file_path_input
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_mqtt

BROKER = "mosquitto-broker"
# TLS=1: MQTT over TLS on 8883, broker certificate verified against certs/ca.crt.
TLS = os.getenv("TLS", "0") == "1"
CA_FILE = os.path.join(os.getenv("CERTS_DIR", "/app/certs"), "ca.crt")
PORT = 8883 if TLS else 1883
TOPIC_CTRL = "file/control"
TOPIC_DATA = "file/data"

CHUNK_SIZE = 1024 * 1024

metadata_ack_event = threading.Event()
metadata_mid = None
metadata_sent_time = 0
ack_latency = 0


def on_publish(client, userdata, mid):
    global metadata_mid, ack_latency
    if mid == metadata_mid:
        ack_latency = time.perf_counter() - metadata_sent_time
        print(f"Metadata ACK received in {ack_latency:.4f}s")
        metadata_ack_event.set()

def make_client(window=0):
    c = mqtt.Client()
    c.on_publish = on_publish
    if window:
        # Allow up to `window` unacknowledged QoS>0 messages in flight.
        c.max_inflight_messages_set(window)
    if TLS:
        c.tls_set(ca_certs=CA_FILE)
    c.connect(BROKER, PORT, 300)
    return c


def measure_tls_handshake() -> float | None:
    """TLS handshake time to the broker, timed on a bare socket (None without TLS).

    Kept separate from the transfer so the TLS setup cost can be reported on
    its own, like tls_handshake_s for http-get.
    """
    if not TLS:
        return None
    sock = socket.create_connection((BROKER, PORT), timeout=30)
    try:
        context = ssl.create_default_context(cafile=CA_FILE)
        start = time.perf_counter()
        tls_sock = context.wrap_socket(sock, server_hostname=BROKER)
        handshake = time.perf_counter() - start
        tls_sock.close()
    finally:
        sock.close()
    print(f"TLS handshake: {handshake:.5f}s")
    return handshake

def calculate_total_chunks(filepath):
    file_size = os.path.getsize(filepath)
    total_chunks = math.ceil(file_size / CHUNK_SIZE)
    return file_size, total_chunks


def send_metadata(filename, total_chunks, checksum, qos_level, client):
    global metadata_mid, metadata_sent_time

    metadata = {
        "filename": filename,
        "total_chunks": total_chunks,
        "checksum": checksum,
        "qos": qos_level,
    }

    metadata_json = json.dumps(metadata)
    metadata_payload_len = len(metadata_json.encode("utf-8"))

    metadata_sent_time = time.perf_counter()
    msg_info = client.publish(TOPIC_CTRL, metadata_json, qos=qos_level)
    metadata_mid = msg_info.mid
    return msg_info, metadata_payload_len


PUBLISH_TIMEOUT_S = 60


class PublishFailed(Exception):
    pass


def send_chunks(filepath, total_chunks, qos_level, client, window=0):
    """Publish the file in CHUNK_SIZE messages.

    window == 0 (protocol key mqtt): wait for each chunk's acknowledgement
    before sending the next one -- an effective in-flight window of 1, which
    is what the legacy measurements used.
    window > 0 (protocol key mqtt-windowed): keep up to `window` chunks in
    flight (paho max_inflight_messages) and wait for all acknowledgements at
    the end. Comparing the two isolates how much of MQTT's throughput comes
    from this client's stop-and-wait rather than from the protocol.
    """
    chunk_lengths = []
    pending = []
    with open(filepath, "rb") as f:
        for chunk_num in range(total_chunks):
            chunk = f.read(CHUNK_SIZE)
            chunk_lengths.append(len(chunk))

            msg_info = client.publish(TOPIC_DATA, bytearray(chunk), qos=qos_level)
            if window:
                pending.append(msg_info)
            else:
                msg_info.wait_for_publish(timeout=PUBLISH_TIMEOUT_S)
                if not msg_info.is_published():
                    raise PublishFailed(f"chunk {chunk_num + 1} not acknowledged "
                                        f"within {PUBLISH_TIMEOUT_S}s")

            if chunk_num % 10 == 0 or chunk_num == total_chunks - 1:
                print(f"Sent chunk {chunk_num + 1}/{total_chunks}")

    # Windowed mode: a generous overall deadline for the whole tail of acks.
    deadline = time.time() + PUBLISH_TIMEOUT_S * max(1, len(pending))
    for i, msg_info in enumerate(pending, 1):
        msg_info.wait_for_publish(timeout=max(0.0, deadline - time.time()))
        if not msg_info.is_published():
            raise PublishFailed(f"chunk {i} not acknowledged before the deadline")

    return chunk_lengths


def send_file(filename, qos_level, window=0):
    global ack_latency
    filepath = os.path.join(get_file_path_input(filename))
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    try:
        tls_handshake = measure_tls_handshake()
    except Exception as e:
        print(f"TLS handshake probe failed: {e}")
        tls_handshake = None

    client = make_client(window)
    client.loop_start()

    file_size, total_chunks = calculate_total_chunks(filepath)
    print(f"\n--- Starting transfer: {filename} ({file_size / 1024 / 1024:.2f} MB) ---")

    checksum = compute_sha256_file(filepath)

    ack_latency = 0
    metadata_ack_event.clear()

    monitor = ResourceMonitor(sample_interval=0.01)
    monitor.start()

    msg_info, metadata_payload_len = send_metadata(filename, total_chunks, checksum, qos_level, client)

    # Wait for the broker's metadata ACK OUTSIDE the timed transfer window:
    # a lost ACK must not inject up to 10 s of dead waiting into
    # sender_duration (the metadata round trip is recorded separately in
    # `latency`). Timing starts only when chunk transmission begins.
    if not metadata_ack_event.wait(timeout=10):
        print("WARNING: Timed out waiting for metadata ACK, proceeding anyway.")

    start_time = time.time()
    try:
        chunk_lengths = send_chunks(filepath, total_chunks, qos_level, client, window)
    except PublishFailed as e:
        # Exit non-zero: the harness records the failed attempt in
        # transfer_failures.csv and the export counts it against the success rate.
        print(f"ERROR: {e}")
        client.loop_stop()
        client.disconnect()
        monitor.stop()
        raise SystemExit(1)
    end_time = time.time()
    client.loop_stop()
    client.disconnect()
    duration = end_time - start_time
    resource_stats = monitor.stop()

    goodput_mbps = (file_size * 8) / (duration * 1_000_000)

    measurements = [
        {
            "protocol": "mqtt",
            "qos": qos_level,
            "side": "sender",
            "tls": TLS,
            "tls_handshake_s": f"{tls_handshake:.5f}" if tls_handshake is not None else "X",
            "file_size": file_size / (1024 * 1024),
            "sender_duration": f"{duration:.3f}",
            "receiver_duration": "X",
            "latency": f"{ack_latency:.4f}",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
            "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
            "sample_count": resource_stats["sample_count"],
        }
    ]
    write_to_file_mqtt(measurements)



    print("Finished sending file.")
    print(f"Latency: {ack_latency:.4f}s | Sender Time: {duration:.2f}s")
    time.sleep(3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--file", required=True)
    parser.add_argument("--qos", required=True, type=int)
    parser.add_argument("--window", type=int, default=0,
                        help="Chunks in flight (0 = wait for each ack, the default).")

    args = parser.parse_args()

    time.sleep(5)  # Wait for broker

    send_file(args.file, args.qos, args.window)