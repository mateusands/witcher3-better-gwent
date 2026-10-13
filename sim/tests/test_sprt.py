"""Sequential testing for the Lab (lab/sprt.py, job kind 'ab', and the deck tuner's race).

Spec (owner, 13 October 2026): stop a test as soon as its answer is clear, as chess engines do
(SPRT, Stockfish's Fishtest), instead of always playing a fixed number of matches.
- A paired difference d = candidate - base per matchup (same deal, same luck), in [-1, 1].
- H0: the mean difference is mu0 (no gain); H1: it is mu1 (a real gain). The log-likelihood
  ratio uses the normal approximation with the sample variance (Fishtest's normalised form).
- Bounds from alpha (false "better") and beta (missed gain): accept H1 above log((1-beta)/alpha),
  accept H0 below log(beta/(1-alpha)), else keep playing; never decide before min_n matchups.
- Job kind 'ab': batches of paired tasks (candidate and base on the same matchup) until the SPRT
  decides or max_tasks is reached; the verdict, mean, z and matchups are stored in the job.
- Deck tuner race: several mutations per iteration, each with its own SPRT; a clearly worse or
  equal candidate is dropped early, the best one that reaches H1 becomes the incumbent.
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))

import core  # noqa: E402
import sprt  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


# ---- the test itself -----------------------------------------------------------------------

def test_bounds_follow_alpha_and_beta():
    low, high = sprt.bounds(0.05, 0.05)
    assert high == pytest.approx(math.log(0.95 / 0.05)) and low == pytest.approx(math.log(0.05 / 0.95))


def stats_of(diffs):
    s = sprt.Stats()
    for d in diffs:
        s.add(d)
    return s


def test_a_clear_gain_is_accepted_early():
    # Given a candidate that wins every other contested matchup (+25 points on average)
    diffs = [1.0, 0.0, 0.0, 0.0] * 40
    verdict = sprt.decide(stats_of(diffs), mu0=0.0, mu1=0.02, alpha=0.05, beta=0.05, min_n=50)
    assert verdict == 'H1'


def test_no_gain_is_rejected_and_a_loss_too():
    # Paired matchups mostly end the same for both versions (Lab, 13 October 2026: standard
    # deviation about 0.25 per matchup), so a neutral change shows rare +1/-1 differences.
    neutral = ([1.0, -1.0] + [0.0] * 28) * 50                      # 1,500 matchups, mean 0
    worse = ([-1.0] + [0.0] * 9) * 30                              # -10 points
    assert sprt.decide(stats_of(neutral), 0.0, 0.02, 0.05, 0.05, 50) == 'H0'
    assert sprt.decide(stats_of(worse), 0.0, 0.02, 0.05, 0.05, 50) == 'H0'


def test_too_few_matchups_never_decide():
    assert sprt.decide(stats_of([1.0] * 10), 0.0, 0.02, 0.05, 0.05, 50) is None


def test_a_small_unclear_effect_keeps_playing():
    unclear = [1.0, -1.0, 0.0, 0.0, 0.5] * 30                      # +10 points over 150, very noisy
    assert sprt.decide(stats_of(unclear), 0.0, 0.02, 0.05, 0.05, 50) in (None, 'H1')


# ---- job kind 'ab' -------------------------------------------------------------------------

def ab_params(**over):
    p = dict(source='player', profile='hard', base_policy=SCENE, base_decks='balanced', policy=SCENE,
             npc_decks='balanced:spyval', seeds=[1401], batch=40, max_tasks=400,
             sprt=dict(mu0=0.0, mu1=0.02, alpha=0.05, beta=0.05, min_n=40))
    p.update(over)
    return p


def test_ab_job_queues_paired_batches():
    tasks = core.ab_payloads(ab_params())
    assert len(tasks) == 40 and all(t['kind'] == 'ab-eval' for t in tasks)
    assert all(t['policy'] == SCENE and t['npc_decks'] == 'balanced:spyval' and t['base_decks'] == 'balanced'
               for t in tasks)
    assert len({(t['pair'], t['seed'], t['swap']) for t in tasks}) == 40


def run_ab(db, params, outcome):
    jid = core.create_job(db, 't', 'ab', params)                    # as the Lab queues a job
    for _ in range(50):
        for tid, payload in db.execute("SELECT id, payload FROM tasks WHERE job_id=? AND status='pending'", (jid,)).fetchall():
            n = db.execute("SELECT COUNT(*) FROM tasks WHERE job_id=? AND status='done'", (jid,)).fetchone()[0]
            db.execute("UPDATE tasks SET status='done', result=? WHERE id=?", (json.dumps(outcome(n)), tid))
        core.ab_step(db)
        status = db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0]
        if status != 'active':
            break
    return json.loads(db.execute("SELECT params FROM jobs WHERE id=?", (jid,)).fetchone()[0]), status


def test_ab_job_stops_when_the_answer_is_clear():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    # Given a candidate that wins every fourth matchup the base loses
    params, status = run_ab(db, ab_params(), lambda n: dict(candidate=1.0 if n % 4 == 0 else 0.5, base=0.5))
    # Then the job stops long before max_tasks with the verdict "better"
    assert status == 'done' and params['verdict']['result'] == 'better'
    assert params['verdict']['n'] < 400


def test_ab_job_gives_up_at_the_budget_when_unclear():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    flip = lambda n: dict(candidate=1.0 if n % 2 else 0.0, base=0.5)
    params, status = run_ab(db, ab_params(max_tasks=120, sprt=dict(mu0=0.0, mu1=0.005, alpha=0.05, beta=0.05, min_n=40)), flip)
    assert status == 'done' and params['verdict']['n'] == 120
    assert params['verdict']['result'] in ('undecided', 'not better')


def test_ab_eval_plays_both_arms_on_one_matchup():
    task = core.ab_payloads(ab_params(batch=1))[0]
    same = core.run_payload(dict(task, npc_decks=task['base_decks'], policy=task['base_policy']))
    assert set(same) == {'candidate', 'base'} and same['candidate'] == same['base']


# ---- deck tuner race -----------------------------------------------------------------------

def tune_params(**over):
    p = dict(npc_decks='balanced', profile='hard', policy=SCENE, seed_base=11, candidates=3, batch=30,
             max_per_candidate=300, sprt=dict(mu0=0.0, mu1=0.02, alpha=0.05, beta=0.05, min_n=30))
    p.update(over)
    return p


def test_race_starts_several_candidates():
    tasks = core.deck_tune_payloads(tune_params())
    ids = {t['candidate_id'] for t in tasks}
    assert ids == {0, 1, 2} and len(tasks) == 3 * 30
    assert len({json.dumps(t['candidate'], sort_keys=True) for t in tasks}) == 3


def race(db, params, outcome):
    jid = core.create_job(db, 't', 'deck-tune', params)
    for _ in range(40):
        rows = db.execute("SELECT id, payload FROM tasks WHERE job_id=? AND status='pending'", (jid,)).fetchall()
        for tid, payload in rows:
            p = json.loads(payload)
            db.execute("UPDATE tasks SET status='done', result=? WHERE id=?", (json.dumps(outcome(p, tid)), tid))
        core.deck_tune_step(db)
        stored = json.loads(db.execute("SELECT params FROM jobs WHERE id=?", (jid,)).fetchone()[0])
        if stored['iteration'] >= 1:
            return stored
    raise AssertionError('race never ended')


def test_race_accepts_the_clearly_better_candidate_and_drops_the_rest():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    # candidate 1 wins every other matchup; the others are equal to the incumbent
    out = lambda p, tid: dict(candidate=1.0 if p['candidate_id'] == 1 and tid % 2 else 0.5, incumbent=0.5)
    stored = race(db, tune_params(), out)
    step = stored['history'][0]
    assert step['accepted'] and stored['genome'] == step['candidate'] and step['candidate_id'] == 1


def test_race_keeps_the_incumbent_when_nothing_is_better():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(core.SCHEMA)
    out = lambda p, tid: dict(candidate=0.0 if tid % 3 == 0 else 0.5, incumbent=0.5)    # all worse
    stored = race(db, tune_params(), out)
    assert not stored['history'][0]['accepted'] and stored['genome'] == {}
    # each candidate was dropped early, far below its budget
    used = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    assert used < 3 * 300


def test_ab_candidate_can_carry_tuned_weights():
    # Given an 'ab' job whose candidate carries utility weights (e.g. from Texel's method)
    from gwentsim.tuning import DEFAULTS
    params = ab_params(npc_decks='balanced', batch=1, weights=dict(DEFAULTS))
    task = core.ab_payloads(params)[0]
    assert task['weights'] == DEFAULTS
    # When the weights are the shipped ones, then both arms play the same match
    result = core.run_payload(task)
    assert result['candidate'] == result['base']
    # And the request body keeps them
    body = dict(kind='ab', source='player', seeds=[1], policy=SCENE, base_policy=SCENE, weights={'reserve_weight': 0.3})
    assert core.job_params('ab', body)['weights'] == {'reserve_weight': 0.3}
