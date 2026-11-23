"""HTTP transfer benchmark client.

Two modes:
  --mode put  (default, protocol key "http")      upload the payload with a
              streamed PUT; the server verifies the SHA-256.
  --mode get  (protocol key "http-get")           device-style download: stream
              the payload from GET /download/<file>, hash on the fly, compare
              with the source file; an interrupted download is resumed with a
              Range request (206).

TLS=1 switches to HTTPS on 8443, verified against certs/ca.crt, and records
the TLS handshake time separately from the TCP connect time.
"""
import argparse
import hashlib
import os
import socket
import ssl
import time
from urllib.parse import urlparse

import requests

from common.file_manager import load_binary_files, get_file_path_input
from common.integrity_checker import compute_sha256_file
from common.resource_monitor import ResourceMonitor
from output.write_csv import write_to_file_http, write_to_file_http_get

TLS = os.getenv("TLS", "0") == "1"
CERTS_DIR = os.getenv("CERTS_DIR", "/app/certs")
CA_FILE = os.path.join(CERTS_DIR, "ca.crt")
BASE_URL = "https://http-server:8443" if TLS else "http://http-server:8000"
VERIFY = CA_FILE if TLS else True

DOWNLOAD_CHUNK = 16 * 1024
# Resume behaviour: how often to retry an interrupted download (connection
# refused while the server restarts counts as a retry, not as a resume).
MAX_RETRY_ATTEMPTS = int(os.getenv("HTTP_MAX_RETRY_ATTEMPTS", "30"))
RETRY_BACKOFF_S = 1.0
CONNECT_TIMEOUT_S = 15
# NB-IoT RTTs are ~1.6 s; a stalled read longer than this is treated as broken.
READ_TIMEOUT_S = float(os.getenv("HTTP_READ_TIMEOUT_S", "120"))


def calculate_logging_size(filepath: str, filename: str):
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"Streaming {filename} ({file_size_mb:.2f} MB)...")
    return file_size_mb


def measure_network_latency() -> tuple[float, float | None]:
    """TCP connect time to the server, plus the TLS handshake time when TLS=1.

    A bare socket connect/disconnect -- no HTTP overhead, no server
    processing -- comparable to a TCP ping. With TLS the handshake on top of
    that connection is timed separately (None without TLS).
    """
    parsed = urlparse(BASE_URL)
    host = parsed.hostname
    port = parsed.port or (443 if TLS else 80)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    handshake = None
    try:
        start = time.perf_counter()
        sock.connect((host, port))
        latency = time.perf_counter() - start
        if TLS:
            context = ssl.create_default_context(cafile=CA_FILE)
            hs_start = time.perf_counter()
            tls_sock = context.wrap_socket(sock, server_hostname=host)
            handshake = time.perf_counter() - hs_start
            tls_sock.close()
    finally:
        sock.close()

    print(f"Network Latency (TCP connect): {latency:.5f}s")
    if handshake is not None:
        print(f"TLS handshake: {handshake:.5f}s")
    return latency, handshake


# ---------------------------------------------------------------- PUT upload

def transfer_file(filename: str) -> None:
    filepath = get_file_path_input(filename)
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    checksum = compute_sha256_file(filepath)
    upload_url = f"{BASE_URL}/upload/{filename}"
    file_size_mb = calculate_logging_size(filepath, filename)
    file_size_bytes = os.path.getsize(filepath)

    latency, _ = measure_network_latency()

    monitor = ResourceMonitor(sample_interval=0.01)
    monitor.start()

    try:
        ttfb = None

        def record_ttfb(response, **kwargs):
            """Response hook: fires when the response headers arrive."""
            nonlocal ttfb
            ttfb = time.perf_counter() - request_start

        with open(filepath, "rb") as file_stream:
            request_start = time.perf_counter()
            put_response = requests.put(
                upload_url,
                data=file_stream,
                headers={"X-Checksum": checksum},
                hooks={"response": record_ttfb},
                verify=VERIFY,
            )
        end_time = time.perf_counter()

        transfer_time = end_time - request_start

        # A 200 response means the server confirmed checksum equality server-side.
        integrity_ok = (put_response.status_code == 200)
        goodput_mbps = (file_size_bytes * 8) / (transfer_time * 1_000_000)

        if integrity_ok:
            print(f"  -> Success! Transfer took {transfer_time:.3f}s.")
        else:
            print(f"  -> Failed. Status: {put_response.status_code}")
        print(f"  -> Integrity OK: {integrity_ok}")

        resource_stats = monitor.stop()

        write_to_file_http([{
            "protocol": "http",
            "file_size": file_size_mb,
            "time_to_transfer": f"{transfer_time:.3f}",
            "latency_tcp_rtt": f"{latency:.5f}",
            "latency_ttfb": f"{ttfb:.5f}" if ttfb is not None else "X",
            "goodput_mbps": f"{goodput_mbps:.3f}",
            "integrity_ok": integrity_ok,
            "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
            "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
            "sample_count": resource_stats["sample_count"],
        }])

        time.sleep(3)

    except Exception as e:
        print(f"  -> Error transferring {filename}: {e}")
        _log_failure_put(filename, file_size_mb, latency)
    finally:
        monitor.stop()


def _log_failure_put(filename, file_size_mb, latency):
    """A failed upload still produces a row, so success rates are honest."""
    write_to_file_http([{
        "protocol": "http",
        "file_size": file_size_mb,
        "time_to_transfer": "X",
        "latency_tcp_rtt": f"{latency:.5f}",
        "latency_ttfb": "X",
        "goodput_mbps": "X",
        "integrity_ok": False,
        "avg_cpu_usage": "X",
        "peak_ram_usage": "X",
        "sample_count": 0,
    }])


