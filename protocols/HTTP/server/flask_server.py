from flask import Flask, request, Response

from common.file_manager import save_file
from common.integrity_checker import sha256

app = Flask(__name__)

@app.route("/upload/<filename>", methods=["PUT"])
def upload(filename):
    data = request.data

    expected_checksum = request.headers.get("X-Checksum")
    actual_checksum = sha256(data)

    # Integrity check happens HERE (server-side)
    if expected_checksum and expected_checksum != actual_checksum:
        print(f"[HTTP] CHECKSUM FAIL: {filename}")
        return Response("Checksum mismatch", status=400)

    save_file(filename, data=data)

    print(f"[HTTP] OK: {filename} ({len(data)} bytes)")
    return Response("OK", status=200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)