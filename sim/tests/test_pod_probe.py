"""When a rented server's battery is finished (lab/remote/pod_probe.py, used by pod.sh wait).

Spec (owner, 13 October 2026): pod.sh wait pulls the database once every job has no work left.
- A benchmark job stays 'active' when its tasks are all done or failed: it is finished then.
- A sequential job (kind 'ab' or 'deck-tune') queues its next batch only after the last one, so
  it is never finished while 'active'; it becomes 'done' (or 'superseded') when it decides.
- Jobs that are 'done', 'superseded' or 'paused' have no work left.
The former probe only summed active jobs, so a battery of 'ab' jobs, which all leave the active
list, never looked finished.

Given the Lab status, when the probe counts the work left, then a battery of decided 'ab' jobs
is finished and an 'ab' job between batches is not.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab' / 'remote'))
sys.path.insert(0, str(ROOT / 'sim'))

import pod_probe  # noqa: E402


def job(kind, status, done, total, errors=0):
    return dict(kind=kind, status=status, done=done, total=total, errors=errors)


def test_decided_sequential_jobs_are_finished():
    jobs = [job('ab', 'done', 400, 400), job('ab', 'done', 1200, 1200)]
    assert pod_probe.work_left(jobs) == 0 and pod_probe.done(jobs) == 1600


def test_a_sequential_job_between_batches_is_not_finished():
    assert pod_probe.work_left([job('ab', 'active', 200, 200)]) > 0
    assert pod_probe.work_left([job('deck-tune', 'active', 60, 60)]) > 0


def test_benchmarks_finish_when_their_tasks_are_done_or_failed():
    assert pod_probe.work_left([job('benchmark', 'active', 90, 100, errors=10)]) == 0
    assert pod_probe.work_left([job('benchmark', 'active', 50, 100)]) == 50
    assert pod_probe.work_left([job('benchmark', 'paused', 0, 100)]) == 0
