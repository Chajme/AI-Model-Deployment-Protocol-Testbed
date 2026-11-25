"""
    Script to automate measurements
    / allows to run multiple profiles and multiple protocols one after the other

    For each protocol/profile it:
      1. builds the images
      2. starts only that protocol's stack (docker-compose.automated.yaml,
         tc network profile applied inside the containers)
      3. waits until the stack is up
      4. drives every transfer through protocols.benchmark_manager
         (one pcap per transfer, analyzed and logged to a CSV)
      5. tears the stack down
"""

import argparse
import itertools
import json
import os
import random
import subprocess
import sys
import time

# Make the project root importable (runner.py sits at the project root).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from protocols.benchmark_manager import run_protocol, RUNNERS
import common.runs as runs

COMPOSE_FILE_AUTOMATED = "docker-compose.automated.yaml"

BASE_ENV = os.environ.copy()

# Reachability probes: (client service to exec into, host, tcp port).
# UDP protocols (CoAP/LwM2M) are handled with a fixed startup delay instead.
PROBE = {
    "mqtt": ("mqtt-client-a", "mosquitto-broker", 1883),
    "mqtt-windowed": ("mqtt-client-a", "mosquitto-broker", 1883),
    "http": ("http-client", "http-server", 8000),
    "http-get": ("http-client", "http-server", 8000),
    "amqp": ("amqp-client-a", "rabbitmq-broker", 5672),
    "grpc": ("grpc-client", "grpc-server", 50051),
}
# Protocols with a TLS variant (--tls) and the port they use with TLS.
TLS_PORTS = {"http": 8443, "http-get": 8443, "mqtt": 8883}
CERTS_DIR = "certs"
NETSHOOT_IMAGE = "nicolaka/netshoot:v0.16"

UDP_SETTLE_SECONDS = {
    "coap": 8,
    "lwm2m": 8,
}


def wait_for_service(env, protocol, timeout=60, tls=False):
    """Block until the protocol's server is reachable from its client container."""
    if protocol in UDP_SETTLE_SECONDS:
        seconds = UDP_SETTLE_SECONDS[protocol]
        print(f"  -> Waiting {seconds}s for {protocol.upper()} server...")
        time.sleep(seconds)
        return

    service, host, port = PROBE[protocol]
    if tls:
        port = TLS_PORTS[protocol]
    code = (
        f"import socket;s=socket.create_connection(('{host}',{port}),timeout=2);s.close()"
    )
    command = ["docker", "compose", "exec", service, "python", "-c", code]

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            subprocess.run(command, env=env, check=True, capture_output=True)
            print(f"  -> {host}:{port} reachable")
            return
        except subprocess.CalledProcessError:
            time.sleep(1)

    raise RuntimeError(f"{protocol} service {host}:{port} never became reachable")


def _capture(argv, env=None, timeout=60):
    """stdout of a command, or None if it fails (provenance is best-effort)."""
    try:
        out = subprocess.run(argv, env=env, capture_output=True, text=True,
                             timeout=timeout, check=True)
        return out.stdout
    except Exception:
        return None


def collect_provenance(env, protocol):
    """What exactly produced this run: code revision, image digests, packages.

    Called once the stack is up, so the pip freeze comes from the client
    container that performs the transfers (not from the host venv).
    """
    meta = {}

    commit = _capture(["git", "rev-parse", "HEAD"])
    if commit:
        meta["git_commit"] = commit.strip()
        dirty = _capture(["git", "status", "--porcelain", "--untracked-files=no"])
        meta["git_dirty"] = bool(dirty and dirty.strip())

    images = {}
    listing = _capture(["docker", "compose", "--profile", protocol, "images",
                        "--format", "json"], env=env)
    if listing:
        try:
            rows = json.loads(listing)
        except json.JSONDecodeError:
            rows = [json.loads(line) for line in listing.splitlines() if line.strip()]
        for row in rows:
            ref = f"{row.get('Repository')}:{row.get('Tag')}"
            if ref in images:
                continue
            digests = _capture(["docker", "image", "inspect", "--format",
                                "{{json .RepoDigests}}", row.get("ID", ref)])
            images[ref] = {
                "id": row.get("ID"),
                "repo_digests": json.loads(digests) if digests else [],
            }
    meta["images"] = images

    service = RUNNERS[protocol]["service"]
    freeze = _capture(["docker", "compose", "exec", "-T", service, "pip", "freeze"], env=env)
    if freeze:
        meta["pip_freeze"] = sorted(line for line in freeze.splitlines() if line.strip())

    return meta


