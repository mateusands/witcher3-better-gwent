"""Data collector for Gwent AI PoC.

Runs ~100 matches with exploratory V8 self-play (epsilon-greedy),
extracting afterstate feature vectors for each turn and labeling with
the final match outcome.

Strictly groups by match_id to prevent data leakage between games.
"""
import argparse
import json
import random
import sys
import time
from dataclasses import replace
from pathlib import Path
import multiprocessing as mp

ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = ROOT / 'sim'
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from evaluate_pool import setup
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from gwentsim import response_v8
from gwentsim.position import UnsupportedPosition
from gwentsim.afterstate_features import extract_features, FEATURE_NAMES, NUM_FEATURES


def _run_single_match(task):
    match_id, pair_index, seed, swap, epsilon = task
    state = setup()
    match = state['match']
    first, second = state['pairs'][pair_index]
    seats = (second, first) if swap else (first, second)
    decks = [seats[0].for_player(0), seats[1].for_player(1)]

    rng = random.Random(seed + match_id * 31)
    turn_samples = []

    orig_search = response_v8.choose_response_v8

    def hooked_search(pos, ctx, diff=2):
        res = orig_search(pos, ctx, diff)
        action = res.action
        explored = False

        if rng.random() < epsilon:
            candidates = []
            for a in pos.actions():
                try:
                    st = pos.apply(a)
                    candidates.append((a, st))
                except UnsupportedPosition:
                    continue
            if len(candidates) > 1:
                alt_a, alt_st = rng.choice(candidates)
                action = alt_a
                explored = True
                res = replace(res, action=alt_a, reason='poc_exploration')

        features = None
        act_kind = 'pass'
        if action is not None:
            try:
                after = pos.apply(action)
                features = extract_features(after, ctx)
                act_kind = 'play'
            except Exception:
                pass
        else:
            features = extract_features(pos, ctx)
            act_kind = 'pass'

        if features is not None:
            turn_samples.append({
                'match_id': match_id,
                'player': pos.player,
                'round_index': ctx.round_index,
                'act_kind': act_kind,
                'explored': explored,
                'features': features,
            })
        return res

    response_v8.choose_response_v8 = hooked_search
    try:
        t0 = time.perf_counter()
        rec, flow = run_match(
            match.templates.values(),
            decks,
            match.card_values,
            SeededRandom(seed),
            seat_policies=('response-v8', 'response-v8'),
            candidate_profile=2,
            coin_toss_choice=lambda: True,
        )
        elapsed = time.perf_counter() - t0
        winner = flow.gameWinner

        # Label samples
        for s in turn_samples:
            if winner == s['player']:
                s['won_match'] = 1.0
            elif winner in (0, 1):
                s['won_match'] = 0.0
            else:
                s['won_match'] = 0.5

        return {
            'match_id': match_id,
            'winner': winner,
            'elapsed_sec': elapsed,
            'samples': turn_samples,
            'error': None,
        }
    except Exception as exc:
        return {
            'match_id': match_id,
            'winner': None,
            'elapsed_sec': 0.0,
            'samples': [],
            'error': str(exc),
        }
    finally:
        response_v8.choose_response_v8 = orig_search


def collect(num_matches=100, jobs=5, seed_base=2026, epsilon=0.10, output_path=None):
    state = setup()
    num_pairs = len(state['pairs'])
    tasks = []
    for i in range(num_matches):
        pair_idx = i % num_pairs
        seed = seed_base + (i // num_pairs) * 1000 + i * 7
        swap = (i % 2 == 1)
        tasks.append((i, pair_idx, seed, swap, epsilon))

    print(f"Starting collection of {num_matches} matches using {jobs} jobs...")
    t_start = time.perf_counter()

    if jobs > 1:
        with mp.get_context('fork').Pool(jobs) as pool:
            results = pool.map(_run_single_match, tasks)
    else:
        results = [_run_single_match(t) for t in tasks]

    total_time = time.perf_counter() - t_start
    errors = [r for r in results if r['error']]
    successful = [r for r in results if not r['error']]
    all_samples = [s for r in successful for s in r['samples']]

    print(f"Collection complete in {total_time:.1f}s ({total_time / 60:.2f} min).")
    print(f"Successful matches: {len(successful)}/{num_matches}, Errors: {len(errors)}")
    print(f"Total turn samples collected: {len(all_samples)}")

    dataset = {
        'metadata': {
            'num_matches_requested': num_matches,
            'num_matches_completed': len(successful),
            'total_time_sec': total_time,
            'epsilon': epsilon,
            'feature_names': FEATURE_NAMES,
            'num_features': NUM_FEATURES,
        },
        'samples': all_samples,
    }

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(dataset, indent=2))
        print(f"Saved dataset to {out_p}")

    return dataset


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Collect PoC dataset")
    parser.add_argument('--num-matches', type=int, default=100)
    parser.add_argument('--jobs', type=int, default=5)
    parser.add_argument('--seed-base', type=int, default=2026)
    parser.add_argument('--epsilon', type=float, default=0.10)
    parser.add_argument('--output', type=Path, default=ROOT / 'game/evaluations/poc_mini_100/dataset.json')
    args = parser.parse_args()

    collect(args.num_matches, args.jobs, args.seed_base, args.epsilon, args.output)
