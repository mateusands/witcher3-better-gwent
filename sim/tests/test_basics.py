# Basic tests for the simulator skeleton. Run with:  python3 -m pytest sim/tests
# or without pytest:                                 python3 sim/tests/test_basics.py
import glob, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(HERE, '..'))

from gwentsim import as3, constants as C  # noqa: E402
from gwentsim.data import load_match  # noqa: E402
from gwentsim.rng import ReplayRandom, ReplayMismatch, SeededRandom, rand_index  # noqa: E402
from gwentsim.sort import qsort_sliced, as3_sort  # noqa: E402

RECORDS = sorted(glob.glob(os.path.join(ROOT, 'game', 'records', 'g[0-9][0-9][0-9].json')))
PROBES = os.path.join(ROOT, 'game', 'probes', 'scaleform.json')


def test_as3_int():
    assert as3.to_int(2.9) == 2 and as3.to_int(-2.9) == -2
    assert as3.to_int(2 ** 31) == -2 ** 31 and as3.to_int(2 ** 32 + 5) == 5
    assert as3.to_int(float('nan')) == 0 and as3.to_int(float('inf')) == 0
    assert as3.to_uint(-1) == 4294967295


def test_as3_math():
    assert as3.math_round(-2.5) == -2 and math.copysign(1, as3.math_round(-0.5)) == 1
    assert math.isnan(as3.math_min(1, float('nan'))) and math.isnan(as3.math_max(float('nan'), 1))
    assert math.copysign(1, as3.math_min(0.0, -0.0)) == -1
    assert as3.div(1, 0) == float('inf') and as3.div(-1, 0) == float('-inf') and math.isnan(as3.div(0, 0))
    assert as3.div(7, 2) == 3.5
    assert as3.mod(-7, 3) == -1
    assert as3.floor(-0.5) == -1 and math.isinf(as3.floor(float('inf')))


def test_sort_matches_game_probes():
    if not os.path.exists(PROBES):
        return
    cases = json.load(open(PROBES))['sort']
    for c in cases:
        items = [(k, i) for i, k in enumerate(c['keys'])]
        if c['case'].endswith('frac'):
            as3_sort(items, lambda a, b: (a[0] - b[0]) * 0.25)
        else:
            qsort_sliced(items, lambda a, b: a[0] - b[0] < 0)
        assert [i for _, i in items] == c['out'], c['case']
    assert len(cases) == 432


def test_replay_random():
    r = ReplayRandom([('FL1', 0), ('DK1', 4294967295), ('DK1', 2147483648)])
    assert r.random('FL1') == 0.0
    assert rand_index(r, 'DK1', 5) == 4          # r == 1.0 is clamped to n - 1
    try:
        r.random('AI1')
        raise AssertionError('tag mismatch not detected')
    except ReplayMismatch:
        pass
    assert rand_index(r, 'DK1', 2) == 1
    r.assert_done()
    s = SeededRandom(1)
    v = s.random('AI1')
    assert 0.0 <= v <= 1.0 and s.log[0][0] == 'AI1'


def test_load_records():
    assert RECORDS, 'run tools/rec_read.py first'
    first = None
    for path in RECORDS:
        m = load_match(path)
        assert len(m.templates) == 228
        first = first or m.templates
        assert m.templates == first                     # identical in every match
        assert m.card_values['summonClones'] == 0.5
        dummy = m.templates[0]
        assert dummy.is_type(C.CardType_Spell) and dummy.has_effect(C.CardEffect_UnsummonDummy)
        for king in (m.decks[0].selected_king_index, m.decks[1].selected_king_index):
            assert m.templates[king].type_array == 0    # kings: typeArray forced to 0 by the script
        # Whole recorded random stream replays with matching tags.
        r = m.replay_random()
        for tag, _ in m.randoms():
            r.random(tag)
        r.assert_done()
        assert m.snapshots('deal') and m.decisions()


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('ok', name)
