#!/bin/bash
# Texel run on the Lab server: collect positions, fit the utility weights, then queue paired SPRT
# A/B jobs of the fitted weights (balanced and strong) in the Lab.
# Collect and fit use the Lab's worker interpreter (PyPy, about 1.7x faster than CPython) at the
# workers' nice level (15), so the run shares the CPU evenly with the Lab instead of taking it first.
#   sudo systemd-run --unit texel-run --uid mateuswzt /srv/gwentailab/lab/lab/remote/texel_run.sh [JOBS]
set -euo pipefail

JOBS=${1:-4}
DATA=/srv/gwentailab/data/texel
PY=$(tr -d '"' < /srv/gwentailab/pypy_path 2>/dev/null || true)
[ -x "$PY" ] || PY=python3

cd /srv/gwentailab/lab
mkdir -p "$DATA"
nice -n 15 "$PY" sim/texel_tune.py collect --seeds 1 2 3 --swap both --npc-decks balanced --jobs "$JOBS" --out "$DATA/samples.jsonl"
nice -n 15 "$PY" sim/texel_tune.py fit --data "$DATA/samples.jsonl" --out "$DATA/weights.json" --holdout 0.2 > "$DATA/fit.log" 2>&1

python3 - "$DATA/weights.json" <<'PY'
import json, sys, urllib.request
w = json.load(open(sys.argv[1]))
weights = w.get('weights', w)
S = 'response-v8:player-mulligan+base-mulligan'
for decks, seed in (('balanced', 2101), ('strong', 2102)):
    body = dict(kind='ab', name='SPRT texel weights %s' % decks, source='player', seeds=[seed], profile='hard',
                policy=S, npc_decks=decks, base_policy=S, base_decks=decks, batch=200, max_tasks=6000, weights=weights)
    req = urllib.request.Request('http://127.0.0.1:8765/api/job', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    print(urllib.request.urlopen(req, timeout=60).read())
PY
