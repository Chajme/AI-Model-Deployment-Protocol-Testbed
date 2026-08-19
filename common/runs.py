"""
    Run registry: structured, run-scoped storage for benchmark outputs.

    A "run" is one self-contained experiment snapshot:
      <OUTPUT_DIR>/runs/<run_id>/
        run.json                     # manifest (protocol, profile, versions, env...)
        {protocol}_measurements.csv  # http / coap / mqtt (side column) / pcap
        pcap/                        # one pcap per transfer

    The active run is shared between the host harness and the containers via
    two mechanisms:
      - RUN_ID  env var (set by the automated runner / manual CLI)
      - a sidecar marker file <OUTPUT_DIR>/.active_run written by the host and
        read by containers through the output bind mount.

    Row-level run_id / timestamp / network_profile columns make any CSV
    self-describing if it is ever concatenated with others.
"""

import json
import os
import subprocess
from datetime import datetime, timezone

RUNS_DIRNAME = "runs"
MARKER_FILENAME = ".active_run"
MANIFEST_FILENAME = "run.json"

# Keys surfaced from the environment into the manifest (avoids leaking secrets
# or unrelated vars).
MANIFEST_ENV_KEYS = [
    "NETWORK_PROFILE",
    "MEASUREMENT_SUFFIX",
    "DATA_DIR",
    "OUTPUT_DIR",
]


def default_output_dir():
    """Directory that (on the host) contains the runs/ tree."""
    return os.getenv("OUTPUT_DIR", "./output")


def now_utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def run_id_for(protocol: str, profile: str | None = None) -> str:
    """Timestamp-based run id, e.g. '20260818T201455_mqtt_harsh'."""
    parts = [now_utc_stamp(), protocol]
    if profile:
        parts.append(profile)
    return "_".join(parts)


# ---------------------------------------------------------------------------
# Active-run resolution (env var + sidecar marker)
# ---------------------------------------------------------------------------

def active_run_id() -> str | None:
    """Highest-precedence active run: RUN_ID env, then the .active_run marker."""
    rid = os.getenv("RUN_ID", "").strip()
    if rid:
        return rid
    return read_marker(default_output_dir())


def read_marker(output_dir: str) -> str | None:
    path = os.path.join(output_dir, MARKER_FILENAME)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def write_marker(output_dir: str, run_id: str) -> None:
    path = os.path.join(output_dir, MARKER_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(run_id)


def clear_marker(output_dir: str) -> None:
    path = os.path.join(output_dir, MARKER_FILENAME)
    if os.path.isfile(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# Run layout helpers
# ---------------------------------------------------------------------------

def runs_dir(output_dir: str) -> str:
    return os.path.join(output_dir, RUNS_DIRNAME)


def run_dir(output_dir: str, run_id: str) -> str:
    return os.path.join(runs_dir(output_dir), run_id)


def manifest_path(output_dir: str, run_id: str) -> str:
    return os.path.join(run_dir(output_dir, run_id), MANIFEST_FILENAME)


def pcap_dir(output_dir: str | None = None) -> str:
    """Run-aware pcap directory: <OUTPUT_DIR>/runs/<run_id>/pcap when a run
    is active, else the legacy flat <OUTPUT_DIR>/pcap."""
    output = output_dir or default_output_dir()
    rid = active_run_id()
    if rid:
        return os.path.join(run_dir(output, rid), "pcap")
    return os.path.join(output, "pcap")


# ---------------------------------------------------------------------------
# Creating / reading runs
# ---------------------------------------------------------------------------

def _tool_version(argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        lines = (out.stdout or "").splitlines()
        return lines[0].strip() if lines else None
    except Exception:
        return None


def _versions():
    return {
        "docker": _tool_version(["docker", "--version"]),
        "tshark": _tool_version(["tshark", "--version"]),
    }


def new_run(
    output_dir: str,
    protocol: str,
    profile: str | None = None,
    run_id: str | None = None,
    meta: dict | None = None,
) -> str:
    """Create a fresh, immutable run directory and write its manifest.

    Raises FileExistsError if run_id already exists (runs are never merged).
    """
    rid = run_id or run_id_for(protocol, profile)
    target = run_dir(output_dir, rid)
    if os.path.exists(target):
        raise FileExistsError(
            f"Run directory already exists: {target}. "
            "Runs are immutable; pass a different --run-id or delete the old run."
        )
    os.makedirs(os.path.join(target, "pcap"), exist_ok=True)

    manifest = {
        "run_id": rid,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": protocol,
        "network_profile": profile or os.getenv("NETWORK_PROFILE", ""),
        "env": {key: os.getenv(key, "") for key in MANIFEST_ENV_KEYS},
        **_versions(),
        **(meta or {}),
    }
    write_manifest(target, manifest)
    return rid


def write_manifest(run_dir_path: str, manifest: dict) -> None:
    with open(os.path.join(run_dir_path, MANIFEST_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def update_manifest(output_dir: str, run_id: str, patch: dict) -> None:
    path = manifest_path(output_dir, run_id)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest.update(patch)
    write_manifest(run_dir(output_dir, run_id), manifest)


def read_manifest(output_dir: str, run_id: str) -> dict | None:
    path = manifest_path(output_dir, run_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_runs(output_dir: str) -> list[str]:
    """Run ids (newest first) that have a manifest."""
    base = runs_dir(output_dir)
    if not os.path.isdir(base):
        return []
    ids = [
        name for name in os.listdir(base)
        if os.path.isfile(os.path.join(base, name, MANIFEST_FILENAME))
    ]
    return sorted(ids, reverse=True)


def find_runs(
    output_dir: str,
    protocol: str | None = None,
    profile: str | None = None,
) -> list[str]:
    """Run ids matching optional protocol / network_profile filters."""
    matched = []
    for rid in list_runs(output_dir):
        manifest = read_manifest(output_dir, rid) or {}
        if protocol and manifest.get("protocol") != protocol:
            continue
        if profile and manifest.get("network_profile") != profile:
            continue
        matched.append(rid)
    return matched


def load_csv(output_dir: str, run_id: str, kind: str) -> list[dict] | None:
    """Rows from <run_dir>/{kind}_measurements.csv, or None if absent."""
    import csv

    path = os.path.join(run_dir(output_dir, run_id), f"{kind}_measurements.csv")
    if not os.path.isfile(path):
        return None
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
