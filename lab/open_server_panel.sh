#!/bin/bash
# Opens the Gwent AI Lab panel of the home server through an SSH tunnel (nothing is exposed
# on the network: the server panel only listens on its own 127.0.0.1:8765).
SERVER="${GWENT_LAB_SERVER:?set GWENT_LAB_SERVER=user@host (e.g. in the desktop entry)}"
LOCAL_PORT="${GWENT_LAB_SERVER_PORT:-8766}"
if ! ss -ltn | grep -q "127.0.0.1:${LOCAL_PORT} "; then
  ssh -f -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
      -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:8765" "$SERVER" || {
    notify-send "Gwent AI Lab" "Could not connect to $SERVER" 2>/dev/null; exit 1; }
fi
xdg-open "http://127.0.0.1:${LOCAL_PORT}/" >/dev/null 2>&1 &
