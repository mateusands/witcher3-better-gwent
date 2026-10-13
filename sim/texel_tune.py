#!/usr/bin/env python3
"""Texel-style tuning of the V8 utility weights (gwentsim.tuning.DEFAULTS).

Specification
-------------
Texel's method (chessprogramming.org, "Texel's Tuning Method") fits evaluation weights to game
results instead of playing games for every candidate: collect many positions with the final
result, map a static evaluation of each position to a predicted win probability, and minimise
the error between prediction and result with a cheap local search. No match is played during
the fit.

collect(pair, seed, swap, profile, npc_decks, policy)
    Plays one player-deck match exactly like the Lab benchmark (evaluate_pool.run_player, the
    scene() switches taken from the policy string, e.g. "response-v8:player-mulligan+base-mulligan";
    the player seat is the shipped response-v8 stand-in). At every decision of the NPC seat it
    records one JSON-serialisable sample: the inputs of the V8 leaf utility for the state that
    decision leads to, plus the NPC's final match result (1 win, 0.5 draw, 0 loss).
    The evaluated state is the one the search itself values for the chosen decision:
      * a pass: the current position with passing=True at depth 0 (choose_sequence's pass_value);
      * a play: the position after the chosen action at depth 1 (choose_sequence's leaf value);
      * a play the position model cannot apply: the current position at depth 0, passing=False.
    No Position object is stored; a sample keeps the scores, hand size, pending draws, own leader
    state, the reserve split into its weight-free part and its draw part (Position.reserve() is
    reserve0 + draw_weight * reserveDraw), the public opponent average, the context, and only
    the board/grave creatures and own deck counts that faction_carry and the Northern Kingdoms
    draw term read.

static_value(sample, weights)
    gwentsim.sequence_search.utility(position, context, depth, reserve, opponent_mean, passing)
    called on a minimal position rebuilt from the sample, with tuning.ACTIVE set to the weights
    for the call only (restored afterwards). This is the very function the search uses for its
    leaves, so the tuned quantity is the AI's own. Deterministic.

fit_k(samples), loss(samples, weights, k), tune(samples, start=DEFAULTS, steps=...)
    Prediction p = sigmoid(k * logit(u)) for the utility u (clipped to [1e-4, 1 - 1e-4]); k = 1
    keeps the utility as the probability. fit_k fits k once with the shipped weights (log grid
    plus golden-section refinement, never worse than k = 1); tune then keeps k fixed. loss is the
    mean squared error (or the mean log loss) between p and the result. tune is coordinate
    descent on the log of the multiplicative factors weight / default, clipped to the SPSA bounds
    (0.25x .. 4x of the defaults): each weight in turn tries one step up and one step down and
    keeps a strict improvement; a pass without improvement halves the step. Returns the best
    weights and a history (one entry per pass, the first being the start).

Limitations: the static value is a one-ply leaf of the search. Inside the full response search
the same weights also act through opponent-reply leaves (opponent reserve from hypothesised
hands instead of hand count x average) and through which moves are chosen; pass_risk only acts
on pass samples. A fit improves how well the leaf predicts results on positions reached by the
current weights; whether it plays better must still be checked by an A/B benchmark.

CLI (heavy runs belong on the cloud server):
    python3 sim/texel_tune.py collect --pairs N --seeds 1 2 3 --jobs 12 --out samples.jsonl
    python3 sim/texel_tune.py fit --data samples.jsonl --out weights.json
"""
import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gwentsim import constants as C  # noqa: E402
from gwentsim import tuning  # noqa: E402
from gwentsim.tuning import DEFAULTS  # noqa: E402
from gwentsim.position import Card, ROWS, UnsupportedPosition  # noqa: E402
from gwentsim.sequence_search import Context, utility, public_opponent_average  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'
PROFILES = ('easy', 'medium', 'hard', 'expert')
LOW, HIGH = 0.25, 4.0          # SPSA bounds (lab/core.py TUNE_DEFAULTS), as factors of the defaults
EPS = 1e-4
CARRY_FACTIONS = (C.FactionId_No_Mans_Land, C.FactionId_Skellige)
VERSION = 1


