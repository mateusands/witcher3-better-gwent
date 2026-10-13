"""Releasing queued Lab jobs when a priority batch ends (lab/remote/release_after.py).

Spec: while some jobs run with priority, others wait paused; once every awaited job has no
work left (done, failed or superseded), the waiting jobs are set active. A job id the Lab does
not know is a mistake and must never count as finished.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab' / 'remote'))

import release_after  # noqa: E402


def job(jid, done, total, errors=0, status='active'):
    return dict(id=jid, done=done, total=total, errors=errors, status=status)


def test_waits_while_work_is_left():
    # Given an awaited job with 100 tasks left, then the batch is not finished
    assert not release_after.finished([job(13, 2000, 2100), job(14, 2100, 2100)], {13, 14})


def test_finished_when_done_or_failed():
    # Given awaited jobs whose tasks are all done or failed, then the batch is finished
    assert release_after.finished([job(13, 2098, 2100, errors=2), job(14, 2100, 2100)], {13, 14})


def test_superseded_job_counts_as_finished():
    # Given an awaited job that was superseded half-way, then it no longer blocks the release
    assert release_after.finished([job(13, 500, 2100, status='superseded'), job(14, 2100, 2100)], {13, 14})


def test_unknown_job_is_an_error_not_finished():
    # Given an awaited id the Lab does not list, then it raises instead of releasing everything
    with pytest.raises(KeyError):
        release_after.finished([job(13, 2100, 2100)], {13, 99})


def test_release_sets_each_job_active(monkeypatch):
    # Given jobs to release, when the batch ends, then each is set active through the Lab API
    calls = []
    monkeypatch.setattr(release_after, 'post', lambda path, body: calls.append((path, body)))
    release_after.release([3, 5, 16])
    assert calls == [('job/status', {'id': j, 'status': 'active'}) for j in (3, 5, 16)]
