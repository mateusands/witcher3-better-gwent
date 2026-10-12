#!/usr/bin/env python3
"""Exploratory candidate-vs-native comparison over the local native deck pool.

Covers every faction and every leader (same-faction leader variants of native NPC
decks). Local simulator only; no game, save or collection change. Leader variants
are not native NPC decks: they are a coverage device, not a claim about real opponents.
"""
import argparse
import hashlib
import json
from pathlib import Path

from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.deck_pool import build_pool, leader_matchups
from gwentsim.gwint.match import run_match
from gwentsim.gwint.headless import SimulationStall
from gwentsim.rng import SeededRandom
from evaluate import validation, engine_hashes

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'game/records/g113.json'
XML = ROOT / 'game/vanilla/xml/content0/gameplay/items'
_state = {}


def setup():
    if not _state:
        match = load_match(SOURCE)
        native = NativeDecks(XML, match.templates)
        pool = build_pool(native, match.templates)
        _state.update(match=match, pairs=leader_matchups(pool))
    return _state


def player_setup():
    """(NPC deck, player-style deck) pairs; NPC decks use the mod's repaired requirements."""
    if 'player_pairs' not in _state:
        from gwentsim.player_decks import build_player_pool, player_matchups
        match = setup()['match']
        native = NativeDecks(XML, match.templates)
        npc = build_pool(native, match.templates, repaired=True)
        players = build_player_pool(match.templates, ROOT / 'game/records')
        _state['player_pairs'] = player_matchups(npc, players)
    return _state['player_pairs']


def player_seats(pair_index, swap, npc_mode=None, difficulty=2):
    """Decks per seat and the NPC seat. Without swap the player sits in seat 0 (as in the game).
    npc_mode: 'balanced' or 'strong' rebuilds the NPC deck with the mod's NPC deck option."""
    npc, player = player_setup()[pair_index]
    if npc_mode not in (None, 'original'):
        from dataclasses import replace
        from gwentsim.npc_balance import apply_mode
        from blunder_hunter import card_names
        deck = apply_mode(setup()['match'].templates, npc.deck, card_names(), npc_mode, player.deck.card_indices,
                          difficulty)
        npc = replace(npc, name='%s/%s' % (npc.name, npc_mode), deck=deck)
    seats = (npc, player) if swap else (player, npc)
    return seats, (0 if swap else 1)


def run_player(pair_index, seed, swap, npc_policy, profile, npc_mode=None):
    """NPC side played by npc_policy ('vanilla' or the candidate) against the player side
    played by response-v8 at the same profile, a strong stand-in for a human player."""
    match = setup()['match']
    seats, npc_seat = player_seats(pair_index, swap, npc_mode, profile)
    decks = [seats[0].for_player(0), seats[1].for_player(1)]
    policies = tuple(npc_policy if p == npc_seat else 'response-v8' for p in (0, 1))
    from contextlib import ExitStack
    import gwentsim.response_v8 as v8
    from evaluate_mulligan import exchange_hook
    hook = ExitStack()
    # Experiment switches change the NPC only; the stand-in player keeps the shipped AI.
    v8.NPC_SEAT = npc_seat
    if 'player-mulligan' in v8.VARIANT:
        # As in the game, the player may exchange up to two opening cards (same evaluated rule),
        # for the native and the Better AI NPC alike.
        hook.enter_context(exchange_hook(1 - npc_seat, 'evaluated', seed + 7919, []))
    if npc_policy != 'vanilla' and v8.VARIANT & {'mulligan', 'base-mulligan', 'mulligan-structural', 'mulligan-leader',
                                                 'mulligan-combined', 'mulligan-full'}:
        # A/B "response-v8:mulligan": the Better AI NPC exchanges up to two opening cards (the
        # native NPC never does); own hand and remaining own-deck counts only.
        # "base-mulligan" is the shipped exchange (since 0.9.0 the leader's weather goes first:
        # "combined") as part of the scene of both A/B arms; "mulligan" alone is the earlier one.
        variant = ('structural' if 'mulligan-structural' in v8.VARIANT else
                   'leader' if 'mulligan-leader' in v8.VARIANT else
                   'full' if 'mulligan-full' in v8.VARIANT else
                   'combined' if v8.VARIANT & {'mulligan-combined', 'base-mulligan'} else 'evaluated')
        hook.enter_context(exchange_hook(npc_seat, variant, seed, []))
    with hook:
        recorder, flow = run_match(match.templates.values(), decks, match.card_values, SeededRandom(seed),
                                   coin_toss_choice=lambda: True, seat_policies=policies, candidate_profile=profile)
    return dict(pair=pair_index, seed=seed, swapped=swap, decks=[d.name for d in seats], npcSeat=npc_seat,
                npcPolicy=npc_policy, winner=flow.gameWinner)