# ---- Collection --------------------------------------------------------------

def _with_weights(weights, fn):
    saved = tuning.ACTIVE
    tuning.ACTIVE = dict(DEFAULTS, **(weights or {}))
    try:
        return fn()
    finally:
        tuning.ACTIVE = saved


def _creatures(position, keys):
    out = []
    for k in keys:
        c = position.cards[k]
        if c.is_type(C.CardType_Creature):
            out.append([c.power, c.types])
    return out


def features(position, context, depth, passing, mean):
    """The inputs of sequence_search.utility for this position (JSON-serialisable)."""
    own = position.player
    r0 = _with_weights(dict(draw_weight=0.0), position.reserve)
    r1 = _with_weights(dict(draw_weight=1.0), position.reserve)
    factions = {own: context.own_faction, 1 - own: context.opponent_faction}
    board, grave = {}, {}
    for side in (0, 1):
        if factions[side] in CARRY_FACTIONS:
            board[str(side)] = _creatures(position, [k for row in ROWS for k in position.board[side, row]])
            grave[str(side)] = _creatures(position, position.grave[side])
    draws = []
    if context.own_faction == C.FactionId_Northern_Kingdom:
        draws = [[position.catalog[t].power, n] for t, n in sorted(position.counts.items()) if n]
    ctx = asdict(context)
    ctx['opponent_known'] = list(ctx['opponent_known'])
    return dict(player=own, scores=list(position.scores()), hand=len(position.hand),
                unknownDraws=position.unknown_draws, leaderModeled=bool(position.leader_modeled(own)),
                reserve0=r0, reserveDraw=r1 - r0, mean=mean, depth=depth, passing=passing,
                context=ctx, board=board, grave=grave, draws=draws)


def collect(pair, seed, swap, profile='hard', npc_decks=None, policy=SCENE, weights=None, probe=None):
    """Play one benchmark-scene player-deck match; one sample per NPC decision (see module doc).

    weights: optional utility weights for the NPC seat (as the Lab's tune-eval does), to collect
    positions reached by tuned weights. probe(position, context, sample): test hook receiving the
    real evaluated Position next to each sample."""
    import evaluate_pool
    import gwentsim.response_v8 as v8
    from gwentsim.gwint.sequence_ai_controller import ResponseV8AIPlayerController
    profile = profile if isinstance(profile, int) else PROFILES.index(profile)
    base_policy, _, flags = policy.partition(':')
    if base_policy != 'response-v8':
        raise ValueError('collect needs a response-v8 NPC policy')
    npc_seat = evaluate_pool.player_seats(pair, swap)[1]
    samples, probes = [], []
    original = ResponseV8AIPlayerController.search

    def search(self, position, context):
        result = original(self, position, context)
        if self.playerID == npc_seat:
            mean = public_opponent_average(position)
            state, depth, passing = position, 0, result.action is None
            if result.action is not None:
                try:
                    state, depth = position.apply(result.action), 1
                except (UnsupportedPosition, ValueError):
                    state, depth = position, 0
            sample = features(state, context, depth, passing, mean)
            samples.append(sample)
            probes.append((state, context, sample))
        return result

    saved = v8.VARIANT, v8.NPC_SEAT, dict(tuning.SEAT_PARAMS)
    v8.VARIANT = frozenset(f for f in flags.split('+') if f)
    tuning.SEAT_PARAMS.clear()
    if weights:
        tuning.SEAT_PARAMS[npc_seat] = dict(weights)
    ResponseV8AIPlayerController.search = search
    try:
        r = evaluate_pool.run_player(pair, seed, swap, base_policy, profile, npc_decks)
    finally:
        ResponseV8AIPlayerController.search = original
        v8.VARIANT, v8.NPC_SEAT = saved[:2]
        tuning.SEAT_PARAMS.clear(); tuning.SEAT_PARAMS.update(saved[2]); tuning.reset()
    result = 1 if r['winner'] == npc_seat else 0.5 if r['winner'] not in (0, 1) else 0
    for i, s in enumerate(samples):
        s.update(v=VERSION, pair=pair, seed=seed, swap=swap, npcSeat=npc_seat, decision=i, result=result)
    if probe is not None:
        for state, context, sample in probes:
            probe(state, context, sample)
    return samples


