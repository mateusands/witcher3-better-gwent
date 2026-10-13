"""Pulling the Lab database from rented servers (lab/remote/gcp_pull.sh, lab/remote/pulldb.sh).

Spec (gcp_pull.sh): copy a consistent snapshot of the VM's database to a local file, only when
the VM runs; a corrupt copy never replaces the last good one and leaves no partial files; two
pulls at the same time never overlap. Spec (pulldb.sh): when the server cannot prepare the
snapshot, stop with a clear error instead of writing an empty database.
gcloud and ssh are replaced by small fakes; nothing leaves the machine.
"""
import gzip
import os
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / 'lab' / 'remote'

FAKE_GCLOUD = """#!/bin/bash
case "$*" in
  *"instances describe"*) echo "$FAKE_STATUS";;
  *"compute ssh"*) exit 0;;
  *"compute scp"*) for last; do :; done; cp "$FAKE_SNAPSHOT" "$last";;
esac
"""


def make_db(path, value):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE t(v TEXT)"); db.execute("INSERT INTO t VALUES (?)", (value,)); db.commit(); db.close()


def run_pull(tmp_path, status, snapshot_bytes, lock=None):
    bin_dir = tmp_path / 'bin'; bin_dir.mkdir(exist_ok=True)
    (bin_dir / 'gcloud').write_text(FAKE_GCLOUD); (bin_dir / 'gcloud').chmod(0o755)
    snap = tmp_path / 'snap.gz'; snap.write_bytes(snapshot_bytes)
    env = dict(os.environ, PATH='%s:%s' % (bin_dir, os.environ['PATH']), FAKE_STATUS=status,
               FAKE_SNAPSHOT=str(snap), GWENT_PULL_LOCK=str(lock or tmp_path / 'pull.lock'))
    return subprocess.run(['bash', str(REMOTE / 'gcp_pull.sh'), str(tmp_path / 'lab.sqlite3')],
                          env=env, capture_output=True, text=True, timeout=60)


def good_snapshot(tmp_path, value):
    make_db(tmp_path / 'src.sqlite3', value)
    return gzip.compress((tmp_path / 'src.sqlite3').read_bytes())


def value(path):
    return sqlite3.connect(path).execute("SELECT v FROM t").fetchone()[0]


def test_stopped_vm_is_a_no_op(tmp_path):
    # Given the VM is stopped, when pulling, then nothing changes and it exits cleanly
    r = run_pull(tmp_path, 'TERMINATED', good_snapshot(tmp_path, 'new'))
    assert r.returncode == 0 and not (tmp_path / 'lab.sqlite3').exists()


def test_good_snapshot_replaces_the_copy(tmp_path):
    # Given a running VM and a good snapshot, when pulling, then the local copy is the snapshot
    make_db(tmp_path / 'lab.sqlite3', 'old')
    r = run_pull(tmp_path, 'RUNNING', good_snapshot(tmp_path, 'new'))
    assert r.returncode == 0 and value(tmp_path / 'lab.sqlite3') == 'new'


def test_corrupt_snapshot_keeps_last_good_copy_and_no_parts(tmp_path):
    # Given a running VM and a corrupt snapshot, when pulling
    make_db(tmp_path / 'lab.sqlite3', 'old')
    r = run_pull(tmp_path, 'RUNNING', gzip.compress(b'not a database' * 100))
    # Then it fails, the last good copy stays, and no partial file is left behind
    assert r.returncode != 0 and value(tmp_path / 'lab.sqlite3') == 'old'
    assert not list(tmp_path.glob('lab.sqlite3*.part'))


def test_concurrent_pull_is_skipped(tmp_path):
    # Given another pull holds the lock, when pulling, then it skips without touching the copy
    lock = tmp_path / 'pull.lock'
    holder = subprocess.Popen(['flock', str(lock), 'sleep', '5'])
    try:
        subprocess.run(['sleep', '0.3'])
        r = run_pull(tmp_path, 'RUNNING', good_snapshot(tmp_path, 'new'), lock=lock)
    finally:
        holder.kill()
    assert r.returncode == 0 and 'already running' in r.stdout and not (tmp_path / 'lab.sqlite3').exists()


def test_pulldb_stops_when_snapshot_not_prepared(tmp_path):
    # Given the server answers nothing to the prepare step (proxy dropped)
    bin_dir = tmp_path / 'bin'; bin_dir.mkdir()
    (bin_dir / 'ssh').write_text('#!/bin/bash\ncat >/dev/null\n'); (bin_dir / 'ssh').chmod(0o755)
    env = dict(os.environ, PATH='%s:%s' % (bin_dir, os.environ['PATH']))
    r = subprocess.run(['bash', str(REMOTE / 'pulldb.sh'), 'pod', str(tmp_path / 'out.sqlite3')],
                       env=env, capture_output=True, text=True, timeout=60)
    # Then it fails with a clear message and writes no database
    assert r.returncode != 0 and 'not prepared' in r.stdout and not (tmp_path / 'out.sqlite3').exists()
