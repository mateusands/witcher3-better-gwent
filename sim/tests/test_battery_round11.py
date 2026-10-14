"""Eleventh battery (lab/battery_round11.py): paired SPRT A/B tests on Runpod.

Spec (owner, 13 October 2026): confirm the pending NPC ideas with sequential tests on three
rented 32-core servers, while the Google Cloud server keeps its own jobs.
- Every test is a Lab job of kind 'ab' (batches of 100): the candidate (an NPC switch or deck flag) against the
  fair scene on the same matchups, stopping as soon as the SPRT decides (max 6,000 matchups).
- Tests already running on Google Cloud are not repeated (spy-first balanced and strong, draw15
  balanced, spyval balanced). spyval is an Adaptive-only flag.
- The tests split over three servers with --pod I/3: each test runs on exactly one server, the
  groups differ in size by at most one, and each test has its own seed.

Given the battery, when it is split over three servers, then every test runs once, as an 'ab'
job with the fair scene as its base.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import battery_round11 as battery  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'
ON_GOOGLE = {('spy-first', 'balanced'), ('spy-first', 'strong'), ('draw15', 'balanced'), ('spyval', 'balanced')}


def test_every_test_is_a_paired_sprt_job_against_the_fair_scene():
    jobs = battery.jobs()
    assert len(jobs) >= 12
    for job in jobs:
        assert job['kind'] == 'ab' and job['source'] == 'player' and job['profile'] == 'hard'
        assert job['base_policy'] == SCENE and job['base_decks'] in ('balanced', 'strong', 'original')
        assert job['policy'].startswith(SCENE) and job['npc_decks'].split(':')[0] == job['base_decks']
        assert (job['policy'], job['npc_decks']) != (job['base_policy'], job['base_decks'])
        assert job['max_tasks'] == 6000 and job['batch'] == 100
    assert len({j['seeds'][0] for j in jobs}) == len(jobs)
    assert len({j['name'] for j in jobs}) == len(jobs)


def test_tests_running_on_google_are_not_repeated():
    for idea, decks in battery.TESTS:
        assert (idea, decks) not in ON_GOOGLE
        if 'spyval' in idea:
            assert decks == 'balanced'


def test_three_servers_split_the_tests_once_and_evenly():
    groups = [battery.jobs(pod=(i, 3)) for i in range(3)]
    names = [j['name'] for g in groups for j in g]
    assert sorted(names) == sorted(j['name'] for j in battery.jobs())
    sizes = [len(g) for g in groups]
    assert max(sizes) - min(sizes) <= 1