# ---- Static value ------------------------------------------------------------

class LeafPosition:
    """The parts of a Position that sequence_search.utility (and faction_carry) read."""

    def __init__(self, s):
        self.player = s['player']
        self._scores = tuple(s['scores'])
        self.hand = (None,) * s['hand']
        self.unknown_draws = s['unknownDraws']
        self._leader = s['leaderModeled']
        self.cards, self.board, self.grave = {}, {}, {}
        key = 0
        for side in (0, 1):
            for row in ROWS:
                self.board[side, row] = ()
            self.grave[side] = ()
            for where in ('board', 'grave'):
                keys = []
                for power, types in s[where].get(str(side), ()):
                    key += 1
                    self.cards[key] = Card(key, 0, power, types, (), (), side, side, 5)
                    keys.append(key)
                if where == 'board':
                    self.board[side, 5] = tuple(keys)
                else:
                    self.grave[side] = tuple(keys)
        self.catalog = {i: SimpleNamespace(power=p) for i, (p, n) in enumerate(s['draws'])}
        self.counts = {i: n for i, (p, n) in enumerate(s['draws'])}

    def scores(self):
        return self._scores

    def leader_modeled(self, side):
        return self._leader if side == self.player else False


class Leaf:
    __slots__ = ('position', 'context', 'depth', 'passing', 'reserve0', 'reserve_draw', 'mean', 'result')

    def __init__(self, s):
        ctx = dict(s['context'], opponent_known=tuple(s['context']['opponent_known']))
        self.position, self.context = LeafPosition(s), Context(**ctx)
        self.depth, self.passing, self.mean = s['depth'], s['passing'], s['mean']
        self.reserve0, self.reserve_draw, self.result = s['reserve0'], s['reserveDraw'], s['result']

    def value(self):
        """Utility under tuning.ACTIVE (the caller sets it)."""
        reserve = self.reserve0 + tuning.ACTIVE['draw_weight'] * self.reserve_draw
        return utility(self.position, self.context, self.depth, reserve, self.mean, passing=self.passing)


def prepare(samples):
    """Rebuild every sample once; loss/fit_k/tune accept the result in place of the samples."""
    return samples if isinstance(samples, Prepared) else Prepared(samples)


class Prepared(list):
    def __init__(self, samples):
        super().__init__(Leaf(s) for s in samples)


def static_value(sample, weights):
    """V8 leaf utility (sequence_search.utility) of the sample's position under the weights."""
    leaf = sample if isinstance(sample, Leaf) else Leaf(sample)
    return _with_weights(weights, leaf.value)


def values(samples, weights):
    leaves = prepare(samples)
    return _with_weights(weights, lambda: [leaf.value() for leaf in leaves])


# ---- Fit ---------------------------------------------------------------------

def predict(u, k):
    u = min(1 - EPS, max(EPS, u))
    x = k * math.log(u / (1 - u))
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def _loss_of(us, results, k, kind):
    total = 0.0
    for u, r in zip(us, results):
        p = predict(u, k)
        if kind == 'log':
            p = min(1 - 1e-12, max(1e-12, p))
            total -= r * math.log(p) + (1 - r) * math.log(1 - p)
        else:
            total += (p - r) ** 2
    return total / max(1, len(us))


def loss(samples, weights, k, kind='mse'):
    """Mean squared error (or mean log loss) of sigmoid(k * logit(utility)) against the results."""
    leaves = prepare(samples)
    return _loss_of(values(leaves, weights), [leaf.result for leaf in leaves], k, kind)


