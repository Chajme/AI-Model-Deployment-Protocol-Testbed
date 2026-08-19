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
import os
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
# CoAP is UDP and is handled with a fixed startup delay instead.
PROBE = {
    "mqtt": ("mqtt-client-a", "mosquitto-broker", 1883),
    "http": ("http-client", "http-server", 8000),
}
COAP_SETTLE_SECONDS = 8


def wait_for_service(env, protocol, timeout=60):
    """Block until the protocol's server is reachable from its client container."""
    if protocol == "coap":
        print(f"  -> Waiting {COAP_SETTLE_SECONDS}s for CoAP server...")
        time.sleep(COAP_SETTLE_SECONDS)
        return

    service, host, port = PROBE[protocol]
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


def run_experiment(protocol, profile, run_id=None):
    print(f"\n=== Running {protocol.upper()} | {profile} ===")

    # Every experiment writes to its own immutable run directory
    # (output/runs/<run_id>/) shared by the host harness and the containers.
    output_dir = os.path.abspath("output")
    rid = runs.new_run(output_dir, protocol, profile, run_id=run_id)

    env = BASE_ENV.copy()
    env["COMPOSE_FILE"] = COMPOSE_FILE_AUTOMATED
    env["COMPOSE_PROFILES"] = protocol
    env["NETWORK_PROFILE"] = profile
    env["MEASUREMENT_SUFFIX"] = f"{protocol}_{profile}"
    env["RUN_ID"] = rid

    # Inherit the experiment environment so that run_protocol() (which runs in
    # this process and drives the capture/analysis/CSV writing) sees the same
    # COMPOSE_FILE / COMPOSE_PROFILES / MEASUREMENT_SUFFIX / RUN_ID as the
    # containers. Without this, pcap rows would land outside the run dir and
    # mix every network profile together.
    os.environ.update(env)

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

        wait_for_service(env, protocol)

        run_protocol(protocol)

    finally:
        # Always clean up
        subprocess.run(["docker", "compose", "down", "-v"], env=env)
        runs.clear_marker(output_dir)


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
        "--run-id",
        default=None,
        help="Explicit run id instead of the auto-generated timestamp+protocol+profile one.",
    )
    args = parser.parse_args()

    if not args.protocols or not args.profiles:
        print("Nothing to run.")
        return

    build_cmd = ["docker", "compose", "-f", COMPOSE_FILE_AUTOMATED]
    for protocol in args.protocols:
        build_cmd += ["--profile", protocol]
    build_cmd += ["build"]
    subprocess.run(build_cmd, check=True)

    for protocol, profile in itertools.product(args.protocols, args.profiles):
        run_experiment(protocol, profile, run_id=args.run_id)


if __name__ == "__main__":
    main()