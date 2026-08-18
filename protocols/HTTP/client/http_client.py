import argparse
import requests
import time
import os
import socket
from urllib.parse import urlparse

from common.file_manager import load_binary_files, get_file_path_input
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_http

BASE_URL = "http://http-server:8000"


def calculate_logging_size(filepath: str, filename: str):
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"Streaming {filename} ({file_size_mb:.2f} MB)...")
    return file_size_mb


def measure_network_latency() -> float:
    """
    Measure raw TCP connection latency to the server by timing a bare
    socket connect/disconnect — no HTTP overhead, no server processing time.
    This is a clean RTT measurement comparable to a TCP ping.
    """
    parsed = urlparse(BASE_URL)
    host = parsed.hostname
    port = parsed.port or 80

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        start = time.perf_counter()
        sock.connect((host, port))
        latency = time.perf_counter() - start
    finally:
        sock.close()

    print(f"Network Latency (TCP RTT): {latency:.5f}s")
    return latency


def transfer_file(filename: str) -> None:
    filepath = get_file_path_input(filename)
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    checksum = compute_sha256_file(filepath)
    upload_url = f"{BASE_URL}/upload/{filename}"
    file_size_mb = calculate_logging_size(filepath, filename)
    file_size_bytes = os.path.getsize(filepath)

    latency = measure_network_latency()

    monitor = ResourceMonitor(sample_interval=0.01)  # 50 ms granularity
    monitor.start()

    try:
        ttfb = None

        def record_ttfb(response, **kwargs):
            """
            requests response hook: fires as soon as the response headers
            arrive, before the body is read. Used to capture TTFB.
            """
            nonlocal ttfb
            ttfb = time.perf_counter() - request_start


        with open(filepath, "rb") as file_stream:
            request_start = time.perf_counter()
            put_response = requests.put(
                upload_url,
                data=file_stream,
                headers={"X-Checksum": checksum},
                hooks={"response": record_ttfb},
            )
        end_time = time.perf_counter()

        transfer_time = end_time - request_start

        # A 200 response means the server confirmed checksum equality server-side.
        integrity_ok = (put_response.status_code == 200)
        goodput_mbps = (file_size_bytes * 8) / (transfer_time * 1_000_000)

        if integrity_ok:
            print(f"  -> Success! Transfer took {transfer_time:.2f}s.")
            print(f"  -> TTFB: {ttfb:.5f}s")
            print(f"  -> TCP RTT Latency: {latency:.5f}s")
            print(f"  -> Integrity OK: {integrity_ok}")
        else:
            print(f"  -> Failed. Status: {put_response.status_code}")
            print(f"  -> Integrity OK: {integrity_ok}")

        resource_stats = monitor.stop()

        print(f"  -> Avg CPU:    {resource_stats['avg_cpu_pct']:.2f}%")
        print(f"  -> Peak RAM:   {resource_stats['peak_rss_mb']:.2f} MB")
        print(f"  -> Energy est: {resource_stats['energy_j']:.4f} J")

        measurements = [
            {
                "protocol": "http",
                "file_size": file_size_mb,
                "time_to_transfer": f"{transfer_time:.3f}",
                "latency_tcp_rtt": f"{latency:.5f}",
                "latency_ttfb": f"{ttfb:.5f}" if ttfb is not None else "X",
                "goodput_mbps": f"{goodput_mbps:.3f}",
                "integrity_ok": integrity_ok,
                "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
                "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
                "energy_est": f"{resource_stats['energy_j']:.4f}"
            }
        ]
        write_to_file_http(measurements)

        time.sleep(3)

    except Exception as e:
        print(f"  -> Error transferring {filename}: {e}")
    finally:
        monitor.stop()


def transfer_binary_files(files: list[str] | None = None):
    if files is None:
        files = load_binary_files()

    if not files:
        return

    for filename in files:
        transfer_file(filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTP file transfer benchmark.")
    parser.add_argument(
        "--file",
        required=False,
        help="Transfer a single file (name in /app/data). Defaults to all .bin files.",
    )
    args = parser.parse_args()

    # Wait briefly for the HTTP server to spin up in the Docker network
    time.sleep(5)

    transfer_binary_files([args.file] if args.file else None)

    # When driven per-file via `docker compose exec` the container stays alive
    # on its own, so we only need a short courtesy delay.
    keep_alive = 3 if args.file else 30
    print(f"\nAll transfers complete. Keeping container alive for {keep_alive}s...")
    time.sleep(keep_alive)