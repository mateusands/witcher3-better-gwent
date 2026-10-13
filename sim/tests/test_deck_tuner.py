"""Automatic deck tuner (lab/core.py, job kind 'deck-tune').

Spec (owner, 13 October 2026): a small self-improving search for NPC decks. The Lab keeps an incumbent
genome (sim/gwentsim/npc_balance.genome), races several mutations per iteration (a knob for one
player faction, or a global knob), plays each candidate and the incumbent on the same matchups,
luck and opening exchanges (paired), and accepts the best candidate proven better by its own
sequential test (SPRT, see test_sprt.py for the race itself). Then it races again, forever.
Mutations respect the genome limits (0-2 Decoys, a weather effect or none, stepped or default heroes).
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))

import core  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


def job(db, params):
    return db.execute("INSERT INTO jobs(name, kind, params, created) VALUES ('t', 'deck-tune', ?, 0)",
                      (json.dumps(params),)).lastrowid


def test_mutations_stay_within_the_genome_limits():
    genome = {}
    for k in range(300):
        genome = core.mutate(genome, k, seed_base=11)
        assert all(0 <= v <= 2 for v in genome.get('decoys', {}).values())
        assert all(v in core.WEATHERS for v in genome.get('weather', {}).values())
        assert genome.get('heroes', 'default') in ('default', 'stepped')


def test_iteration_tasks_are_paired_and_carry_the_scene():
    params = dict(npc_decks='balanced', profile='hard', policy=SCENE, candidates=2, batch=20, seed_base=11)
    tasks = core.deck_tune_payloads(params)
    assert len(tasks) == 40 and all(t['kind'] == 'deck-eval' for t in tasks)
    assert all(t['policy'] == SCENE and t['npc_decks'] == 'balanced' for t in tasks)
    assert all(t['candidate'] != t['incumbent'] for t in tasks)


def test_weather_choices_are_real_weather_cards():
    # Every weather the tuner may choose is a weather effect with a card the builder can add
    from evaluate_pool import setup
    from gwentsim import constants as C
    templates = setup()['match'].templates
    assert core.WEATHERS[0] == 0
    for effect in core.WEATHERS[1:]:
        assert effect in (C.CardEffect_Melee, C.CardEffect_Ranged, C.CardEffect_Siege)
        assert any(t.is_type(C.CardType_Weather) and t.get_first_effect() == effect for t in templates.values())
    assert core.PLAYER_FACTIONS == (C.FactionId_No_Mans_Land, C.FactionId_Nilfgaard, C.FactionId_Northern_Kingdom,
                                    C.FactionId_Scoiatael, C.FactionId_Skellige)


def test_deck_eval_plays_both_genomes_on_one_matchup():
    task = core.deck_tune_payloads(dict(npc_decks='balanced', profile='hard', policy=SCENE, candidates=1, batch=1, seed_base=11))[0]
    result = core.run_payload(task)
    assert set(result) == {'candidate', 'incumbent'}
    assert all(v in (0.0, 0.5, 1.0) for v in result.values())
    # The same genome on both sides gives the same score (paired: same matchup and luck)
    same = core.run_payload(dict(task, candidate=task['incumbent']))
    assert same['candidate'] == same['incumbent']


def test_status_summary_reads_deck_tune_results():
    # Given a deck-tune job with a finished paired task, when the panel summarises it, then it
    # reports the paired games without failing (the panel's status page lists every job)
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    params = dict(npc_decks='balanced', profile='hard', policy=SCENE, tasks=2, seed_base=11, iteration=0, genome={})
    jid = job(db, params)
    db.execute("INSERT INTO tasks(job_id, idx, payload, status, result) VALUES (?, 0, '{}', 'done', ?)",
               (jid, json.dumps(dict(candidate=1.0, incumbent=0.0))))
    summary = core.job_summary(db, db.execute("SELECT * FROM jobs").fetchone())
    assert summary['matches'] == 2 and summary['candidateScore'] == 1.0 and summary['nativeScore'] == 0.0