def resolve_sizes(tokens):
    """Map --sizes tokens (e.g. 250kb, 1mb) to payload filenames in data/.

    Payloads are named binary_file_<size>.bin by data/binary_file_generator.py.
    Fails fast if a requested size has no payload file.
    """
    from common.file_manager import DATA_DIR

    files = []
    for token in tokens:
        name = f"binary_file_{token.strip().lower()}.bin"
        if not os.path.isfile(os.path.join(DATA_DIR, name)):
            available = sorted(
                f[len("binary_file_"):-len(".bin")]
                for f in os.listdir(DATA_DIR)
                if f.startswith("binary_file_") and f.endswith(".bin")
            )
            raise SystemExit(f"ERROR: no payload for size '{token}' "
                             f"(available: {', '.join(available)})")
        files.append(name)
    files.sort(key=lambda f: os.path.getsize(os.path.join(DATA_DIR, f)))
    return files


def ensure_certs():
    """Generate the test CA + server certificate once (scripts/gen_certs.sh).

    Runs inside the pinned netshoot image so the host needs no openssl.
    """
    if os.path.isfile(os.path.join(CERTS_DIR, "ca.crt")):
        return
    print("Generating test TLS certificates (scripts/gen_certs.sh)...")
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{os.path.abspath('.')}:/work", "-w", "/work",
         "--entrypoint", "sh", NETSHOOT_IMAGE, "scripts/gen_certs.sh", CERTS_DIR],
        check=True,
    )


def run_experiment(protocol, profile, run_id=None, files=None, qos_levels=None,
                   tls=False, meta=None, repeat_index=None):
    print(f"\n=== Running {protocol.upper()} | {profile} ===")

    # Every experiment writes to its own immutable run directory
    # (output/runs/<run_id>/) shared by the host harness and the containers.
    output_dir = os.path.abspath("output")
    rid = run_id or runs.run_id_for(protocol, profile)
    if tls and not run_id:
        rid += "_tls"
    if repeat_index is not None and not run_id:
        rid += f"_r{repeat_index}"

    env = BASE_ENV.copy()
    env["COMPOSE_FILE"] = COMPOSE_FILE_AUTOMATED
    env["COMPOSE_PROFILES"] = protocol
    env["NETWORK_PROFILE"] = profile
    env["RUN_ID"] = rid
    env["TLS"] = "1" if tls else "0"
    env["MOSQUITTO_CONF"] = "mosquitto-tls.conf" if tls else "mosquitto.conf"

    # Publish the experiment environment BEFORE creating the run: new_run()
    # snapshots os.environ into the manifest, so setting it afterwards records
    # the previous run's NETWORK_PROFILE (or empty for the first run).
    # run_protocol() (which runs in this process and drives the
    # capture/analysis/CSV writing) also needs to see the same
    # COMPOSE_FILE / COMPOSE_PROFILES / RUN_ID as the containers, otherwise
    # pcap rows land outside the run dir.
    os.environ.update(env)

    runs.new_run(output_dir, protocol, profile, run_id=rid,
                 meta={"tls": tls, "shaping_model": "access-link-bidir-v2", **(meta or {})})

    # Sidecar marker lets containers (which lack RUN_ID) resolve the active run
    # through the output bind mount.
    runs.write_marker(output_dir, rid)

    try:
        # Start only the selected protocol's stack (clients stay idle; tc is
        # applied inside each container by scripts/network_chaos.sh).
        subprocess.run(
            [
                "docker", "compose",
                "--profile", protocol,
                "up", "-d",
            ],
            env=env,
            check=True,
        )

        wait_for_service(env, protocol, tls=tls)

        runs.update_manifest(output_dir, rid, collect_provenance(env, protocol))

        run_protocol(protocol, files=files, qos_levels=qos_levels)

    finally:
        # Always clean up
        subprocess.run(["docker", "compose", "down", "-v"], env=env)
        runs.clear_marker(output_dir)


