"""SPSA tuning plays the same scene as the benchmarks it is validated against.

Given a tune job with a policy carrying scene switches and an NPC deck mode,
when its iteration tasks are built and evaluated,
then each task carries that policy and deck mode, and a task with the shipped weights
scores exactly like the benchmark match of the same scene.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))

import core  # noqa: E402
import evaluate_pool  # noqa: E402
import gwentsim.response_v8 as v8  # noqa: E402
from gwentsim.tuning import DEFAULTS  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


def test_tune_tasks_carry_scene():
    tasks = core.tune_payloads(dict(policy=SCENE, npc_decks='balanced', pool=2, player=2))
    assert tasks and all(t['policy'] == SCENE for t in tasks)
    assert all(t.get('npc_decks') == 'balanced' for t in tasks if t['source'] == 'player')


def test_tune_eval_with_shipped_weights_matches_benchmark():
    saved = v8.VARIANT, v8.NPC_SEAT
    try:
        for pair, seed in ((0, 1401), (1, 1402), (2, 1403), (3, 1404)):
            task = dict(kind='tune-eval', source='player', pair=pair, seed=seed, swap=False, profile='hard',
                        policy=SCENE, npc_decks='balanced', params=dict(DEFAULTS), iteration=0, sign=1)
            score = core.run_payload(task)['score']
            v8.VARIANT = frozenset({'player-mulligan', 'base-mulligan'})
            bench = evaluate_pool.run_player(pair, seed, False, 'response-v8', 2, 'balanced')
            expected = 1.0 if bench['winner'] == bench['npcSeat'] else 0.5 if bench['winner'] not in (0, 1) else 0.0
            assert score == expected, (pair, seed)
    finally:
        v8.VARIANT, v8.NPC_SEAT = saved


def test_tune_job_keeps_scene_from_request():
    body = dict(kind='tune', source='pool', seeds=[1], profile='hard', iterations=60,
                policy=SCENE, npc_decks='balanced')
    params = core.job_params('tune', body)
    assert params['policy'] == SCENE and params['npc_decks'] == 'balanced'


def test_spsa_step_compares_only_matchups_finished_on_both_sides():
    # Given an iteration where one matchup failed on the plus side only
    import json
    import sqlite3
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    params = dict(iteration=0, iterations=1, a=0.4, c=0.1, A=5, alpha=0.602, gamma=0.101, low=0.25, high=4.0,
                  x={n: 1.0 for n in DEFAULTS}, delta={n: 1 for n in DEFAULTS}, history=[])
    jid = db.execute("INSERT INTO jobs(name, kind, params, created) VALUES ('t', 'tune', ?, 0)",
                     (json.dumps(params),)).lastrowid
    rows = [(1, 0, 'done', 1.0), (1, 1, 'error', None), (-1, 0, 'done', 0.0), (-1, 1, 'done', 1.0)]
    for i, (sign, pair, status, score) in enumerate(rows):
        db.execute("INSERT INTO tasks(job_id, idx, payload, status, result) VALUES (?, ?, ?, ?, ?)",
                   (jid, i, json.dumps(dict(iteration=0, sign=sign, pair=pair, source='player')), status,
                    json.dumps(dict(score=score, games=1)) if score is not None else None))
    # When the step runs, then the plus and minus means use the same matchups (pair 0 only)
    core.tune_step(db)
    step = json.loads(db.execute("SELECT params FROM jobs").fetchone()[0])['history'][0]
    assert (step['plus'], step['minus']) == (1.0, 0.0)