def fit_k(samples, weights=DEFAULTS, kind='mse', low=0.02, high=20.0):
    """Scale k minimising the loss for fixed weights; never worse than k = 1."""
    leaves = prepare(samples)
    us, results = values(leaves, weights), [leaf.result for leaf in leaves]
    f = lambda lk: _loss_of(us, results, math.exp(lk), kind)  # noqa: E731
    lo, hi = math.log(low), math.log(high)
    grid = [lo + (hi - lo) * i / 40 for i in range(41)] + [0.0]
    scored = sorted((f(x), x) for x in grid)
    best_loss, best = scored[0]
    step = (hi - lo) / 40
    a, b = best - step, best + step
    g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(40):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a); fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a); fd = f(d)
    for value, x in ((fc, c), (fd, d)):
        if value < best_loss:
            best_loss, best = value, x
    return math.exp(best)


def tune(samples, start=DEFAULTS, steps=50, k=None, kind='mse', step=0.25, min_step=0.01,
         low=LOW, high=HIGH, names=None, log=None):
    """Coordinate descent on log(weight / default) within [low, high] factors (see module doc)."""
    leaves = prepare(samples)
    results = [leaf.result for leaf in leaves]
    if k is None:
        k = fit_k(leaves, kind=kind)
    names = sorted(names or DEFAULTS)
    lo, hi = math.log(low), math.log(high)
    x = {n: min(hi, max(lo, math.log(start.get(n, DEFAULTS[n]) / DEFAULTS[n]))) for n in DEFAULTS}
    weights = lambda x: {n: DEFAULTS[n] * math.exp(x[n]) for n in DEFAULTS}  # noqa: E731
    evaluate = lambda x: _loss_of(values(leaves, weights(x)), results, k, kind)  # noqa: E731
    best = evaluate(x)
    history = [dict(step=0, delta=step, loss=best, weights=weights(x))]
    for i in range(1, steps + 1):
        improved = False
        for n in names:
            for sign in (1, -1):
                trial = dict(x, **{n: min(hi, max(lo, x[n] + sign * step))})
                if trial[n] == x[n]:
                    continue
                value = evaluate(trial)
                if value < best - 1e-15:
                    x, best, improved = trial, value, True
                    break
        history.append(dict(step=i, delta=step, loss=best, weights=weights(x)))
        if log:
            log('pass %d step %.4f loss %.6f' % (i, step, best))
        if not improved:
            step /= 2
            if step < min_step:
                break
    return weights(x), history


# ---- CLI ---------------------------------------------------------------------

def _collect_task(task):
    pair, seed, swap, profile, npc_decks, policy, weights = task
    from gwentsim.gwint.headless import SimulationStall
    started = time.time()
    try:
        return task[:3], collect(pair, seed, swap, profile, npc_decks, policy, weights), None, time.time() - started
    except (SimulationStall, RuntimeError, UnsupportedPosition) as exc:
        return task[:3], [], str(exc), time.time() - started


def _holdout(sample, fraction):
    key = '%s/%s/%s' % (sample['pair'], sample['seed'], sample['swap'])
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xffffffff < fraction


def main(argv=None):
    parser = argparse.ArgumentParser(description='Texel-style tuning of the V8 utility weights.')
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('collect', help='play benchmark-scene matches and write samples (JSON lines)')
    c.add_argument('--pairs', type=int, help='first N player-deck pairs (default: all)')
    c.add_argument('--pair-start', type=int, default=0)
    c.add_argument('--seeds', nargs='+', type=int, required=True)
    c.add_argument('--swap', choices=['both', 'off', 'on'], default='both')
    c.add_argument('--profile', choices=PROFILES, default='hard')
    c.add_argument('--npc-decks', default=None, help="NPC deck mode, e.g. 'balanced' (default: original)")
    c.add_argument('--policy', default=SCENE)
    c.add_argument('--weights', type=Path, help='weights JSON for the NPC seat (a fit output or a plain dict)')
    c.add_argument('--jobs', type=int, default=1)
    c.add_argument('--out', type=Path, required=True)
    f = sub.add_parser('fit', help='fit k, then tune the weights on collected samples')
    f.add_argument('--data', type=Path, nargs='+', required=True)
    f.add_argument('--out', type=Path, required=True)
    f.add_argument('--loss', choices=['mse', 'log'], default='mse')
    f.add_argument('--steps', type=int, default=60, help='maximum coordinate-descent passes')
    f.add_argument('--step', type=float, default=0.25, help='initial log-factor step')
    f.add_argument('--holdout', type=float, default=0.0, help='fraction of matches held out for a check')
    f.add_argument('--start', type=Path, help='start weights JSON (default: shipped)')
    args = parser.parse_args(argv)
    if args.command == 'collect':
        return _main_collect(args)
    return _main_fit(args)


