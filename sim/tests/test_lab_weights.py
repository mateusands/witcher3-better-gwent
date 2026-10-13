"""Lab weights path: the shipped weights must reproduce the plain run, switches included."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))

import core  # noqa: E402
from gwentsim.tuning import DEFAULTS  # noqa: E402


def test_default_weights_keep_policy_switches():
    payload = dict(source='player', pair=0, seed=1401, swap=False, profile='hard', npc_decks='balanced',
                   policy='response-v8:player-mulligan+base-mulligan')
    plain = core.run_payload(dict(payload))
    weighted = core.run_payload(dict(payload, weights=dict(DEFAULTS)))
    assert weighted == plain
