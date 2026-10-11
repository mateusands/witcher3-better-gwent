#!/usr/bin/env python3
"""Outcome-based blunder hunter for the V8 policy (diagnostic only).

For a simulated match the candidate (V8) LOST or drew against the native AI, every V8
decision is retried with up to MAX_ALTERNATIVES alternatives that V8's own search ranked
(plus a pass). Each option (the chosen move too) is replayed with the real game over
CONTINUATIONS luck streams that start right after the judged decision: everything before it
is identical, only later draws/coin flips vary. A decision is reported only when an
alternative's mean result beats the chosen move's mean by MIN_REGRET, so a lucky draw after
an equal move is not mistaken for a blunder.

The replay uses the real hidden cards, i.e. full information, ONLY to judge decisions after
the fact. The policy itself is unchanged and never sees hidden information.
"""
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent

from gwentsim.gwint.match import run_match  # noqa: E402
from gwentsim.gwint.sequence_ai_controller import ResponseV8AIPlayerController  # noqa: E402
from gwentsim.response_v8 import alternative_action  # noqa: E402
from gwentsim.rng import SeededRandom  # noqa: E402

PROFILES = ['easy', 'medium', 'hard', 'expert']
MAX_ALTERNATIVES = 2
CONTINUATIONS = 4          # luck continuations per option after the judged decision
MIN_REGRET = 0.5           # mean result gain (0..1) an alternative needs to count as a finding


class BranchRandom(SeededRandom):
    """Same stream as SeededRandom until branch(): then a fresh stream for the rest of the match.

    Everything before the judged decision (shuffle, hands, earlier moves) is identical across
    options; only the luck after it varies, so options are compared on equal footing."""

    def __init__(self, seed):
        super().__init__(seed)
        self.seed = seed

    def branch(self, decision, k):
        import random as _random
        self._r = _random.Random('%s/%s/%s' % (self.seed, decision, k))


@lru_cache(maxsize=1)
def card_names():
    names = {}
    base = ROOT / 'game/vanilla/xml/content0/gameplay/items'
    for filename in ('def_gwint_cards_final.xml', 'def_gwint_battle_king_cards.xml'):
        for card in ET.parse(base / filename).findall('.//card'):
            names[int(card.attrib['index'])] = card.attrib['name']
    return names


def describe(position, action):
    if action is None:
        return 'pass'
    card = position.cards.get(action.source)
    name = card_names().get(card.template, 'template %d' % card.template) if card else str(action.source)
    text = name
    if action.chain:
        text += ' (recover %s)' % ', '.join(card_names().get(position.cards[k].template, str(k)) for k, _ in action.chain)
    elif action.target != -1 and action.target in position.cards:
        text += ' (target %s)' % card_names().get(position.cards[action.target].template, str(action.target))
    return text


def match_setup(spec):
    if spec['source'] == 'player':
        from evaluate_pool import setup, player_seats
        seats, _ = player_seats(spec['pair'], spec['swap'])
        return setup()['match'], [seats[0].for_player(0), seats[1].for_player(1)], [d.name for d in seats]
    if spec['source'] == 'pool':
        from evaluate_pool import setup
        state = setup()
        match = state['match']
        first, second = state['pairs'][spec['pair']]
        seats = (second, first) if spec['swap'] else (first, second)
        return match, [seats[0].for_player(0), seats[1].for_player(1)], [d.name for d in seats]
    from gwentsim.data import load_match
    match = load_match(spec['record'])
    decks = list(reversed(match.decks)) if spec['swap'] else match.decks
    return match, decks, [d.deck_name for d in decks]


def play(spec, override=None, branch=None):
    """Run one match; record every candidate search.

    override=(index, action) forces one candidate decision; branch=(index, k) switches to luck
    stream k right after that decision."""
    match, decks, names = match_setup(spec)
    seat, profile = spec['seat'], PROFILES.index(spec['profile'])
    log = []
    original = ResponseV8AIPlayerController.search

    def search(controller, position, context):
        result = original(controller, position, context)
        if controller.playerID != seat:
            return result
        index = len(log)
        if override is not None and override[0] == index:
            forced = override[1]
            result = replace(result, action=forced, reason='forced_alternative')
        if branch is not None and branch[0] == index:
            source.branch(*branch)
        log.append(dict(position=position, context=context, result=result))
        return result

    source = BranchRandom(spec['seed'])
    ResponseV8AIPlayerController.search = search
    try:
        if spec['source'] == 'player':
            # Player side played by response-v8 too (strong stand-in for a human); only the
            # NPC seat's decisions are logged and judged (see search() above).
            _, flow = run_match(match.templates.values(), decks, match.card_values, source,
                                coin_toss_choice=lambda: True, candidate_profile=profile,
                                seat_policies=tuple(spec.get('policy', 'response-v8') if p == seat else 'response-v8'
                                                    for p in (0, 1)))
        else:
            _, flow = run_match(match.templates.values(), decks, match.card_values, source,
                                coin_toss_choice=lambda: True, candidate_player=seat,
                                candidate_policy=spec.get('policy', 'response-v8'), candidate_profile=profile)
    finally:
        ResponseV8AIPlayerController.search = original
    rounds = [[r.getPlayerScore(0), r.getPlayerScore(1)] for r in flow.cardManager.roundResults if r.played]
    return dict(winner=flow.gameWinner, rounds=rounds, decks=names), log


