"""Fifteenth battery (lab/battery_round15.py): the autopilot's next ideas, run early on Runpod.

Spec (owner, 13 October 2026): spend the last Runpod credit on the heaviest work. The Google Cloud
autopilot already runs the first three ideas of its list; the rented servers take the next ones,
as the very same jobs (same names and seeds as the autopilot would queue), so their results can
replace those ideas on the cloud server later.

Given the battery, then its jobs are exactly the autopilot's idea jobs after the first three.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import autopilot  # noqa: E402
import battery_round15 as battery  # noqa: E402


def test_jobs_are_the_autopilot_ideas_after_the_first_three():
    expected = [autopilot.idea_job(s, d) for s, d in autopilot.IDEAS[3:3 + len(battery.jobs())]]
    assert battery.jobs() == expected and len(expected) >= 6
    names = [j['name'] for i in range(3) for j in battery.jobs(pod=(i, 3))]
    assert sorted(names) == sorted(j['name'] for j in expected)
