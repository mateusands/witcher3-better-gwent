#!/usr/bin/env python3
"""Replay harness: runs every recorded match (game/records/gNNN.json) in the simulator with the
recorded Math.random() values injected by call-site tag, and compares the simulator's event stream
(R random, F first player, S snapshots, A AI decisions, H plays, P passes, C choices, E end) with the recording, event by event.
Stops each match at its FIRST divergence and prints it with context.

Usage: python3 sim/replay.py [game/records/g000.json ...] [-v]
Exit code 0 only if every match replays with zero divergences.
"""
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, HERE)

from gwentsim.data import load_match  # noqa: E402
from gwentsim.rng import ReplayRandom, ReplayMismatch  # noqa: E402
from gwentsim.gwint.headless import SimulationStall
from gwentsim.gwint.match import run_match  # noqa: E402

RECORDS = os.path.join(ROOT, 'game', 'records')


class Divergence(Exception):
    def __init__(self, index, expected, got, detail, context):
        Exception.__init__(self, detail)
        self.index = index
        self.expected = expected
        self.got = got
        self.detail = detail
        self.context = context


def num_equal(a, b):
    """Numbers are compared exactly as doubles. The recorder writes AS3 Number -> String (16
    significant digits, docs/RUNTIME.md §3); every value seen so far is an integer or a short
    decimal (e.g. 0.5), which round-trips exactly. NaN equals NaN here (both print "NaN")."""
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return a == b


def diff_events(exp, got):
    """None if equal, else a human-readable description of the differences."""
    if exp['k'] != got['k']:
        return 'event kind: expected %s, simulator produced %s' % (exp['k'], got['k'])
    k = exp['k']
    if k == 'R':
        if exp['tag'] != got['tag'] or exp['u32'] != got['u32']:
            return 'random: expected %s:%s, got %s:%s' % (exp['tag'], exp['u32'], got['tag'], got['u32'])
        return None
    if k in ('F', 'E'):
        return None if exp == got else 'expected %s, got %s' % (exp, got)
    if k == 'A':
        out = []
        for f in ('player', 'attitude'):
            if exp[f] != got[f]:
                out.append('%s: expected %s, got %s' % (f, exp[f], got[f]))
        et, gt = exp['tx'], got['tx']
        if (et is None) != (gt is None):
            out.append('tx: expected %s, got %s' % (et, gt))
        elif et is not None:
            for f in ('source', 'slot', 'targetPlayer', 'target'):
                if et[f] != gt[f]:
                    out.append('tx.%s: expected %s, got %s' % (f, et[f], gt[f]))
            for f in ('powerChange', 'strategic'):
                if not num_equal(gt[f], et[f]):
                    out.append('tx.%s: expected %r, got %r' % (f, et[f], gt[f]))
        return '; '.join(out) or None
    if k == 'S':
        out = []
        if exp['tag'] != got['tag']:
            out.append('snapshot tag: expected %s, got %s' % (exp['tag'], got['tag']))
        for p in range(2):
            ep, gp = exp['players'][p], got['players'][p]
            for f in ep:
                if ep[f] != gp.get(f):
                    out.append('P%d.%s: expected %s, got %s' % (p, f, ep[f], gp.get(f)))
        for f in ('weather', 'roundResults'):
            if exp[f] != got[f]:
                out.append('%s: expected %s, got %s' % (f, exp[f], got[f]))
        return '; '.join(out) or None
    return None if exp == got else 'expected %s, got %s' % (exp, got)


def short(ev):
    if ev is None:
        return '(none)'
    if ev['k'] == 'R':
        return 'R %s:%d' % (ev['tag'], ev['u32'])
    if ev['k'] == 'S':
        return 'S %s  score %d/%d' % (ev['tag'], ev['players'][0]['score'], ev['players'][1]['score'])
    if ev['k'] == 'A':
        tx = ev['tx']
        return 'A P%d att=%d %s' % (ev['player'], ev['attitude'], 'pass' if tx is None else
                                    'src=%s slot=%s tp=%s tgt=%s pc=%s sv=%s' % (tx['source'], tx['slot'], tx['targetPlayer'],
                                                                             tx['target'], tx['powerChange'], tx['strategic']))
    return '%s %s' % (ev['k'], {k: v for k, v in ev.items() if k != 'k'})


def replay(path, collect_all=False):
    """Returns (match, n_compared, divergence or None). With collect_all, keeps running after a
    divergence is found (only the first one is returned) to show how far the simulation gets."""
    m = load_match(path)
    expected = m.events
    state = {'i': 0, 'div': None}

    def on_event(ev):
        i = state['i']
        state['i'] += 1
        if state['div'] is not None:
            return
        exp = expected[i] if i < len(expected) else None
        d = 'simulator produced more events than recorded' if exp is None else diff_events(exp, ev)
        if d:
            state['div'] = Divergence(i, exp, ev, d, expected[max(0, i - 6):i])
            if not collect_all:
                raise state['div']

    rnd = ReplayRandom(m.randoms())
    try:
        human = any(ev['k'] in ('H', 'P', 'C') for ev in expected)
        run_match(m.templates.values(), m.decks, m.card_values, rnd, on_event=on_event,
                  double_ai=not human, scripted_events=expected if human else None, instance_base=m.instance_base)
    except Divergence as d:
        return m, d.index, d
    except (ReplayMismatch, SimulationStall) as e:
        i = state['i']
        return m, i, Divergence(i, expected[i] if i < len(expected) else None, None, '%s: %s' % (type(e).__name__, e),
                                expected[max(0, i - 6):i])
    if state['div'] is not None:
        return m, state['div'].index, state['div']
    if state['i'] != len(expected):
        i = state['i']
        return m, i, Divergence(i, expected[i], None, 'simulation ended after %d of %d events' % (i, len(expected)),
                                expected[max(0, i - 6):i])
    return m, state['i'], None


def main(argv):
    paths = [a for a in argv if not a.startswith('-')] or sorted(glob.glob(os.path.join(RECORDS, 'g[0-9][0-9][0-9].json')))
    bad = 0
    for path in paths:
        m, n, div = replay(path)
        name = os.path.basename(path)
        total = len(m.events)
        if div is None:
            print('%s OK   %d/%d events identical (R %d, S %d, A %d)' % (
                name, n, total, len(m.randoms()), len(m.snapshots()), len(m.decisions())))
            continue
        bad += 1
        print('%s DIVERGES at event %d/%d: %s' % (name, div.index, total, div.detail))
        print('   context (last recorded events before it):')
        for e in div.context:
            print('     ' + short(e))
        print('   expected: ' + short(div.expected))
        print('   got:      ' + short(div.got))
    print('== %d/%d matches replay with zero divergences' % (len(paths) - bad, len(paths)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