def outcome(winner, seat):
    return 1.0 if winner == seat else 0.5 if winner not in (0, 1) else 0.0


def alternatives(entry):
    result = entry['result']
    chosen = result.action
    out = []
    for alt in result.alternatives or ():
        action = alternative_action(alt['action'])
        if action != chosen:
            out.append(action)
        if len(out) >= MAX_ALTERNATIVES:
            break
    if chosen is not None:
        out.append(None)  # passing instead
    return out


def option_value(spec, index, action, need=None):
    """Mean result (0..1) of playing `action` at decision `index`, over luck continuations.

    need: the mean this option must reach to matter. Once even winning every remaining
    continuation cannot reach it, stop early and return None (the option cannot become a
    finding, so findings are identical to the full evaluation). Returns (mean, rounds, plays)."""
    total = 0.0; rounds = None
    for k in range(CONTINUATIONS):
        res, _ = play(spec, (index, action), (index, k))
        total += outcome(res['winner'], spec['seat'])
        rounds = rounds or res['rounds']
        if need is not None and (total + CONTINUATIONS - k - 1) / CONTINUATIONS < need - 1e-9:
            return None, rounds, k + 1
    return total / CONTINUATIONS, rounds, CONTINUATIONS


def hunt(spec):
    """Returns dict(result, findings). Only losses/draws are searched for costly mistakes."""
    base, log = play(spec)
    seat = spec['seat']
    score = outcome(base['winner'], seat)
    report = dict(spec=spec, result=base, score=score, decisions=len(log), findings=[], replays=0)
    if score >= 1.0:
        return report
    for index, entry in enumerate(log):
        position, context, result = entry['position'], entry['context'], entry['result']
        options = alternatives(entry)
        if not options:
            continue
        try:
            chosen_value, chosen_rounds, plays = option_value(spec, index, result.action)
        except Exception as exc:
            report.setdefault('skipped', []).append('%s: %s' % (type(exc).__name__, exc)); continue
        report['replays'] += plays
        need = chosen_value + MIN_REGRET
        if need > 1.0 + 1e-9:
            continue  # no alternative can beat the chosen move by MIN_REGRET
        best = None
        for action in options:
            try:
                value, rounds, plays = option_value(spec, index, action, need)
            except Exception as exc:  # an illegal/unsupported forced move is skipped, not a finding
                report.setdefault('skipped', []).append('%s: %s' % (type(exc).__name__, exc)); continue
            report['replays'] += plays
            if value is not None and (best is None or value > best[0]):
                best = (value, action, rounds)
        if best is not None and best[0] - chosen_value >= MIN_REGRET:
            scores = position.scores()
            report['findings'].append(dict(
                decision=index, round=context.round_index + 1,
                ownScore=scores[seat], opponentScore=scores[1 - seat],
                ownHand=len(position.hand), opponentHand=context.opponent_hand_count,
                opponentPassed=context.opponent_passed, ownLosses=context.own_losses,
                chosen=describe(position, result.action), chosenReason=result.reason, chosenValue=chosen_value,
                better=describe(position, best[1]), betterValue=best[0], regret=best[0] - chosen_value,
                originalRounds=base['rounds']))
    return report


# ---- Deep hunt (additive; `hunt` above is unchanged) ---------------------------------
# Covers what the plain hunt cannot: won matches, smaller mistakes and moves the policy
# never ranked. Every option at a decision is compared on the SAME luck streams (common
# random numbers, as in duplicate poker), the field of candidates is narrowed with
# Sequential Halving (Karnin et al. 2013, the root selection of Gumbel MuZero), and a
# finding needs a paired mean gain of DEEP_MIN_REGRET over DEEP_FINAL continuations.
DEEP_SCREEN = 4            # chosen move first: if it wins every screen stream, nothing to gain
DEEP_FIRST = 2             # continuations per candidate in the first halving round
DEEP_FINAL = 16            # continuations for the final paired comparison
DEEP_MIN_REGRET = 0.25