# -------------------------------------------------------------- GET download

class DownloadFailed(Exception):
    pass


def download_file(filename: str) -> None:
    source = get_file_path_input(filename)
    if not os.path.exists(source):
        print(f"File {source} not found.")
        return

    expected = compute_sha256_file(source)
    size = os.path.getsize(source)
    file_size_mb = size / (1024 * 1024)
    url = f"{BASE_URL}/download/{filename}"
    dest = f"/tmp/download_{filename}"
    print(f"Downloading {filename} ({file_size_mb:.2f} MB) from {url} ...")

    try:
        latency, handshake = measure_network_latency()
    except Exception as e:
        print(f"  -> Latency probe failed: {e}")
        latency, handshake = None, None

    monitor = ResourceMonitor(sample_interval=0.01)
    monitor.start()

    digest = hashlib.sha256()
    received = 0
    resumed = 0
    bytes_resumed = 0
    attempts = 0
    ttfb = None
    error = None
    session = requests.Session()

    start = time.perf_counter()
    try:
        with open(dest, "wb") as out:
            while received < size:
                headers = {"Range": f"bytes={received}-"} if received else {}
                try:
                    with session.get(url, stream=True, headers=headers, verify=VERIFY,
                                     timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S)) as resp:
                        if received and resp.status_code != 206:
                            raise DownloadFailed(
                                f"resume at {received} B got HTTP {resp.status_code}, not 206")
                        if not received and resp.status_code != 200:
                            raise DownloadFailed(f"HTTP {resp.status_code}")
                        if ttfb is None:
                            ttfb = time.perf_counter() - start
                        is_resume = received > 0
                        if is_resume:
                            resumed += 1
                            print(f"  -> resumed at {received} B (206)")
                        for chunk in resp.iter_content(DOWNLOAD_CHUNK):
                            out.write(chunk)
                            digest.update(chunk)
                            received += len(chunk)
                            if is_resume:
                                bytes_resumed += len(chunk)
                    if received < size:
                        raise requests.exceptions.ChunkedEncodingError(
                            f"connection closed at {received}/{size} B")
                except requests.exceptions.SSLError as e:
                    # A certificate/handshake failure is a configuration
                    # error, not a dropped connection: don't retry it.
                    raise DownloadFailed(f"TLS error: {e}") from e
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.Timeout) as e:
                    attempts += 1
                    print(f"  -> interrupted at {received}/{size} B "
                          f"(attempt {attempts}/{MAX_RETRY_ATTEMPTS}): {type(e).__name__}")
                    if attempts >= MAX_RETRY_ATTEMPTS:
                        raise DownloadFailed(f"gave up after {attempts} attempts") from e
                    time.sleep(RETRY_BACKOFF_S)
    except DownloadFailed as e:
        error = str(e)
    finally:
        session.close()
    end = time.perf_counter()
    resource_stats = monitor.stop()

    transfer_time = end - start
    integrity_ok = error is None and received == size and digest.hexdigest() == expected
    goodput_mbps = (size * 8) / (transfer_time * 1_000_000) if integrity_ok else None

    if integrity_ok:
        print(f"  -> Success! Download took {transfer_time:.3f}s "
              f"(resumed {resumed}x, {bytes_resumed} B after resume).")
    else:
        print(f"  -> Failed: {error or 'checksum mismatch'} ({received}/{size} B)")
    print(f"  -> Integrity OK: {integrity_ok}")

    write_to_file_http_get([{
        "protocol": "http-get",
        "direction": "download",
        "tls": TLS,
        "file_size": file_size_mb,
        "time_to_transfer": f"{transfer_time:.3f}" if integrity_ok else "X",
        "latency_tcp_rtt": f"{latency:.5f}" if latency is not None else "X",
        "tls_handshake_s": f"{handshake:.5f}" if handshake is not None else "X",
        "latency_ttfb": f"{ttfb:.5f}" if ttfb is not None else "X",
        "goodput_mbps": f"{goodput_mbps:.3f}" if goodput_mbps is not None else "X",
        "resumed": resumed,
        "bytes_resumed": bytes_resumed,
        "integrity_ok": integrity_ok,
        "avg_cpu_usage": f"{resource_stats['avg_cpu_pct']:.2f}%",
        "peak_ram_usage": f"{resource_stats['peak_rss_mb']:.2f} MB",
        "sample_count": resource_stats["sample_count"],
    }])

    try:
        os.remove(dest)
    except OSError:
        pass
    time.sleep(3)


def transfer_binary_files(files: list[str] | None = None, mode: str = "put"):
    if files is None:
        files = load_binary_files()

    for filename in files or []:
        if mode == "get":
            download_file(filename)
        else:
            transfer_file(filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTP file transfer benchmark.")
    parser.add_argument(
        "--file",
        required=False,
        help="Transfer a single file (name in /app/data). Defaults to all .bin files.",
    )
    parser.add_argument(
        "--mode",
        choices=["put", "get"],
        default="put",
        help="put = upload (protocol key http), get = device download (http-get).",
    )
    args = parser.parse_args()

    # Wait briefly for the HTTP server to spin up in the Docker network
    time.sleep(5)

    transfer_binary_files([args.file] if args.file else None, mode=args.mode)

    # When driven per-file via `docker compose exec` the container stays alive
    # on its own, so we only need a short courtesy delay.
    keep_alive = 3 if args.file else 30
    print(f"\nAll transfers complete. Keeping container alive for {keep_alive}s...")
    time.sleep(keep_alive)
