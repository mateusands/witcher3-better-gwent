"""Injectable Math.random() for the simulator.

Every Math.random() call in the rule/AI classes is identified by a call-site tag, exactly as the
recorder numbers them (tools/build_recorder.py: n-th occurrence of Math.random() in the
decompiled file): CM1..3 CardManager, CI1..10 CardInstance, CL1..4 CardLeaderInstance,
DK1..2 GwintDeck, FL1 GwintGameFlowController, AI1..15 AIPlayerController.

Value = u32 / (2^32 - 1), a closed interval [0, 1] (docs/RUNTIME.md §2); this is why the game
code clamps with Math.min(Math.floor(r * n), n - 1) (see rand_index).
"""
import random as _random

from . import as3

U32_DENOM = 4294967295


class ReplayMismatch(AssertionError):
    pass


class ReplayRandom:
    """Replays recorded (tag, u32) values in order; the simulator's call site must match."""

    def __init__(self, records):
        self.records = [(t, int(u)) for t, u in records]
        self.pos = 0

    def random(self, tag):
        if self.pos >= len(self.records):
            raise ReplayMismatch('random #%d (%s): recording exhausted' % (self.pos, tag))
        want, u = self.records[self.pos]
        if want != tag:
            raise ReplayMismatch('random #%d: simulator called %s, game called %s' % (self.pos, tag, want))
        self.pos += 1
        return u / U32_DENOM

    def remaining(self):
        return len(self.records) - self.pos

    def assert_done(self):
        if self.pos != len(self.records):
            raise ReplayMismatch('%d recorded random values not consumed (next: %s)'
                                 % (self.remaining(), self.records[self.pos][0]))


class SeededRandom:
    """Free-play source with the game's distribution (uniform u32 / (2^32-1)); logs every call
    in the recorder's format so a simulated match can itself be replayed."""

    def __init__(self, seed=None):
        self._r = _random.Random(seed)
        self.log = []

    def random(self, tag):
        u = self._r.getrandbits(32)
        self.log.append((tag, u))
        return u / U32_DENOM


class _MathRandom:
    """The process-wide Math.random() used by the ported rule/AI classes (sim/gwentsim/gwint).

    Every call site passes its recorder tag (e.g. math_random('CI4')), so a ReplayRandom source can
    check that the simulator calls Math.random() at the same site, in the same order, as the game.
    `listener(tag, value)` (optional) sees every value, e.g. to log it next to snapshots."""

    def __init__(self):
        self.source = None
        self.listener = None


MATH = _MathRandom()


def set_random_source(source, listener=None):
    MATH.source = source
    MATH.listener = listener


def math_random(tag):
    """Math.random() at the call site identified by `tag`."""
    if MATH.source is None:
        raise RuntimeError('no Math.random() source set (rng.set_random_source)')
    v = MATH.source.random(tag)
    if MATH.listener is not None:
        MATH.listener(tag, v)
    return v


def rand_index(rng, tag, n):
    """The game's idiom Math.min(Math.floor(Math.random() * n), n - 1), as an int."""
    return as3.to_int(as3.math_min(as3.floor(rng.random(tag) * n), n - 1))