def all_options(entry):
    """The chosen move, every modelled legal move, the policy's ranked alternatives and a pass."""
    position, result = entry['position'], entry['result']
    seen, out = set(), []
    def add(action):
        key = repr(action)
        if key not in seen:
            seen.add(key); out.append(action)
    add(result.action)
    try:
        for action in position.actions():
            add(action)
    except Exception:
        pass
    for alt in result.alternatives or ():
        add(alternative_action(alt['action']))
    add(None)
    return out


def deep_decision(spec, index, chosen, options, report):
    """Sequential Halving with cached, shared luck streams. Returns a finding dict or None."""
    seat = spec['seat']
    cache = {}

    def sample(action, k):
        key = (repr(action), k)
        if key not in cache:
            res, _ = play(spec, (index, action), (index, k))
            cache[key] = outcome(res['winner'], seat)
            report['replays'] += 1
        return cache[key]

    def mean(action, n):
        return sum(sample(action, k) for k in range(n)) / n

    if mean(chosen, DEEP_SCREEN) >= 1.0:
        return None                     # already wins with every screened luck stream
    alive = [a for a in options if repr(a) != repr(chosen)]
    n = DEEP_FIRST
    while len(alive) > 1 and n < DEEP_FINAL:
        scored = []
        for action in alive:
            try:
                scored.append((mean(action, n), action))
            except Exception as exc:    # illegal/unsupported forced move: dropped, not a finding
                report.setdefault('skipped', []).append('%s: %s' % (type(exc).__name__, exc))
        scored.sort(key=lambda item: -item[0])
        alive = [a for _, a in scored[:max(1, (len(scored) + 1) // 2)]]
        n *= 2
    if not alive:
        return None
    best = alive[0]
    try:
        best_value = mean(best, DEEP_FINAL)
    except Exception as exc:
        report.setdefault('skipped', []).append('%s: %s' % (type(exc).__name__, exc)); return None
    chosen_value = mean(chosen, DEEP_FINAL)
    if best_value - chosen_value < DEEP_MIN_REGRET - 1e-9:
        return None
    better = sum(sample(best, k) > sample(chosen, k) for k in range(DEEP_FINAL))
    worse = sum(sample(best, k) < sample(chosen, k) for k in range(DEEP_FINAL))
    return dict(best=best, chosenValue=chosen_value, betterValue=best_value,
                regret=best_value - chosen_value, pairedBetter=better, pairedWorse=worse,
                candidates=len(options), continuations=DEEP_FINAL)


def deep_hunt(spec):
    """Like hunt(), for every match (won ones too) and every modelled legal move."""
    base, log = play(spec)
    seat = spec['seat']
    score = outcome(base['winner'], seat)
    report = dict(spec=spec, result=base, score=score, decisions=len(log), findings=[], replays=0)
    for index, entry in enumerate(log):
        position, context, result = entry['position'], entry['context'], entry['result']
        options = all_options(entry)
        if len(options) < 2:
            continue
        try:
            found = deep_decision(spec, index, result.action, options, report)
        except Exception as exc:
            report.setdefault('skipped', []).append('%s: %s' % (type(exc).__name__, exc)); continue
        if found:
            scores = position.scores()
            report['findings'].append(dict(
                decision=index, round=context.round_index + 1,
                ownScore=scores[seat], opponentScore=scores[1 - seat],
                ownHand=len(position.hand), opponentHand=context.opponent_hand_count,
                opponentPassed=context.opponent_passed, ownLosses=context.own_losses,
                chosen=describe(position, result.action), chosenReason=result.reason,
                chosenValue=found['chosenValue'], better=describe(position, found['best']),
                betterValue=found['betterValue'], regret=found['regret'],
                pairedBetter=found['pairedBetter'], pairedWorse=found['pairedWorse'],
                candidates=found['candidates'], continuations=found['continuations'],
                originalRounds=base['rounds'], matchScore=score))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=int, default=0)
    parser.add_argument('--seed', type=int, default=600)
    parser.add_argument('--swap', action='store_true')
    parser.add_argument('--seat', type=int, default=0)
    parser.add_argument('--profile', choices=PROFILES, default='hard')
    args = parser.parse_args()
    spec = dict(source='pool', pair=args.pair, seed=args.seed, swap=args.swap, seat=args.seat, profile=args.profile)
    print(json.dumps(hunt(spec), indent=1, default=str))