def group_player(task):
    pair, seed, swap, policy, profile = task[:5]
    npc_mode = task[5] if len(task) > 5 else None
    try:
        return [run_player(pair, seed, swap, 'vanilla', profile, npc_mode),
                run_player(pair, seed, swap, policy, profile, npc_mode)], None
    except (SimulationStall, RuntimeError) as exc:
        return [], dict(pair=pair, seed=seed, swapped=swap, detail=str(exc))


def run(pair_index, seed, swap, candidate_player=None, policy='response-v6', profile=2):
    state = setup();match = state['match']
    first, second = state['pairs'][pair_index]
    seats = (second, first) if swap else (first, second)
    decks = [seats[0].for_player(0), seats[1].for_player(1)]
    recorder, flow = run_match(match.templates.values(), decks, match.card_values, SeededRandom(seed),
                               coin_toss_choice=lambda: True, candidate_player=candidate_player,
                               candidate_policy=policy, candidate_profile=profile)
    result = dict(pair=pair_index, seed=seed, swapped=swap, decks=[d.name for d in seats],
                  leaders=[d.leader for d in seats], factions=[d.faction for d in seats], winner=flow.gameWinner,
                  eventSha256=hashlib.sha256(json.dumps(recorder.events, sort_keys=True).encode()).hexdigest())
    if candidate_player is not None:
        decisions = flow.playerControllers[candidate_player].policy_decisions
        audits = [d.get('sequenceSearch', {}) for d in decisions]
        result.update(candidatePlayer=candidate_player, candidateWon=flow.gameWinner == candidate_player,
                      changedDecisions=sum(d['changed'] for d in decisions),
                      nativeUnsupportedChoices=sum(a.get('reason') == 'native_unsupported_choice' for a in audits))
    return result


def group(task):
    pair, seed, swap, policy, profile = task
    try:
        out = [run(pair, seed, swap)]
        for seat in (0, 1):
            out.append(run(pair, seed, swap, seat, policy, profile))
        return out, None
    except (SimulationStall, RuntimeError) as exc:
        return [], dict(pair=pair, seed=seed, swapped=swap, detail=str(exc))


def summarize(trials):
    base = {(t['pair'], t['seed'], t['swapped']): t for t in trials if 'candidatePlayer' not in t}
    cand = [t for t in trials if 'candidatePlayer' in t]
    score = lambda won, winner: 1 if won else 0.5 if winner not in (0, 1) else 0
    def block(rows):
        return dict(matches=len(rows),
            candidateScore=sum(score(t['candidateWon'], t['winner']) for t in rows),
            nativeSeatScore=sum(score(base[t['pair'], t['seed'], t['swapped']]['winner'] == t['candidatePlayer'],
                                      base[t['pair'], t['seed'], t['swapped']]['winner']) for t in rows))
    by_leader = {}
    for t in cand:
        by_leader.setdefault(str(t['leaders'][t['candidatePlayer']]), []).append(t)
    by_faction = {}
    for t in cand:
        by_faction.setdefault(str(t['factions'][t['candidatePlayer']]), []).append(t)
    return dict(overall=block(cand), byCandidateLeader={k: block(v) for k, v in sorted(by_leader.items())},
                byCandidateFaction={k: block(v) for k, v in sorted(by_faction.items())},
                nativeUnsupportedChoices=sum(t['nativeUnsupportedChoices'] for t in cand),
                scope='Exploratory; correlated seats/decks; leader variants are coverage devices. No strength claim.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', type=int, required=True)
    parser.add_argument('--policy', choices=['response-v6', 'response-v8'], default='response-v6')
    parser.add_argument('--profile', choices=['easy', 'medium', 'hard', 'expert'], default='hard')
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--pairs', type=int, help='limit to the first N matchups (smoke runs)')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    hashes = engine_hashes()
    pairs = setup()['pairs']
    count = min(len(pairs), args.pairs or len(pairs))
    profile = ['easy', 'medium', 'hard', 'expert'].index(args.profile)
    tasks = [(p, s, w, args.policy, profile) for p in range(count) for s in args.seeds for w in (False, True)]
    if args.jobs > 1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
            groups = pool.map(group, tasks, chunksize=1)
    else:
        groups = list(map(group, tasks))
    report = dict(status='exploratory', policy=args.policy, profile=args.profile, seeds=args.seeds,
                  validation=validation(), engineSourceSha256=hashes, sourceRecord=SOURCE.name,
                  pairs=[dict(index=i, decks=[a.name, b.name]) for i, (a, b) in enumerate(pairs[:count])],
                  trials=[t for g, _ in groups for t in g], errors=[e for _, e in groups if e])
    report['summary'] = summarize(report['trials'])
    report['sourceUnchangedDuringRun'] = engine_hashes() == hashes
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('%d trials, %d errors; overall %s; native unsupported choices %d; source unchanged %s' % (
        len(report['trials']), len(report['errors']), report['summary']['overall'],
        report['summary']['nativeUnsupportedChoices'], report['sourceUnchangedDuringRun']))
    return int(bool(report['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