def ensure_payloads() -> None:
    """Fail fast (before building/starting anything) when no .bin payloads exist.

    Every transfer needs the host-side ``data/*.bin`` files; without them the
    sweep cannot run, so surface an actionable message instead of a traceback
    deep inside the first protocol.
    """
    from common.file_manager import DATA_DIR, load_binary_files

    try:
        load_binary_files()
    except Exception as e:
        print(f"\nERROR: {e}")
        print(f"(payloads are read from '{os.path.abspath(DATA_DIR)}')")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Run automated protocol benchmarks.")
    parser.add_argument(
        "--protocols",
        nargs="+",
        choices=list(RUNNERS),
        default=list(RUNNERS),
        help="Protocols to run (default: all).",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["mobile"],
        help="Network profiles to run (default: mobile).",
    )
    parser.add_argument(
        "--sizes",
        default=None,
        help="Comma-separated payload sizes to transfer, e.g. 250kb,1mb,5mb "
             "(default: every data/*.bin). Use it to keep slow profiles short.",
    )
    parser.add_argument(
        "--qos",
        nargs="+",
        type=int,
        default=None,
        help="MQTT QoS levels to sweep (default: 1 2).",
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        help="Run the TLS variant (HTTPS on 8443 / MQTT over TLS on 8883). "
             f"Only for: {', '.join(TLS_PORTS)}.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat every protocol x profile combination N times (n for the "
             "median/IQR statistics; the thesis tables use 5).",
    )
    parser.add_argument(
        "--sweep-id",
        default=None,
        help="Label shared by all runs of this sweep (recorded in run.json; "
             "export_measurements.py --sweep-id aggregates them). Default with "
             "--repeat > 1: sweep-<timestamp>.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for shuffling the combination order per repetition "
             "(default: random, recorded in run.json).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id instead of the auto-generated timestamp+protocol+profile one.",
    )
    args = parser.parse_args()

    if not args.protocols or not args.profiles:
        print("Nothing to run.")
        return

    if args.tls:
        unsupported = [p for p in args.protocols if p not in TLS_PORTS]
        if unsupported:
            parser.error(f"--tls is only implemented for {', '.join(TLS_PORTS)} "
                         f"(not: {', '.join(unsupported)})")
        ensure_certs()

    ensure_payloads()
    files = resolve_sizes(args.sizes.split(",")) if args.sizes else None

    build_cmd = ["docker", "compose", "-f", COMPOSE_FILE_AUTOMATED]
    for protocol in args.protocols:
        build_cmd += ["--profile", protocol]
    build_cmd += ["build"]
    subprocess.run(build_cmd, check=True)

    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    if args.run_id and args.repeat > 1:
        parser.error("--run-id cannot be combined with --repeat > 1")

    combos = list(itertools.product(args.protocols, args.profiles))
    sweep_id = args.sweep_id or (f"sweep-{runs.now_utc_stamp()}" if args.repeat > 1 else None)
    seed = args.seed if args.seed is not None else random.randrange(2**31)
    rng = random.Random(seed)
    if sweep_id:
        print(f"Sweep {sweep_id}: {len(combos)} combination(s) x {args.repeat} "
              f"repetition(s), order seed {seed}")

    failures = []
    for repeat_index in range(1, args.repeat + 1):
        order = combos[:]
        if args.repeat > 1:
            # Shuffle per repetition so drift over time (host load, thermal
            # state) doesn't systematically favour the protocols run first.
            rng.shuffle(order)
        for protocol, profile in order:
            meta = ({"sweep_id": sweep_id, "repeat_index": repeat_index, "seed": seed}
                    if sweep_id else {})
            try:
                run_experiment(protocol, profile, run_id=args.run_id,
                               files=files, qos_levels=args.qos, tls=args.tls,
                               meta=meta,
                               repeat_index=repeat_index if sweep_id else None)
            except Exception as e:
                # One protocol/profile failing (e.g. a stack that won't come up)
                # must not abort the rest of the sweep, otherwise a single bad
                # combination hides the state of every remaining one.
                failures.append((protocol, profile, e))
                print(f"\n!!! {protocol.upper()} | {profile} FAILED: {e}")

    if failures:
        print("\n=== Sweep summary (failures) ===")
        for protocol, profile, error in failures:
            print(f"  FAILED  {protocol}/{profile}: {error}")
        sys.exit(1)

    print("\nAll runs completed.")


if __name__ == "__main__":
    main()