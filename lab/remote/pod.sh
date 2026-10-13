#!/bin/bash
# Rented-server helpers for Lab batteries (Runpod SSH proxy: ssh POD@ssh.runpod.io, scripted stdin).
#   pod.sh bundle OUTDIR                    code.tgz + upload.txt from this repository
#   pod.sh setup  SSH_USER OUTDIR           upload the code, install PyPy and start the Lab server
#   pod.sh test   SSH_USER                  run the Python test suite on the pod (never on the PC)
#   pod.sh start  SSH_USER "BATTERY ARGS"   queue a battery, e.g. "lab/battery_round8.py --cells strong:medium"
#   pod.sh wait   SSH_USER OUT.sqlite3      wait until every active job is done, then pull the database
set -e
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd)
S() { timeout ${2:-300} ssh -tt -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "$1@ssh.runpod.io"; }
case "$1" in
bundle)
  OUT=$2; mkdir -p "$OUT"; cd "$ROOT"
  # Game-derived inputs (vanilla XML/AS, records) go only to the rented server, never to git.
  tar czf "$OUT/code.tgz" --exclude=__pycache__ --exclude='*.pyc' sim lab tools/*.py mod/v8 mod/settings \
      game/records/*.json game/vanilla/xml game/vanilla/as game/vanilla/as_deck_builder
  { printf "stty -echo\nmkdir -p /srv/lab && cd /srv/lab\nbase64 -d > code.tgz <<'B64EOF'\n"; base64 -w 76 "$OUT/code.tgz"
    printf "B64EOF\ntar xzf code.tgz && echo UNPACKED \$(sha256sum code.tgz | cut -c1-16)\nexit\n"; } > "$OUT/upload.txt"
  echo "BUNDLE $(du -h "$OUT/code.tgz" | cut -f1) $(sha256sum "$OUT/code.tgz" | cut -c1-16)";;
setup)
  until S "$2" 60 <<< $'stty -echo\necho READY\nexit' 2>&1 | tr -d '\r' | grep -q "^READY"; do sleep 15; done
  S "$2" 900 < "$3/upload.txt" 2>&1 | tr -d '\r' | grep -a "^UNPACKED"
  S "$2" 900 < "$HERE/setup.txt" 2>&1 | tr -d '\r' | grep -a "^APT_DONE\|^PYV\|^PSUTIL\|^SETUP_END" | tr '\n' ' '; echo;;
test)
  printf 'stty -echo\ncd /srv/lab && python3 -m pytest -q -p no:cacheprovider sim/tests 2>&1 | tail -25 | sed "s/^/T /"\nexit\n' \
    | S "$2" 1800 2>&1 | tr -d '\r' | grep -a "^T " | cut -c3-;;
start)
  printf 'stty -echo\ncd /srv/lab\nP=$(ls -d ~/.local/share/uv/python/pypy-3.11*/bin/pypy3.11 | head -1); curl -s -X POST -H "Content-Type: application/json" -d "{\\"workers\\":32,\\"autoresume\\":true,\\"worker_python\\":\\"$P\\"}" 127.0.0.1:8765/api/settings </dev/null >/dev/null\npython3 %s 8765 </dev/null | grep -c ok | sed "s/^/QUEUED /"\ncurl -s -X POST -H "Content-Type: application/json" -d "{}" 127.0.0.1:8765/api/resume </dev/null >/dev/null\nsleep 20; curl -s 127.0.0.1:8765/api/status </dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(\\"STATE\\",d[\\"state\\"],d[\\"activeWorkers\\"],sum(j[\\"total\\"] for j in d[\\"jobs\\"]))"\nexit\n' "$3" \
    | S "$2" 300 2>&1 | tr -d '\r' | grep -a "^QUEUED\|^STATE" | tr '\n' ' '; echo;;
wait)
  sleep 60
  until S "$2" 60 < "$HERE/probe.txt" 2>&1 | tr -d '\r' | grep -a "^STATUS" | awk '{exit !($4>0 && $3+$5>=$4)}'; do sleep 60; done
  "$HERE/pulldb.sh" "$2" "$3";;
*) sed -n 2,7p "$0"; exit 1;;
esac
