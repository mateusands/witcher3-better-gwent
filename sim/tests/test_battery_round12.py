"""Twelfth battery (lab/battery_round12.py): the response-search switches on Runpod.

Spec (owner, 13 October 2026): after round 11 (weights and rules, none better), test new ideas
on the NPC's search itself, Adaptive and Strong, as paired SPRT A/B jobs: more imagined hands
(beliefs6, beliefs8), a narrower or wider second ply (beam4, beam12), a pass margin (pass10,
pass25) and caution towards the worst hand (caution25, caution50). Every switch keeps the same
node budget, so the NPC never thinks longer in the game.

Given the battery, when it is split over three servers, then every test is a valid 'ab' job of
a known search switch, each runs once and each has its own seed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import battery_round12 as battery  # noqa: E402
from gwentsim import response_search, response_v8 as v8  # noqa: E402
from gwentsim.options import Difficulty  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


def test_every_test_is_a_search_switch_against_the_fair_scene():
    jobs = battery.jobs()
    assert len(jobs) == 16
    shipped = response_search.search_settings(Difficulty.HARD, 1)
    for job in jobs:
        assert job['kind'] == 'ab' and job['base_policy'] == SCENE and job['npc_decks'] == job['base_decks']
        switch = job['policy'][len(SCENE) + 1:]
        v8.VARIANT, v8.NPC_SEAT = frozenset({switch}), 1
        assert response_search.search_settings(Difficulty.HARD, 1) != shipped, switch
        assert response_search.search_settings(Difficulty.HARD, 1).budget == shipped.budget
    assert len({j['seeds'][0] for j in jobs}) == len(jobs)
    assert not {j['seeds'][0] for j in jobs} & {2201 + i for i in range(13)}      # not round 11's


def test_three_servers_split_the_tests_once():
    names = [j['name'] for i in range(3) for j in battery.jobs(pod=(i, 3))]
    assert sorted(names) == sorted(j['name'] for j in battery.jobs())
