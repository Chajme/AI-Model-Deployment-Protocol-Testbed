#!/bin/sh
set -e

PROFILE=${NETWORK_PROFILE:-iot}

echo "[tc] Applying network profile: $PROFILE"

# Clean up (important for restarts)
tc qdisc del dev eth0 root 2>/dev/null || true

apply_iot() {
  tc qdisc add dev eth0 root handle 1: netem \
    delay 200ms 100ms 30% \
    loss 2% 25% \
    duplicate 0.5% \
    reorder 0.2% 50%

  tc qdisc add dev eth0 parent 1:1 handle 10: tbf \
    rate 512kbit \
    burst 32kbit \
    latency 400ms
}

apply_good() {
  tc qdisc add dev eth0 root handle 1: netem \
    delay 40ms 10ms \
    loss 0.1%

  tc qdisc add dev eth0 parent 1:1 handle 10: tbf \
    rate 10mbit \
    burst 64kbit \
    latency 50ms
}

apply_harsh() {
  tc qdisc add dev eth0 root handle 1: netem \
    delay 300ms 200ms 50% \
    loss gemodel 1% 50% 90% 1% \
    duplicate 1% \
    reorder 1% 50%

  tc qdisc add dev eth0 parent 1:1 handle 10: tbf \
    rate 256kbit \
    burst 16kbit \
    latency 800ms
}

apply_mobile() {
  # Simulates unstable cellular (spikes + variability)
  tc qdisc add dev eth0 root handle 1: netem \
    delay 150ms 150ms 60% \
    loss 3% 40% \
    reorder 0.5% 50%

  tc qdisc add dev eth0 parent 1:1 handle 10: tbf \
    rate 1mbit \
    burst 32kbit \
    latency 300ms
}

apply_satellite() {
  # Extreme latency, low loss but painful TCP behavior
  tc qdisc add dev eth0 root handle 1: netem \
    delay 600ms 100ms 20% \
    loss 0.5%

  tc qdisc add dev eth0 parent 1:1 handle 10: tbf \
    rate 1mbit \
    burst 64kbit \
    latency 1000ms
}

case "$PROFILE" in
  good)
    apply_good
    ;;
  iot)
    apply_iot
    ;;
  harsh)
    apply_harsh
    ;;
  mobile)
    apply_mobile
    ;;
  satellite)
    apply_satellite
    ;;
  *)
    echo "[tc] Unknown profile: $PROFILE"
    exit 1
    ;;
esac

echo "[tc] Active qdisc:"
tc qdisc show dev eth0

if [ -z "$APP_COMMAND" ]; then
  echo "[app] APP_COMMAND not set -- applying tc only and staying idle."
  echo "      (transfers are driven externally via 'docker compose exec')"
  exec sleep infinity
fi

echo "[app] Starting: $APP_COMMAND"
exec sh -c "$APP_COMMAND"

