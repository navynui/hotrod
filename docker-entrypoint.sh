#!/bin/sh
# Entry point for the isolated Strata-HotRod test container.
#
# It starts serve/server.py with a run config that points at the model, pack and
# MTP layer mounted read-only from the existing Strata v0.2.13.1 install. It does
# NOT run setup.py: the engine is in the image and nothing should be downloaded
# or written into the mounted shares.
set -e
cd /opt/strata || exit 1

CONFIG="${CONFIG:-/data/config/strata-coder-iq1_m.json}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

[ -f "$CONFIG" ] || { echo "CONFIG=$CONFIG does not exist." >&2; exit 1; }

# Compose sets the A/B knobs even when they are empty, and an empty variable is
# not the same as an unset one to the engine (e.g. an empty STRATA_ROUTE_RESIDENT
# would override STRATA_STANDIN's margin with 0). Drop the empty ones.
for v in STRATA_ROUTE_RESIDENT STRATA_STANDIN STRATA_FRAGILE_RECHECK STRATA_MASK; do
  eval "val=\$$v"
  [ -z "$val" ] && unset "$v"
done

mkdir -p /data/logs /data/state

# STRATA_API_KEY (compose env) is read by the server itself; empty means no key.
# The port is published on 127.0.0.1 only (see docker-compose.yaml).
exec .venv/bin/python serve/server.py \
  --engine strata \
  --config "$CONFIG" \
  --host "$HOST" \
  --port "$PORT"
