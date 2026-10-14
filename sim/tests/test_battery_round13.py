"""Thirteenth battery (lab/battery_round13.py): strategy fusion in the NPC's second search ply.

Spec (owner, 13 October 2026): the second ply picks the NPC's next move separately in each
imagined player hand, as if it knew the hand (strategy fusion, the known flaw of sampling-based
search). Test keeping 0, 25 and 50% of that gain (fusion0, fusion25, fusion50), Adaptive and
Strong, as paired SPRT A/B jobs with the same node budget.

Given the battery, then every test is an 'ab' job of a fusion switch with its own seed, apart
from rounds 11 and 12, and the servers split it once.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import battery_round12  # noqa: E402
import battery_round13 as battery  # noqa: E402
from gwentsim import response_search, response_v8 as v8  # noqa: E402
from gwentsim.options import Difficulty  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


def test_every_test_is_a_fusion_switch():
    jobs = battery.jobs()
    assert len(jobs) == 6
    for job in jobs:
        switch = job['policy'][len(SCENE) + 1:]
        v8.VARIANT, v8.NPC_SEAT = frozenset({switch}), 1
        assert switch.startswith('fusion') and response_search.search_settings(Difficulty.HARD, 1).fusion < 1
    seeds = {j['seeds'][0] for j in jobs}
    assert len(seeds) == 6 and not seeds & {j['seeds'][0] for j in battery_round12.jobs()}
    assert not seeds & {2201 + i for i in range(13)}
    names = [j['name'] for i in range(2) for j in battery.jobs(pod=(i, 2))]
    assert sorted(names) == sorted(j['name'] for j in jobs)
