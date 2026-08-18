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
import threading

from common.file_manager import get_file_path_input
from common.integrity_checker import compute_sha256_file
from output.write_csv import write_to_file_mqtt

BROKER = "mosquitto-broker"
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

def make_client():
    c = mqtt.Client()
    c.on_publish = on_publish
    c.connect(BROKER, 1883, 300)
    return c

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


def send_chunks(filepath, total_chunks, qos_level, client):
    chunk_lengths = []
    with open(filepath, "rb") as f:
        for chunk_num in range(total_chunks):
            chunk = f.read(CHUNK_SIZE)
            chunk_lengths.append(len(chunk))

            msg_info = client.publish(TOPIC_DATA, bytearray(chunk), qos=qos_level)
            msg_info.wait_for_publish(timeout=60)

            if chunk_num % 10 == 0 or chunk_num == total_chunks - 1:
                print(f"Sent chunk {chunk_num + 1}/{total_chunks}")

    return chunk_lengths


def send_file(filename, qos_level):
    global ack_latency
    filepath = os.path.join(get_file_path_input(filename))
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    client = make_client()
    client.loop_start()

    file_size, total_chunks = calculate_total_chunks(filepath)
    print(f"\n--- Starting transfer: {filename} ({file_size / 1024 / 1024:.2f} MB) ---")

    checksum = compute_sha256_file(filepath)

    ack_latency = 0
    metadata_ack_event.clear()


    start_time = time.time()
    msg_info, metadata_payload_len = send_metadata(filename, total_chunks, checksum, qos_level, client)

    if not metadata_ack_event.wait(timeout=10):
        print("WARNING: Timed out waiting for metadata ACK, proceeding anyway.")


    chunk_lengths = send_chunks(filepath, total_chunks, qos_level, client)


    end_time = time.time()
    client.loop_stop()
    client.disconnect()
    duration = end_time - start_time

    goodput_mbps = (file_size * 8) / (duration * 1_000_000)

    measurements = [
        {
            "protocol": "mqtt",
            "qos": qos_level,
            "side": "sender",
            "file_size": file_size / (1024 * 1024),
            "sender_duration": f"{duration:.2f}",
            "receiver_duration": "X",
            "latency": f"{ack_latency:.4f}",
            "goodput_mbps": f"{goodput_mbps:.3f}"
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

    args = parser.parse_args()

    time.sleep(5)  # Wait for broker

    send_file(args.file, args.qos)