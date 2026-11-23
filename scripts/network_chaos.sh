#!/bin/sh
# Apply a tc (netem + tbf) network profile to this container's egress, then
# either run APP_COMMAND or stay idle.
#
# Environment:
#   NETWORK_PROFILE  good | iot | harsh | mobile | satellite | ltem | nbiot | none
#                    (default: iot). "none" applies no shaping at all.
#   SHAPE_IFACE      interface to shape (default: eth0)
#   SHAPE_DST        optional hostname. When set, ONLY packets addressed to that
#                    host are shaped; all other egress stays clean. Used by the
#                    MQTT/AMQP capture sidecars, which share the broker's network
#                    namespace: they shape broker -> device (client-b) traffic
#                    without touching broker -> server (client-a) traffic.
#   APP_COMMAND      command to exec after shaping (default: stay idle)
#
# Shaping model ("bidirectional access link", see docs/network-chaos.md): the
# one constrained link is between the device and its data source, and both of
# its endpoints shape their own egress, so profile values are per direction
# and RTT ~= 2 x delay.
set -e

PROFILE=${NETWORK_PROFILE:-iot}
IFACE=${SHAPE_IFACE:-eth0}

echo "[tc] Applying network profile: $PROFILE on $IFACE${SHAPE_DST:+ (only towards $SHAPE_DST)}"

# Clean up (important for restarts)
tc qdisc del dev "$IFACE" root 2>/dev/null || true

# Profile -> netem and tbf argument strings. One place per profile, used by
# both the whole-interface and the destination-only mode.
set_profile() {
  case "$1" in
    good)
      NETEM="delay 40ms 10ms loss 0.1%"
      TBF="rate 10mbit burst 64kbit latency 50ms"
      ;;
    iot)
      NETEM="delay 200ms 100ms 30% loss 2% 25% duplicate 0.5% reorder 0.2% 50%"
      TBF="rate 512kbit burst 32kbit latency 400ms"
      ;;
    harsh)
      NETEM="delay 300ms 200ms 50% loss gemodel 1% 50% 90% 1% duplicate 1% reorder 1% 50%"
      TBF="rate 256kbit burst 16kbit latency 800ms"
      ;;
    mobile)
      # Unstable cellular (spikes + variability)
      NETEM="delay 150ms 150ms 60% loss 3% 40% reorder 0.5% 50%"
      TBF="rate 1mbit burst 32kbit latency 300ms"
      ;;
    satellite)
      # Extreme latency, low loss but painful TCP behavior
      NETEM="delay 600ms 100ms 20% loss 0.5%"
      TBF="rate 1mbit burst 64kbit latency 1000ms"
      ;;
    ltem)
      # LTE-M (Cat-M1): ~300 kbit/s realistic throughput (3GPP TS 36.306),
      # one-way 75 ms -> RTT ~150 ms with both link ends shaped.
      # Starting values from the literature; recalibrate on the field SIM.
      NETEM="delay 75ms 25ms 25% loss 0.5%"
      TBF="rate 300kbit burst 16kbit latency 1500ms"
      ;;
    nbiot)
      # NB-IoT (Cat-NB1): ~26 kbit/s downlink peak (3GPP TS 36.306), latency
      # target <= 10 s (3GPP TR 45.820); one-way 800 ms -> RTT ~1.6 s with both
      # link ends shaped. Moderate jitter: large netem jitter reorders packets
      # and would penalise TCP unrealistically. Recalibrate on the field SIM.
      NETEM="delay 800ms 150ms 25% loss 1%"
      TBF="rate 25kbit burst 4kbit latency 8000ms"
      ;;
    none)
      NETEM=""
      TBF=""
      ;;
    *)
      echo "[tc] Unknown profile: $1"
      exit 1
      ;;
  esac
}

# Shape all egress of $IFACE.
apply_root() {
  # shellcheck disable=SC2086  # word splitting of the argument strings is intended
  tc qdisc add dev "$IFACE" root handle 1: netem $NETEM
  # shellcheck disable=SC2086
  tc qdisc add dev "$IFACE" parent 1:1 handle 10: tbf $TBF
}

# Resolve a hostname to its IPv4 address, waiting for it to come up.
resolve_ip() {
  i=0
  while [ "$i" -lt 30 ]; do
    ip_addr=$(getent hosts "$1" | awk '{print $1; exit}')
    if [ -n "$ip_addr" ]; then
      echo "$ip_addr"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  return 1
}

# Shape only egress addressed to $SHAPE_DST: default traffic goes to an
# unshaped prio band (1:2), the u32 filter sends the destination's packets to
# band 1:3, which carries the profile's netem + tbf.
apply_dst() {
  if ! DST_IP=$(resolve_ip "$SHAPE_DST"); then
    echo "[tc] Could not resolve SHAPE_DST=$SHAPE_DST"
    exit 1
  fi
  echo "[tc] $SHAPE_DST resolves to $DST_IP"
  tc qdisc add dev "$IFACE" root handle 1: prio bands 3 priomap 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
  # shellcheck disable=SC2086
  tc qdisc add dev "$IFACE" parent 1:3 handle 30: netem $NETEM
  # shellcheck disable=SC2086
  tc qdisc add dev "$IFACE" parent 30:1 handle 31: tbf $TBF
  tc filter add dev "$IFACE" parent 1:0 protocol ip prio 1 u32 \
    match ip dst "$DST_IP"/32 flowid 1:3
}

set_profile "$PROFILE"

if [ "$PROFILE" = "none" ]; then
  echo "[tc] Profile 'none': leaving $IFACE unshaped."
elif [ -n "$SHAPE_DST" ]; then
  apply_dst
else
  apply_root
fi

echo "[tc] Active qdisc:"
tc qdisc show dev "$IFACE"
if [ -n "$SHAPE_DST" ] && [ "$PROFILE" != "none" ]; then
  echo "[tc] Active filters:"
  tc filter show dev "$IFACE"
fi

if [ -z "$APP_COMMAND" ]; then
  echo "[app] APP_COMMAND not set -- applying tc only and staying idle."
  echo "      (transfers are driven externally via 'docker compose exec')"
  exec sleep infinity
fi

echo "[app] Starting: $APP_COMMAND"
exec sh -c "$APP_COMMAND"
