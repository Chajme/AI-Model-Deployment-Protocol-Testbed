"""
Run the v2 re-run matrix (docs/protocol-analysis-completion-plan.md, Phase 8).

Each profile is its own sweep id (v2-<profile>), so a crash only loses that
batch and the export can combine any subset:

    python scripts/run_v2_matrix.py --dry-run          # print the commands
    python scripts/run_v2_matrix.py                    # run everything (~15-25 h)
    python scripts/run_v2_matrix.py --profiles ltem nbiot --repeat 5
    python scripts/run_v2_matrix.py --skip-optional    # without mqtt-windowed

Then:
    python scripts/export_measurements.py --sweep-id v2-good v2-iot v2-mobile \
        v2-harsh v2-ltem v2-nbiot
"""

import argparse
import os
import subprocess
import sys

TCP_PROTOCOLS = ["http", "http-get", "mqtt", "grpc", "amqp"]
BLOCK_PROTOCOLS = ["coap", "lwm2m"]
TLS_PROTOCOLS = ["http-get", "mqtt"]

# profile -> (sizes for TCP-based protocols, sizes for CoAP/LwM2M)
MATRIX = {
    "good":   ("250kb,1mb,5mb,20mb,50mb", "250kb,1mb,5mb"),
    "iot":    ("250kb,1mb,5mb", "250kb,1mb"),
    "mobile": ("250kb,1mb,5mb", "250kb,1mb"),
    "harsh":  ("250kb,1mb,5mb", "250kb,1mb"),
    "ltem":   ("250kb,1mb,5mb", "250kb,1mb"),
    "nbiot":  ("250kb,1mb", "250kb"),
}
TLS_PROFILES = ["good", "ltem", "nbiot"]
WINDOWED_PROFILES = ["good", "iot", "ltem"]


def commands(profiles, repeat, skip_optional):
    py = sys.executable
    for profile in profiles:
        tcp_sizes, block_sizes = MATRIX[profile]
        sweep = f"v2-{profile}"
        common = ["--profiles", profile, "--repeat", str(repeat), "--sweep-id", sweep, "--qos", "1"]
        yield [py, "runner.py", "--protocols", *TCP_PROTOCOLS, "--sizes", tcp_sizes, *common]
        yield [py, "runner.py", "--protocols", *BLOCK_PROTOCOLS, "--sizes", block_sizes, *common]
        if profile in TLS_PROFILES:
            yield [py, "runner.py", "--protocols", *TLS_PROTOCOLS, "--sizes", tcp_sizes,
                   "--tls", *common]
        if not skip_optional and profile in WINDOWED_PROFILES:
            yield [py, "runner.py", "--protocols", "mqtt-windowed", "--sizes", tcp_sizes, *common]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profiles", nargs="+", choices=list(MATRIX), default=list(MATRIX))
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--skip-optional", action="store_true",
                        help="Leave out the optional mqtt-windowed rows.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the commands.")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    failed = []
    for cmd in commands(args.profiles, args.repeat, args.skip_optional):
        printable = " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd))
        print(f"\n>>> {printable}", flush=True)
        if args.dry_run:
            continue
        # runner.py exits non-zero when any combination failed; keep going so
        # one bad batch does not block the rest of the matrix.
        if subprocess.run(cmd, cwd=root).returncode != 0:
            failed.append(printable)

    if failed:
        print("\nBatches with failures (see their run directories):")
        for line in failed:
            print(f"  {line}")
        sys.exit(1)


if __name__ == "__main__":
    main()
