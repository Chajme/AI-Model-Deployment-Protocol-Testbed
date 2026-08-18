import asyncio
import time
import os
from urllib.parse import urlparse

from aiocoap import Message, Context, PUT, GET

from common.file_manager import load_binary_files
from common.integrity_checker import sha256
from output.write_csv import write_to_file_coap

DATA_DIR   = "/app/data"
SERVER_URI = "coap://coap-server/upload"
MAX_RETRIES = 3


async def get_latency(context: Context, uri: str) -> float:
    """
    Measure CoAP round-trip latency using GET /.well-known/core — a standard
    discovery endpoint every CoAP server is expected to serve. This avoids
    sending a GET to a PUT-only resource (which would return 4.05 Method Not
    Allowed and measure an error round-trip instead of real latency).
    """
    parsed = urlparse(uri)
    ping_uri = f"coap://{parsed.hostname}/.well-known/core"
    try:
        req = Message(code=GET, uri=ping_uri)
        t0 = time.perf_counter()
        await context.request(req).response
        return time.perf_counter() - t0
    except Exception:
        return 0.0


async def transfer_file(context: Context, filename: str) -> None:
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f"File {filename} not found.")
        return

    # NOTE: aiocoap requires the full payload in memory to perform blockwise
    # transfers automatically. Unlike the HTTP client there is no streaming
    # path here — for very large files this will be the primary RAM cost.
    with open(filepath, "rb") as f:
        payload = f.read()

    file_size_bytes = len(payload)
    file_size_mb    = file_size_bytes / (1024 * 1024)
    print(f"\n--- CoAP Transfer: {filename} ({file_size_mb:.2f} MB) ---")

    checksum = sha256(payload)
    latency  = await get_latency(context, SERVER_URI)

    retries       = 0
    response      = None
    goodput_mbps  = 0.0
    transfer_time = 0.0

    for attempt in range(MAX_RETRIES):
        try:
            request = Message(
                code=PUT,
                payload=payload,
                uri=f"{SERVER_URI}?file={filename}&checksum={checksum}",
            )
            t0       = time.perf_counter()
            response = await context.request(request).response
            transfer_time = max(time.perf_counter() - t0, 0.001)
            goodput_mbps  = (file_size_bytes * 8) / (transfer_time * 1_000_000)
            break
        except Exception as e:
            retries += 1
            print(f"  Attempt {attempt + 1} failed: {e}. Retrying...")
            await asyncio.sleep(2 ** attempt)  # exponential back-off

    if response is None:
        print(f"  Transfer failed after {MAX_RETRIES} attempts.")
        return

    # integrity_ok relies on the server verifying the checksum query parameter
    # and returning 4.00 Bad Request on mismatch; 2.04 Changed means the server
    # confirmed the file was saved with a matching checksum.
    integrity_ok = response.code.is_successful()

    print(f"Result: {response.code} | Time: {transfer_time:.2f}s | Retries: {retries}")
    print(f"Latency: {latency:.4f}s")

    write_to_file_coap([{
        "protocol":        "coap",
        "file_size":       file_size_mb,
        "time_to_transfer": f"{transfer_time:.2f}",
        "latency":         f"{latency:.4f}",
        "goodput_mbps":    f"{goodput_mbps:.3f}",
        "integrity_ok":    integrity_ok,
    }])

    await asyncio.sleep(3)


async def transfer_all_files(files: list[str] | None = None) -> None:
    if files is None:
        files = load_binary_files()
    if not files:
        print("No .bin files found.")
        return
    context = await Context.create_client_context()
    for filename in files:
        await transfer_file(context, filename)


async def main(single_file: str | None = None) -> None:
    await asyncio.sleep(5)  # Wait for the server container to spin up

    files = [single_file] if single_file else None
    await transfer_all_files(files)

    # When driven per-file via `docker compose exec` the container stays alive
    # on its own, so we only need a short courtesy delay.
    keep_alive = 3 if single_file else 30
    print(f"\nTransfer complete. Keeping alive for {keep_alive} seconds.")
    await asyncio.sleep(keep_alive)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CoAP blockwise PUT benchmark.")
    parser.add_argument(
        "--file",
        required=False,
        help="Transfer a single file (name in /app/data). Defaults to all .bin files.",
    )
    args = parser.parse_args()

    asyncio.run(main(args.file))