"""Sixteenth battery (lab/battery_round16.py): confirm on Runpod the three Original-mode passes.

Spec (owner, 13 October 2026): the cloud autopilot queued two confirmations for each idea that
passed on Runpod in round 15 (fusion15, fusion20 and spy-first+fusion25, all on Original). They
are slow there, so the last Runpod credit runs the very same jobs (same names and seeds), and the
cloud server drops them afterwards.

Given the battery, then its jobs are exactly the autopilot's confirmations of the outside passes.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import autopilot  # noqa: E402
import battery_round16 as battery  # noqa: E402


def test_jobs_are_the_autopilot_confirmations_of_outside_passes():
    expected = autopilot.outside_confirmations(battery.ROUND15_PASSES)
    assert battery.jobs() == expected and len(expected) == 6
    assert [j['name'] for j in expected][:2] == ['AUTO confirm runpod:fusion15:original 1',
                                                 'AUTO confirm runpod:fusion15:original 2']
