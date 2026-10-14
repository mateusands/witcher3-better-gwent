"""Texel run on the Lab server (lab/remote/texel_run.sh).

Spec (owner, 13 October 2026): the Texel collection must not slow the Lab down more than needed.
On 13 October 2026 it ran with the system CPython at nice 10 while the Lab workers run PyPy at
nice 15, so it took CPU first and ran about 1.7x slower than it could.
- Collect and fit use the Lab's worker interpreter (PyPy, path in /srv/gwentailab/pypy_path),
  falling back to python3 when that file is missing.
- Both run at the workers' nice level (15), so they share the CPU evenly with the Lab.
- After the fit, paired SPRT A/B jobs of the fitted weights are queued for balanced and strong.

Given the script, when it is read, then it uses the worker interpreter and the workers' priority
for every heavy step and queues the two A/B jobs.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'lab/remote/texel_run.sh'
sys.path.insert(0, str(ROOT / 'sim'))


def text():
    return SCRIPT.read_text()


def heavy_lines(source):
    return [line for line in source.splitlines() if 'texel_tune.py' in line and not line.lstrip().startswith('#')]


def test_heavy_steps_use_the_worker_interpreter_and_priority():
    source = text()
    assert '/srv/gwentailab/pypy_path' in source and 'python3' in source      # fallback
    steps = heavy_lines(source)
    assert any(' collect ' in s for s in steps) and any(' fit ' in s for s in steps)
    for step in steps:
        assert re.search(r'nice -n %d "\$PY" sim/texel_tune\.py' % 15, step), step
    assert 'os.nice(15)' in (ROOT / 'lab/core.py').read_text()                 # the workers' level


def test_fitted_weights_are_queued_as_paired_ab_jobs():
    source = text()
    assert "kind='ab'" in source and "weights=weights" in source
    assert "'balanced'" in source and "'strong'" in source
    assert source.index(' fit ') < source.index("kind='ab'")
