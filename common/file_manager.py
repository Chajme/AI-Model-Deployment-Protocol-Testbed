import os

try:
    import common.runs as runs
except ImportError:  # pragma: no cover - project root not on sys.path yet
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import common.runs as runs

DATA_DIR = os.getenv("DATA_DIR", "./data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")

def load_binary_files():
    if not os.path.exists(DATA_DIR):
        raise  Exception("Error: Directory '{DATA_DIR}' does not exist.")

    files = [
        f for f in os.listdir(DATA_DIR)
        if os.path.isfile(os.path.join(DATA_DIR, f)) and f.endswith(".bin")
    ]

    if not files:
        raise  Exception("No bin files found in '{DATA_DIR}'.")

    files.sort(key=lambda f: os.path.getsize(os.path.join(DATA_DIR, f)))

    print(f"Found {len(files)} file(s).\n")
    return files

def save_file(filename, data):
    output_directory_exists()

    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(data)

    print(f"Saved '{filename}' successfully.")

def get_file_path_output(filename):
    return os.path.join(OUTPUT_DIR, filename)

def get_file_path_input(filename):
    return os.path.join(DATA_DIR, filename)

def output_directory_exists():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Ensure the active run directory exists so in-container writes (clients,
    # servers) land inside the run even if the host creates it a moment later.
    run_id = runs.active_run_id()
    if run_id:
        os.makedirs(runs.run_dir(OUTPUT_DIR, run_id), exist_ok=True)
        os.makedirs(os.path.join(runs.run_dir(OUTPUT_DIR, run_id), "pcap"), exist_ok=True)