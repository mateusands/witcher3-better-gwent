#!/usr/bin/env python3
"""Crash/resume validation: hard-kill workers repeatedly and require identical results.

Runs a small benchmark twice under the data root (HDD): once uninterrupted (reference) and
once with workers killed by SIGKILL at random moments and restarted after a fresh init()
(the same as a power cut and a program restart). Every task result must match the
reference and the SQLite file must pass integrity_check.
"""
import json
import multiprocessing as mp
import os
import random
import shutil
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

PARAMS = dict(source='pool', policy='response-v8', profile='easy', seeds=[900], pairs=30)


def fresh_root(base, name):
    root = base / name
    shutil.rmtree(root, ignore_errors=True)
    (root / 'db').mkdir(parents=True)
    (root / core.MARKER).write_text('selftest\n')
    return root


def results(root):
    db = core.connect(root)
    return {idx: json.loads(r) if r else None for idx, r in
            db.execute("SELECT idx, result FROM tasks ORDER BY idx")}, db


def main(kills=10, workers=4):
    base = core.data_root() / 'selftest'
    base.mkdir(exist_ok=True)
    ref_root = fresh_root(base, 'reference')
    db = core.init(ref_root); core.create_job(db, 'reference', 'benchmark', PARAMS); db.close()
    t0 = time.time(); core.worker_main(ref_root, stop_when_empty=True)
    reference, _ = results(ref_root)
    print('reference: %d tasks in %.1fs' % (len(reference), time.time() - t0))

    chaos_root = fresh_root(base, 'chaos')
    db = core.init(chaos_root); core.create_job(db, 'chaos', 'benchmark', PARAMS); db.close()
    rng = random.Random(1234); killed = 0
    while True:
        db = core.init(chaos_root)  # restart: running -> pending
        pending = db.execute("SELECT COUNT(*) FROM tasks WHERE status!='done'").fetchone()[0]
        db.close()
        if pending == 0:
            break
        procs = [mp.Process(target=core.worker_main, args=(str(chaos_root), True)) for _ in range(workers)]
        for p in procs:
            p.start()
        if killed < kills:
            time.sleep(rng.uniform(0.3, 4.0))
            for p in procs:
                if p.is_alive():
                    os.kill(p.pid, signal.SIGKILL)
            killed += 1
        for p in procs:
            p.join()
    chaos, db = results(chaos_root)
    integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    errors = db.execute("SELECT COUNT(*) FROM tasks WHERE status='error'").fetchone()[0]
    same = chaos == reference
    print('chaos: %d hard kills, integrity=%s, errors=%d, identical=%s' % (killed, integrity, errors, same))
    return 0 if same and integrity == 'ok' and errors == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
