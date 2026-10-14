"""Seventeenth battery (lab/battery_round17.py): the round-1 spending ceiling (r1capN).

Spec (owner, 13 October 2026), from match g167: test r1cap10, r1cap15 and r1cap20 on Adaptive,
Strong and Original as paired SPRT A/B jobs, named like the autopilot's idea jobs (same names and
seeds), so the cloud server can take them over or skip them later.

Given the battery, then it holds the nine r1cap idea jobs, each a known switch of the NPC.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import autopilot  # noqa: E402
import battery_round17 as battery  # noqa: E402
from gwentsim import response_v8 as v8  # noqa: E402


def test_nine_r1cap_idea_jobs():
    jobs = battery.jobs()
    assert len(jobs) == 9
    assert jobs == [autopilot.idea_job('r1cap%d' % n, d) for n in (10, 15, 20) for d in ('balanced', 'strong', 'original')]
    for j in jobs:
        switch = j['policy'].rsplit('+', 1)[1]
        assert v8.r1_cap_lead(frozenset({switch}), 1, 1) in (10, 15, 20)
    names = [j['name'] for i in range(2) for j in battery.jobs(pod=(i, 2))]
    assert sorted(names) == sorted(j['name'] for j in jobs)
