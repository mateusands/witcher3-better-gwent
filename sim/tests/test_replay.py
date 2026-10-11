# Replay tests: every recorded match (game/records/gNNN.json) must replay in the simulator with zero
# divergences, plus static checks of the port (Math.random call-site tags, AS3 line references).
# Run with:  python3 -m pytest sim/tests      or without pytest:  python3 sim/tests/test_replay.py
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(HERE, '..'))

import replay  # noqa: E402  (sim/replay.py)

RECORDS = sorted(glob.glob(os.path.join(ROOT, 'game', 'records', 'g[0-9][0-9][0-9].json')))
PORT = os.path.join(HERE, '..', 'gwentsim', 'gwint')
AS_DIRS = [os.path.join(ROOT, 'game', 'vanilla', 'as', 'scripts', 'red', 'game', 'witcher3', 'menus', 'gwint'),
           os.path.join(ROOT, 'game', 'vanilla', 'as', 'scripts', 'red', 'game', 'witcher3', 'utils')]
TAG_FILES = {'CM': 'CardManager', 'CI': 'CardInstance', 'CL': 'CardLeaderInstance', 'DK': 'GwintDeck',
             'FL': 'GwintGameFlowController', 'AI': 'AIPlayerController'}


def _as_file(name):
    for d in AS_DIRS:
        p = os.path.join(d, name + '.as')
        if os.path.exists(p):
            return p
    raise AssertionError('no AS3 file ' + name)


def test_random_call_sites_cover_every_math_random():
    """Each Math.random() of the decompiled rule classes has exactly one math_random(tag) call
    site in the port, with the recorder's tag (n-th occurrence in the file)."""
    used = {}
    for f in glob.glob(os.path.join(PORT, '*.py')):
        for tag in re.findall(r"math_random\('([A-Z]{2}\d+)'\)", open(f).read()):
            used[tag] = used.get(tag, 0) + 1
        for a, b in re.findall(r"\('(CI\d)', '(CI\d)'\)", open(f).read()):   # scorch blocks take a tag pair
            used[a] = used.get(a, 0) + 1
            used[b] = used.get(b, 0) + 1
        for tag in re.findall(r"tag = '(CL\d)'", open(f).read()):
            used[tag] = used.get(tag, 0) + 1
    expected = set()
    for prefix, cls in TAG_FILES.items():
        n = len(re.findall(r'Math\.random\(\)', open(_as_file(cls)).read()))
        expected |= {'%s%d' % (prefix, i) for i in range(1, n + 1)}
    assert set(used) == expected, (sorted(set(used) - expected), sorted(expected - set(used)))


def test_line_references_point_at_the_ported_function():
    """`# File.as:LINE` right above a def must name the line of that AS3 function."""
    checked = 0
    for f in glob.glob(os.path.join(PORT, '*.py')):
        lines = open(f).read().split('\n')
        for i, line in enumerate(lines):
            m = re.match(r'\s*# (\w+)\.as:(\d+)\s*$', line)
            if not m:
                continue
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith('@'):
                j += 1
            d = re.match(r'\s*def (\w+)', lines[j])
            if not d or d.group(1) == '__init__':
                continue
            name = d.group(1)
            if name.startswith('set_'):
                name = name[4:]
            src = open(_as_file(m.group(1))).read().split('\n')
            target = src[int(m.group(2)) - 1]
            assert re.search(r'function (get |set )?%s\b' % name, target), '%s: %s -> %r' % (os.path.basename(f), line.strip(), target.strip())
            checked += 1
    assert checked > 200


def _check(path):
    m, n, div = replay.replay(path)
    assert div is None, '%s diverges at event %d/%d: %s' % (os.path.basename(path), div.index, len(m.events), div.detail)
    assert n == len(m.events)


def test_replays():
    assert RECORDS, 'no recorded matches in game/records'
    failures = []
    for path in RECORDS:
        try:
            _check(path)
        except AssertionError as exc:
            failures.append(str(exc))
    assert not failures, '\n'.join(failures)


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('ok', name)
