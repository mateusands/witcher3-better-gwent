"""Gwent AI Lab core: crash-safe job store, low-priority workers, resource guards.

All data lives under the data root (default /mnt/hdd/GwentAILab), never on the system disk:
the root must contain the marker file, otherwise nothing starts (the HDD is mounted with
`nofail`, so a missing mount must not silently fall back to the NVMe).

Crash safety: every finished task is written in the SAME SQLite transaction that marks it
done (journal WAL, synchronous FULL). Tasks left "running" by a crash or power cut go back
to "pending" at the next start. Each task is fully described by its payload (record/pair,
seed, swap, policy, profile), so re-running it produces the identical result.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'sim'
DEFAULT_DATA = Path(os.environ.get('GWENT_LAB_DATA', '/mnt/hdd/GwentAILab'))
MARKER = '.gwent_ai_lab_root'
PROFILES = ['easy', 'medium', 'hard', 'expert']


class LabError(RuntimeError):
    pass


def data_root(path=None):
    root = Path(path or DEFAULT_DATA)
    if not (root / MARKER).is_file():
        raise LabError('data root %s has no %s marker (is the HDD mounted?)' % (root, MARKER))
    return root


def connect(root):
    db = sqlite3.connect(str(root / 'db' / 'lab.sqlite3'), timeout=60, isolation_level=None, check_same_thread=False)
    for pragma in ('journal_mode=WAL', 'synchronous=FULL', 'busy_timeout=60000'):
        db.execute('PRAGMA ' + pragma).fetchall()   # read fully: PyPy keeps unread statements open
    return db


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, params TEXT NOT NULL,
  created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, idx INTEGER NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', result TEXT, error TEXT, worker INTEGER,
  started REAL, finished REAL, UNIQUE(job_id, idx));
CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, id);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

DEFAULT_SETTINGS = {
    'workers': 4,              # cores used while I keep using the PC
    'paused': True,            # the PC always starts paused; press Resume
    'autoresume': False,       # True on the headless server
    'pause_on_processes': ['witcher3.exe'],
    'disk_cap_gb': 50,
    'worker_python': '',       # interpreter for workers ('' = same as the panel); PyPy is ~1.7x faster
}


def init(root):
    db = connect(root)
    db.executescript(SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', (key, json.dumps(value)))
    # Crash recovery: whatever was running when the process died is simply redone.
    db.execute("UPDATE tasks SET status='pending', worker=NULL, started=NULL WHERE status='running'")
    if not get(db, 'autoresume'):
        set_(db, 'paused', True)
    return db


def one(db, sql, args=()):
    """First row or None. Reads the whole result so no statement stays open: PyPy's sqlite3
    refuses COMMIT while a half-read SELECT is still active."""
    rows = db.execute(sql, args).fetchall()
    return rows[0] if rows else None


def get(db, key):
    row = one(db, 'SELECT value FROM settings WHERE key=?', (key,))
    return json.loads(row[0]) if row else DEFAULT_SETTINGS.get(key)


def set_(db, key, value):
    db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (key, json.dumps(value)))


# ---- Jobs -------------------------------------------------------------------

def benchmark_payloads(params):
    """Expand a benchmark into independent deterministic task payloads."""
    policy, profile, seeds = params['policy'], params['profile'], params['seeds']
    weights = params.get('weights')
    out = []
    if params['source'] == 'player':
        sys.path.insert(0, str(SIM))
        from evaluate_pool import player_setup
        pool = player_setup()
        pairs = len(pool)
        only_recorded = params.get('player_filter') == 'recorded'   # my own real decks only
        for pair in range(min(pairs, params.get('pairs') or pairs)):
            if only_recorded and not pool[pair][1].name.startswith('recorded/'):
                continue
            for seed in seeds:
                for swap in (False, True):
                    out.append(dict(source='player', pair=pair, seed=seed, swap=swap, policy=policy, profile=profile,
                                    **({'weights': weights} if weights else {}),
                                    **({'npc_decks': params['npc_decks']} if params.get('npc_decks') else {})))
    elif params['source'] == 'pool':
        sys.path.insert(0, str(SIM))
        from evaluate_pool import setup
        pairs = len(setup()['pairs'])
        for pair in range(min(pairs, params.get('pairs') or pairs)):
            for seed in seeds:
                for swap in (False, True):
                    out.append(dict(source='pool', pair=pair, seed=seed, swap=swap, policy=policy, profile=profile,
                                    **({'weights': weights} if weights else {})))
    else:
        records = sorted(str(p) for p in (ROOT / 'game/records').glob('g[0-9][0-9][0-9].json')
                         if p.name in set(params['records']))
        for path in records:
            for seed in seeds:
                for swap in (False, True):
                    out.append(dict(source='records', record=path, seed=seed, swap=swap, policy=policy, profile=profile))
    return out


def hunt_payloads(params):
    """Blunder hunt: the candidate plays each pool pair from both seats; losses get replayed.
    Source 'player': the candidate plays the NPC side against a player-style deck."""
    sys.path.insert(0, str(SIM))
    if params['source'] == 'player':
        from evaluate_pool import player_setup
        pool = player_setup()
        pairs = len(pool)
        only_recorded = params.get('player_filter') == 'recorded'   # my own real decks only
        swaps = (False,) if params.get('game_seat') else (False, True)  # NPC in seat 1, as in the game
        return [dict(kind='hunt', source='player', pair=pair, seed=seed, swap=swap, seat=0 if swap else 1,
                     policy=params['policy'], profile=params['profile'],
                     **({'npc_decks': params['npc_decks']} if params.get('npc_decks') else {}))
                for pair in range(min(pairs, params.get('pairs') or pairs))
                if not only_recorded or pool[pair][1].name.startswith('recorded/')
                for seed in params['seeds'] for swap in swaps]
    from evaluate_pool import setup
    pairs = len(setup()['pairs'])
    return [dict(kind='hunt', source='pool', pair=pair, seed=seed, swap=False, seat=seat,
                 policy=params['policy'], profile=params['profile'])
            for pair in range(min(pairs, params.get('pairs') or pairs))
            for seed in params['seeds'] for seat in (0, 1)]


def deep_hunt_payloads(params):
    """Deep hunt: same matches as a hunt, analysed with blunder_hunter.deep_hunt."""
    return [dict(p, kind='deep-hunt') for p in hunt_payloads(params)]


TUNE_DEFAULTS = dict(iterations=30, pool=32, player=32, a=0.4, c=0.1, A=5, alpha=0.602, gamma=0.101,
                     low=0.25, high=4.0, seed_base=7000)


def _tune_iteration(params):
    """Tasks for SPSA iteration k: theta +/- c_k * delta on the same matchups and luck."""
    import random
    sys.path.insert(0, str(SIM))
    from gwentsim.tuning import DEFAULTS
    from evaluate_pool import setup, player_setup
    k = params['iteration']
    names = sorted(DEFAULTS)
    rng = random.Random('%d/%d' % (params['seed_base'], k))
    delta = {n: rng.choice((-1, 1)) for n in names}
    ck = params['c'] / (k + 1) ** params['gamma']
    params['delta'] = delta
    thetas = {}
    for sign in (1, -1):
        thetas[sign] = {n: DEFAULTS[n] * min(params['high'], max(params['low'], params['x'][n] + sign * ck * delta[n]))
                        for n in names}
    pool = rng.sample(range(len(setup()['pairs'])), params['pool'])
    player = rng.sample(range(len(player_setup())), params['player'])
    out = []
    for sign in (1, -1):
        for pair in pool:
            out.append(dict(kind='tune-eval', source='pool', pair=pair, seed=params['seed_base'] + k * 1000 + pair,
                            swap=bool(pair % 2), profile=params['profile'], policy='response-v8',
                            params=thetas[sign], iteration=k, sign=sign))
        for pair in player:
            out.append(dict(kind='tune-eval', source='player', pair=pair, seed=params['seed_base'] + k * 1000 + pair,
                            swap=bool(pair % 2), profile=params['profile'], policy='response-v8',
                            params=thetas[sign], iteration=k, sign=sign))
    return out


def tune_payloads(params):
    """Phase 3: SPSA tuning of the V8 utility weights (gwentsim.tuning), x = weight / default."""
    sys.path.insert(0, str(SIM))
    from gwentsim.tuning import DEFAULTS
    for key, value in TUNE_DEFAULTS.items():
        params.setdefault(key, value)
    params.setdefault('profile', 'hard')
    params.setdefault('x', {n: 1.0 for n in DEFAULTS})
    params.setdefault('iteration', 0)
    params.setdefault('history', [])
    return _tune_iteration(params)


def tune_step(db):
    """When every task of the current iteration is done, update x and queue the next one.
    One transaction: a crash can never apply an iteration twice."""
    stepped = []
    for jid, params in db.execute("SELECT id, params FROM jobs WHERE kind='tune' AND status='active'").fetchall():
        db.execute('BEGIN IMMEDIATE')
        try:
            params = json.loads(params)
            k = params['iteration']
            if params.get('finished') or one(db, "SELECT COUNT(*) FROM tasks WHERE job_id=? AND status IN ('pending','running')", (jid,))[0]:
                db.execute('COMMIT'); continue
            f = {1: [0.0, 0], -1: [0.0, 0]}
            for payload, result in db.execute("SELECT payload, result FROM tasks WHERE job_id=? AND status='done'", (jid,)).fetchall():
                p = json.loads(payload)
                if p['iteration'] == k:
                    r = json.loads(result)
                    f[p['sign']][0] += r['score']; f[p['sign']][1] += r['games']
            if not f[1][1] or not f[-1][1]:
                db.execute('COMMIT'); continue
            fp, fm = f[1][0] / f[1][1], f[-1][0] / f[-1][1]
            ck = params['c'] / (k + 1) ** params['gamma']
            ak = params['a'] / (k + 1 + params['A']) ** params['alpha']
            for n, d in params['delta'].items():
                g = (fp - fm) / (2 * ck * d)
                params['x'][n] = min(params['high'], max(params['low'], params['x'][n] + ak * g))
            params['history'].append(dict(iteration=k, plus=fp, minus=fm, games=f[1][1] + f[-1][1],
                                           x=dict(params['x'])))
            params['iteration'] = k + 1
            if params['iteration'] >= params['iterations']:
                params['finished'] = True
            else:
                start = one(db, 'SELECT COALESCE(MAX(idx)+1, 0) FROM tasks WHERE job_id=?', (jid,))[0]
                add_tasks(db, jid, _tune_iteration(params), start)
            db.execute('UPDATE jobs SET params=? WHERE id=?', (json.dumps(params), jid))
            db.execute('COMMIT')
            stepped.append((jid, k, fp, fm))
        except BaseException:
            db.execute('ROLLBACK')
            raise
    return stepped


PAYLOADS = {'benchmark': benchmark_payloads, 'hunt': hunt_payloads, 'deep-hunt': deep_hunt_payloads,
            'tune': tune_payloads}
HUNTS = ('hunt', 'deep-hunt')


def add_tasks(db, job, payloads, start=0):
    db.executemany('INSERT INTO tasks(job_id,idx,payload) VALUES(?,?,?)',
                   [(job, start + i, json.dumps(p, sort_keys=True)) for i, p in enumerate(payloads)])


def create_job(db, name, kind, params):
    """params['continuous']=True: when the queue runs dry, refill() adds the next seed."""
    if kind not in PAYLOADS:
        raise LabError('unknown job kind %s' % kind)
    payloads = PAYLOADS[kind](params)
    db.execute('BEGIN IMMEDIATE')
    try:
        job = db.execute('INSERT INTO jobs(name,kind,params,created) VALUES(?,?,?,?)',
                         (name, kind, json.dumps(params), time.time())).lastrowid
        add_tasks(db, job, payloads)
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
    return job


def refill(db):
    """Continuous jobs: once every task is finished, queue the same work with a new seed.

    Seeds only grow (max used + 1), and the check + insert is one transaction, so a crash
    or two managers can never queue a seed twice."""
    added = []
    for jid, kind, params in db.execute(
            "SELECT id, kind, params FROM jobs WHERE status='active'").fetchall():
        params = json.loads(params)
        if not params.get('continuous'):
            continue
        db.execute('BEGIN IMMEDIATE')
        try:
            busy = one(db, "SELECT COUNT(*) FROM tasks WHERE job_id=? AND status IN ('pending','running')",
                       (jid,))[0]
            if busy:
                db.execute('COMMIT'); continue
            params['seeds'] = [max(params['seeds']) + 1]
            start = one(db, 'SELECT COALESCE(MAX(idx)+1, 0) FROM tasks WHERE job_id=?', (jid,))[0]
            add_tasks(db, jid, PAYLOADS[kind](params), start)
            stored = json.loads(one(db, 'SELECT params FROM jobs WHERE id=?', (jid,))[0])
            stored['seeds'] = stored['seeds'] + params['seeds']
            db.execute('UPDATE jobs SET params=? WHERE id=?', (json.dumps(stored), jid))
            db.execute('COMMIT')
            added.append((jid, params['seeds'][0]))
        except BaseException:
            db.execute('ROLLBACK')
            raise
    return added


# ---- Work -------------------------------------------------------------------

def run_payload(payload):
    """One group: native baseline plus the candidate in each seat. Compact summary only.

    Policy "response-v8:a+b" runs response-v8 with experiment switches a and b (A/B tests)."""
    sys.path.insert(0, str(SIM))
    policy, _, flags = payload.get('policy', 'response-v8').partition(':')
    import gwentsim.response_v8 as v8
    v8.VARIANT = frozenset(f for f in flags.split('+') if f)
    payload = dict(payload, policy=policy)
    if payload.get('weights') and payload.get('kind') not in ('tune-eval',):
        return _with_weights(payload)
    if payload.get('kind') == 'tune-eval':
        return tune_eval(payload)
    if payload.get('kind') in HUNTS:
        import blunder_hunter
        report = (blunder_hunter.deep_hunt if payload['kind'] == 'deep-hunt' else blunder_hunter.hunt)(payload)
        return dict(score=report['score'], decisions=report['decisions'], replays=report['replays'],
                    rounds=report['result']['rounds'], decks=report['result']['decks'],
                    findings=report['findings'], skipped=len(report.get('skipped', [])))
    profile = payload['profile'] if isinstance(payload['profile'], int) else PROFILES.index(payload['profile'])
    if payload['source'] == 'player':
        from evaluate_pool import group_player
        trials, error = group_player((payload['pair'], payload['seed'], payload['swap'], payload['policy'], profile,
                                      payload.get('npc_decks')))
        if error:
            raise LabError(json.dumps(error))
        base, cand = trials
        return dict(baselineWinner=base['winner'], seats=[dict(seat=cand['npcSeat'], winner=cand['winner'],
                                                                won=cand['winner'] == cand['npcSeat'])])
    if payload['source'] == 'pool':
        from evaluate_pool import group
        trials, error = group((payload['pair'], payload['seed'], payload['swap'], payload['policy'], profile))
    else:
        from evaluate import trial_group
        trials, error = trial_group((payload['record'], payload['seed'], payload['swap'], True, payload['policy'], profile))
    if error:
        raise LabError(json.dumps(error))
    base = next(t for t in trials if 'candidatePlayer' not in t)
    out = dict(baselineWinner=base['winner'], seats=[])
    for t in trials:
        if 'candidatePlayer' in t:
            out['seats'].append(dict(seat=t['candidatePlayer'], winner=t['winner'], won=t['candidateWon']))
    return out


def _with_weights(payload):
    """Benchmark group with tuned weights on the candidate side only (NPC side for player decks)."""
    from gwentsim import tuning
    from evaluate_pool import player_seats
    weights = payload.pop('weights')
    seats = (0, 1) if payload['source'] == 'pool' else (player_seats(payload['pair'], payload['swap'])[1],)
    tuning.SEAT_PARAMS.clear()
    tuning.SEAT_PARAMS.update({seat: weights for seat in seats})
    try:
        return run_payload(payload)
    finally:
        tuning.SEAT_PARAMS.clear(); tuning.reset()


def tune_eval(payload):
    """Score of the tuned V8 (its weights on the candidate/NPC seat only) on one matchup."""
    from gwentsim import tuning
    profile = PROFILES.index(payload['profile'])
    score = games = 0.0
    try:
        if payload['source'] == 'pool':
            from evaluate_pool import run
            for seat in (0, 1):
                tuning.SEAT_PARAMS.clear(); tuning.SEAT_PARAMS[seat] = payload['params']
                r = run(payload['pair'], payload['seed'], payload['swap'], seat, 'response-v8', profile)
                score += 1.0 if r['candidateWon'] else 0.5 if r['winner'] not in (0, 1) else 0.0
                games += 1
        else:
            from evaluate_pool import player_seats, run_player
            _, npc = player_seats(payload['pair'], payload['swap'])
            tuning.SEAT_PARAMS.clear(); tuning.SEAT_PARAMS[npc] = payload['params']
            r = run_player(payload['pair'], payload['seed'], payload['swap'], 'response-v8', profile)
            score += 1.0 if r['winner'] == npc else 0.5 if r['winner'] not in (0, 1) else 0.0
            games += 1
    finally:
        tuning.SEAT_PARAMS.clear(); tuning.reset()
    return dict(score=score, games=games)


def claim(db, worker):
    db.execute('BEGIN IMMEDIATE')
    try:
        # Fair share: the active job with pending work and the fewest running tasks goes next,
        # so several jobs advance side by side instead of one after the other.
        job = one(db, "SELECT j.id FROM jobs j WHERE j.status='active' AND EXISTS "
                      "(SELECT 1 FROM tasks p WHERE p.job_id=j.id AND p.status='pending') "
                      "ORDER BY (SELECT COUNT(*) FROM tasks r WHERE r.job_id=j.id AND r.status='running'), j.id LIMIT 1")
        row = job and one(db, "SELECT id, payload FROM tasks WHERE job_id=? AND status='pending' ORDER BY id LIMIT 1",
                          (job[0],))
        if row:
            db.execute("UPDATE tasks SET status='running', worker=?, started=? WHERE id=?", (worker, time.time(), row[0]))
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
    return row


def finish(db, task, result=None, error=None):
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("UPDATE tasks SET status=?, result=?, error=?, finished=? WHERE id=? AND status='running'",
                   ('error' if error else 'done', json.dumps(result) if result is not None else None,
                    error, time.time(), task))
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise


def die_with_parent():
    """Exit as soon as the panel process is gone, so no orphan keeps the CPU busy after a
    crash of the panel. (PR_SET_PDEATHSIG would follow the launching *thread*, and the
    panel starts workers from short-lived request threads.)"""
    import threading
    parent = os.getppid()

    def watch():
        while True:
            time.sleep(3)
            if os.getppid() != parent:
                os._exit(0)
    threading.Thread(target=watch, daemon=True).start()


def worker_main(root, stop_when_empty=False):
    """Worker process loop. Runs at low priority; may be killed at any moment."""
    try:
        os.nice(15)
    except OSError:
        pass
    db = connect(Path(root))
    pid = os.getpid()
    while True:
        row = claim(db, pid)
        if row is None:
            if stop_when_empty:
                return
            time.sleep(2)
            continue
        task, payload = row
        try:
            result = run_payload(json.loads(payload))
            finish(db, task, result=result)
        except Exception as exc:  # recorded, visible in the panel; never silently dropped
            finish(db, task, error='%s: %s' % (type(exc).__name__, exc))


# ---- Reporting --------------------------------------------------------------

def score(won, winner):
    return 1.0 if won else 0.5 if winner not in (0, 1) else 0.0


def job_summary(db, job, max_findings=30):
    jid, name, kind, params, created, status = job
    counts = dict(db.execute('SELECT status, COUNT(*) FROM tasks WHERE job_id=? GROUP BY status', (jid,)).fetchall())
    total = sum(counts.values())
    cand = native = matches = 0.0
    durations = []
    findings = []; losses = 0
    for result, started, finished, payload in db.execute(
            "SELECT result, started, finished, payload FROM tasks WHERE job_id=? AND status='done' ORDER BY id", (jid,)):
        r = json.loads(result)
        if started and finished:
            durations.append(finished - started)
        if kind == 'tune':
            matches += r['games']
            continue
        if kind in HUNTS:
            cand += r['score']; matches += 1; losses += r['score'] < 1
            p = json.loads(payload)
            for f in r['findings']:
                findings.append(dict(f, pair=p['pair'], seed=p['seed'], seat=p['seat'], decks=r['decks']))
            continue
        for s in r['seats']:
            cand += score(s['won'], s['winner'])
            native += score(r['baselineWinner'] == s['seat'], r['baselineWinner'])
            matches += 1
        if started and finished:
            durations.append(finished - started)
    # Running tasks count with their elapsed time so far: a hunt job finishes fast wins first,
    # and an average of those alone would promise minutes for hours of lost-match replays.
    now = time.time()
    durations += [now - s for (s,) in db.execute(
        "SELECT started FROM tasks WHERE job_id=? AND status='running' AND started IS NOT NULL", (jid,))]
    errors = [e for (e,) in db.execute("SELECT error FROM tasks WHERE job_id=? AND status='error' LIMIT 5", (jid,))]
    findings.sort(key=lambda f: -f['regret'])
    return dict(id=jid, name=name, kind=kind, params=json.loads(params), status=status, total=total,
                findingCount=len(findings), findings=findings[:max_findings], lossesHunted=losses,
                done=counts.get('done', 0), running=counts.get('running', 0), pending=counts.get('pending', 0),
                errors=counts.get('error', 0), errorSamples=errors, matches=int(matches),
                candidateScore=cand, nativeScore=native,
                avgTaskSeconds=(sum(durations) / len(durations)) if durations else None)


def dir_size(path):
    total = 0
    for p in Path(path).rglob('*'):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


if __name__ == '__main__':
    # Worker entry when the panel starts workers under another interpreter (e.g. PyPy):
    #   <python> lab/core.py --worker <data root>
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        die_with_parent()
        worker_main(sys.argv[2])
