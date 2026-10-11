"""Mini paired duel: learned-leaf V8 (PoC) vs V8, simulator only.

Each unit = (deck matchup, seed) played twice with identical decks/seed:
  game A: learned in seat 0, V8 in seat 1
  game B: V8 in seat 0, learned in seat 1
Unit score for learned = A + B in {0, 0.5, ..., 2}. Analysis is on units
(dependent games stay together): exact two-sided sign test on units where
learned scored != 1. Seeds differ from the training collection.
"""
import argparse
import json
import sys
import time
from pathlib import Path
import multiprocessing as mp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))

from evaluate_pool import setup
from gwentsim.gwint.match import run_match
from gwentsim.gwint.headless import SimulationStall
from gwentsim.gwint.sequence_ai_controller import ResponseV8AIPlayerController
from gwentsim.response_v8 import choose_response_v8
from gwentsim.response_learned import choose_response_learned
from gwentsim.rng import SeededRandom

LEARNED_SEAT = None


def _search(self, position, context):
    if self.playerID == LEARNED_SEAT:
        return choose_response_learned(position, context, self.search_profile)
    return choose_response_v8(position, context, self.search_profile)


ResponseV8AIPlayerController.search = _search


def play(pair, seed, learned_seat):
    global LEARNED_SEAT
    LEARNED_SEAT = learned_seat
    state = setup()
    first, second = state['pairs'][pair]
    decks = [first.for_player(0), second.for_player(1)]
    _, flow = run_match(state['match'].templates.values(), decks, state['match'].card_values,
                        SeededRandom(seed), seat_policies=('response-v8', 'response-v8'),
                        candidate_profile=2, coin_toss_choice=lambda: True)
    w = flow.gameWinner
    return 1.0 if w == learned_seat else 0.0 if w in (0, 1) else 0.5


def unit(task):
    pair, seed = task
    t0 = time.perf_counter()
    try:
        a = play(pair, seed, 0)
        b = play(pair, seed, 1)
        return dict(pair=pair, seed=seed, gameA=a, gameB=b, score=a + b,
                    seconds=time.perf_counter() - t0, error=None)
    except (SimulationStall, RuntimeError, ValueError) as exc:
        return dict(pair=pair, seed=seed, error=str(exc))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--units', type=int, default=50)
    p.add_argument('--jobs', type=int, default=5)
    p.add_argument('--seed-base', type=int, default=9001)
    p.add_argument('--output', type=Path, default=ROOT / 'game/evaluations/poc_mini_100/duel.json')
    a = p.parse_args()
    pairs = len(setup()['pairs'])
    tasks = [((i * 2) % pairs, a.seed_base + i * 13) for i in range(a.units)]
    t0 = time.perf_counter()
    with mp.get_context('fork').Pool(min(a.jobs, 5)) as pool:
        rows = pool.map(unit, tasks, chunksize=1)
    elapsed = time.perf_counter() - t0
    ok = [r for r in rows if not r['error']]
    errors = [r for r in rows if r['error']]
    wins = sum(r['score'] > 1 for r in ok)
    losses = sum(r['score'] < 1 for r in ok)
    ties = len(ok) - wins - losses
    from scipy.stats import binomtest
    pval = binomtest(wins, wins + losses, 0.5).pvalue if wins + losses else 1.0
    summary = dict(units=len(ok), games=2 * len(ok), errors=len(errors),
                   learnedPoints=sum(r['score'] for r in ok), v8Points=2 * len(ok) - sum(r['score'] for r in ok),
                   unitsLearnedBetter=wins, unitsV8Better=losses, unitsEven=ties,
                   signTestP=pval, minutes=elapsed / 60,
                   scope='Mini PoC; one seed block; not a strength claim.')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(dict(summary=summary, rows=rows), indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
