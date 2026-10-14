"""Fourteenth battery (lab/battery_round14.py): confirm the two ideas that passed.

Spec (owner, 13 October 2026): about 35 SPRT tests ran on 13 October 2026, each with a 5% chance
of a false "better", so one or two passes can be luck. Before anything goes to the game, each
idea that passed is tested again on new matchups (new seeds, two per idea): fusion25 on Strong
(+2.5%, z 2.8; but fusion0 and fusion50 were worse) and spy-first on Original (+2.2%, z 2.8).

Given the battery, then each confirmation is an 'ab' job of the same idea and mode as the pass,
with seeds never used before.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import battery_round11, battery_round12, battery_round13  # noqa: E402,E401
import battery_round14 as battery  # noqa: E402


def test_confirmations_use_new_seeds():
    jobs = battery.jobs()
    assert sorted((j['policy'].rsplit('+', 1)[1], j['base_decks']) for j in jobs) == [
        ('fusion25', 'strong'), ('fusion25', 'strong'), ('spy-first', 'original'), ('spy-first', 'original')]
    old = {j['seeds'][0] for m in (battery_round11, battery_round12, battery_round13) for j in m.jobs()}
    seeds = {j['seeds'][0] for j in jobs}
    assert len(seeds) == 4 and not seeds & old and all(j['batch'] == 100 for j in jobs)
