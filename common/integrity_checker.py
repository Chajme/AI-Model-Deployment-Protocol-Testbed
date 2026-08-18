import hashlib

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def compute_sha256_file(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()