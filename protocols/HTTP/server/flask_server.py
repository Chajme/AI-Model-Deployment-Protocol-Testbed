"""HTTP server for the transfer benchmark.

Routes:
  PUT /upload/<filename>    streamed upload, SHA-256 checked against X-Checksum
  GET /download/<filename>  device-style download of a payload from /app/data;
                            Werkzeug answers Range requests with 206, so a
                            client can resume an interrupted download.

Served by gunicorn (not the Flask development server) for both the plain and
the TLS variant, so the two differ only in TLS. Run as a module:
  python -m protocols.HTTP.server.flask_server
TLS=1 serves HTTPS on 8443 with certs/server.{crt,key}; otherwise HTTP on 8000.
"""
import hashlib
import os

from flask import Flask, Response, abort, request, send_from_directory

from common.file_manager import get_file_path_output, output_directory_exists

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
CHUNK = 64 * 1024

app = Flask(__name__)


@app.route("/upload/<filename>", methods=["PUT"])
def upload(filename):
    """Stream the request body to disk, hashing as it arrives (no full buffering)."""
    output_directory_exists()
    digest = hashlib.sha256()
    received = 0
    target = get_file_path_output(os.path.basename(filename))
    with open(target, "wb") as out:
        while True:
            chunk = request.stream.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            out.write(chunk)
            received += len(chunk)

    expected_checksum = request.headers.get("X-Checksum")
    # Integrity check happens HERE (server-side)
    if expected_checksum and expected_checksum != digest.hexdigest():
        print(f"[HTTP] CHECKSUM FAIL: {filename}")
        return Response("Checksum mismatch", status=400)

    print(f"[HTTP] OK: {filename} ({received} bytes)")
    return Response("OK", status=200)


@app.route("/download/<filename>", methods=["GET"])
def download(filename):
    """Serve a payload; conditional=True enables Range/206 for resume."""
    if not filename.endswith(".bin"):
        abort(404)
    return send_from_directory(DATA_DIR, filename, conditional=True,
                               mimetype="application/octet-stream")


def gunicorn_argv() -> list[str]:
    """gunicorn command line for the plain or the TLS variant."""
    tls = os.getenv("TLS", "0") == "1"
    argv = [
        "gunicorn",
        "--worker-class", "gthread", "--workers", "2", "--threads", "4",
        # gthread workers heartbeat independently of request length, but keep
        # a generous timeout anyway: one NB-IoT transfer can take minutes.
        "--timeout", "3600",
        "--access-logfile", "-",
        "--bind", "0.0.0.0:8443" if tls else "0.0.0.0:8000",
    ]
    if tls:
        certs = os.getenv("CERTS_DIR", "/app/certs")
        argv += ["--certfile", os.path.join(certs, "server.crt"),
                 "--keyfile", os.path.join(certs, "server.key")]
    return argv + ["protocols.HTTP.server.flask_server:app"]


if __name__ == "__main__":
    argv = gunicorn_argv()
    print("[HTTP] exec " + " ".join(argv), flush=True)
    os.execvp(argv[0], argv)
