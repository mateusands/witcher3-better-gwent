"""Player-deck style chart from the shipped AI's mode x level benchmark (lab/dashboard.py).

Spec: the "player-style decks" chart reads the same matches as the deck-mode chart (the shipped
AI in the fair scene, every NPC deck mode and level), pooled per player deck style plus "all".
Candidate ideas (other switches) and tuned weights stay out.

Given a Lab database with fair-scene benchmarks on two levels and two deck modes, and an idea job,
when the dashboard pools the matches by player deck style,
then each style sums every mode and level, "all" sums every style, and the idea job is ignored.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))

import dashboard  # noqa: E402


def make_db(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, params TEXT, created REAL, status TEXT)")
    db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY, job_id INTEGER, idx INTEGER, payload TEXT, status TEXT, "
               "result TEXT, error TEXT, worker INTEGER, started REAL, finished REAL)")
    jobs = ((1, 'easy', 'balanced', 'response-v8:player-mulligan+base-mulligan'),
            (2, 'hard', 'original', 'response-v8:player-mulligan+base-mulligan'),
            (3, 'hard', 'original', 'response-v8:player-mulligan+base-mulligan+fusion10'))
    for jid, profile, mode, policy in jobs:
        params = dict(source='player', policy=policy, profile=profile, npc_decks=mode)
        db.execute("INSERT INTO jobs VALUES (?, 'x', 'benchmark', ?, 0, 'active')", (jid, json.dumps(params)))
        # pair 0 is an early-game deck, pair 1 a recorded deck: Better AI wins both, the native AI one
        for idx, pair in enumerate((0, 1)):
            result = dict(baselineWinner=1 if pair == 0 else 0, seats=[dict(seat=1, winner=1, won=True)])
            db.execute("INSERT INTO tasks(job_id, idx, payload, status, result) VALUES (?, ?, ?, 'done', ?)",
                       (jid, idx, json.dumps(dict(source='player', pair=pair, profile=profile)), json.dumps(result)))
    db.commit(); db.close()


def test_styles_pool_every_mode_and_level_without_ideas(tmp_path, monkeypatch):
    path = tmp_path / 'lab.sqlite3'
    make_db(path)
    monkeypatch.setattr(dashboard, 'player_styles', lambda: ['early', 'recorded'])
    styles = dashboard.style_rows([path])
    assert styles['early'] == [2.0, 2.0, 2]
    assert styles['recorded'] == [2.0, 0.0, 2]
    assert styles['all'] == [4.0, 2.0, 4]