def _read_weights(path):
    data = json.loads(path.read_text())
    return {n: float(v) for n, v in data.get('weights', data).items() if n in DEFAULTS}


def _main_collect(args):
    import evaluate_pool
    pairs = evaluate_pool.player_setup()
    end = len(pairs) if args.pairs is None else min(len(pairs), args.pair_start + args.pairs)
    swaps = {'both': (False, True), 'off': (False,), 'on': (True,)}[args.swap]
    weights = _read_weights(args.weights) if args.weights else None
    tasks = [(p, s, w, args.profile, args.npc_decks, args.policy, weights)
             for p in range(args.pair_start, end) for s in args.seeds for w in swaps]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time(); matches = samples = errors = 0
    with args.out.open('w') as out:
        def write(item):
            nonlocal matches, samples, errors
            key, rows, error, seconds = item
            if error:
                errors += 1
                print('error %s: %s' % (key, error), file=sys.stderr)
                return
            matches += 1; samples += len(rows)
            for row in rows:
                out.write(json.dumps(row, separators=(',', ':')) + '\n')
            out.flush()
            if matches % 50 == 0:
                print('%d/%d matches, %d samples, %.1fs' % (matches, len(tasks), samples, time.time() - started),
                      file=sys.stderr)
        if args.jobs > 1:
            import multiprocessing
            with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
                for item in pool.imap_unordered(_collect_task, tasks, chunksize=1):
                    write(item)
        else:
            for task in tasks:
                write(_collect_task(task))
    elapsed = time.time() - started
    print('%d matches, %d samples, %d errors, %.1fs (%.2fs per match per job)' % (
        matches, samples, errors, elapsed, elapsed * max(1, args.jobs) / max(1, matches + errors)))
    return 0 if matches else 1


def _main_fit(args):
    rows = [json.loads(line) for path in args.data for line in path.read_text().splitlines() if line.strip()]
    train = [s for s in rows if not _holdout(s, args.holdout)]
    held = [s for s in rows if _holdout(s, args.holdout)]
    if not train:
        print('no training samples (empty data or every match held out)', file=sys.stderr)
        return 1
    start = _read_weights(args.start) if args.start else DEFAULTS
    start = dict(DEFAULTS, **start)
    leaves = prepare(train)
    k = fit_k(leaves, kind=args.loss)
    began = time.time()
    best, history = tune(leaves, start=start, steps=args.steps, k=k, kind=args.loss, step=args.step,
                         log=lambda line: print(line, file=sys.stderr))
    report = dict(method='texel', loss_kind=args.loss, k=k, samples=len(rows), train=len(train), holdout=len(held),
                  matches=len({(s['pair'], s['seed'], s['swap']) for s in rows}),
                  results=dict(win=sum(s['result'] == 1 for s in rows), draw=sum(s['result'] == 0.5 for s in rows),
                               loss=sum(s['result'] == 0 for s in rows)),
                  weights=best, factors={n: best[n] / DEFAULTS[n] for n in DEFAULTS}, start=start,
                  loss=dict(start=history[0]['loss'], end=history[-1]['loss']),
                  seconds=round(time.time() - began, 1), history=history)
    if held:
        hl = prepare(held)
        report['holdoutLoss'] = dict(start=loss(hl, start, k, args.loss), end=loss(hl, best, k, args.loss))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('k %.4f, loss %.6f -> %.6f, factors %s' % (k, report['loss']['start'], report['loss']['end'],
          {n: round(v, 3) for n, v in report['factors'].items()}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
