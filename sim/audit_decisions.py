#!/usr/bin/env python3
"""Pattern audit of the NPC's V8 decisions (diagnostic only).

Simulated NPC-vs-player matches are played with the shipped AI; every NPC decision is checked
against patterns of the mistakes seen in game (weather that changes nothing, clearing weather
for a loss, playing on with a lead that no hand can overtake after a lost round, ignoring a
card publicly back in the player's hand, keeping the weather card the leader can pull, a
play that lowers the score difference, falling back to the native AI). A sample of every
pattern is then judged: the flagged move and the fix are both played to the end with the real
hidden cards (as blunder_hunter does), so a pattern counts as a mistake only when the fix
does better.

    python3 sim/audit_decisions.py --pairs 0-499 --step 5 --seed 401 --profile hard --decks balanced \
        [--faction 5] [--judge 20] [--jobs 10] --output report.json
"""
import argparse
import json
import multiprocessing
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import blunder_hunter as bh  # noqa: E402
from gwentsim import constants as C  # noqa: E402
from gwentsim import response_v8  # noqa: E402
from gwentsim.gwint.card_manager import CardManager  # noqa: E402
from gwentsim.gwint.sequence_ai_controller import ResponseV8AIPlayerController  # noqa: E402
from gwentsim.known_hand import known_templates  # noqa: E402
from gwentsim.npc_balance import LEADER_PICK  # noqa: E402
from gwentsim.position import UnsupportedPosition  # noqa: E402

FALLBACK = ('no_supported_plan', 'insufficient_public_catalog', 'native_unsupported_choice')


def gain(position, action):
    try:
        after = position.apply(action)
    except (UnsupportedPosition, ValueError):
        return None
    own, other = position.player, 1 - position.player
    b, a = position.scores(), after.scores()
    return (a[own] - a[other]) - (b[own] - b[other])


def patterns(entry):
    """Names of the mistake patterns this decision matches, with the fix to judge."""
    position, context, result = entry['position'], entry['context'], entry['result']
    action = result.action; out = []
    if result.reason in FALLBACK and not (context.opponent_passed and not response_v8.secured(position, context)
                                          and len(position.hand) <= 1):
        out.append(('native-fallback', None))   # a lost ending with one card left is not counted
    if action is None:
        return out
    card = position.cards.get(action.source)
    leader = action.source == (position.leaders or {}).get(position.player)
    g = gain(position, action)
    spy = card is not None and card.is_type(C.CardType_Spy)
    if card is not None and card.is_type(C.CardType_Weather) and not leader:
        if card.has(C.CardEffect_ClearSky):
            if g is not None and g <= 0:
                out.append(('clear-weather-loss', 'best-other'))
        elif g is not None and g <= 0:
            out.append(('weather-no-gain', 'best-other'))
    if g is not None and g < 0 and not spy and not (card is not None and card.has(C.CardEffect_UnsummonDummy)):
        out.append(('negative-play', 'best-other'))
    if not spy and not context.opponent_passed and response_v8.safe_lead_pass(position, context):
        out.append(('lead-overplay', 'pass'))
    if not spy and not context.opponent_passed and len(position.hand) == 1 and context.round_index < 2 \
            and response_v8.secured(position, context) and context.own_losses:
        out.append(('last-card-on-lead', 'pass'))
    if entry.get('known'):
        out.append(('known-card-ignored', 'known'))
    if entry.get('first') and entry.get('leader_weather_kept'):
        out.append(('leader-weather-kept', None))
    return out


def collect(spec):
    """Play one match and return its NPC decisions with pattern flags (picklable summary)."""
    seat = spec['seat']; extra = []
    original = ResponseV8AIPlayerController.search

    def search(controller, position, context):
        result = original(controller, position, context)
        if controller.playerID == seat:
            cm = CardManager.getInstance(); known = known_templates(cm, 1 - seat)
            info = dict(known=False, first=not extra)
            if known:
                saved = response_v8.VARIANT
                response_v8.VARIANT = frozenset(saved | {'known-hand'})
                try:
                    with_known = original(controller, position, replace(context, opponent_known=known))
                finally:
                    response_v8.VARIANT = saved
                info['known'] = with_known.action != result.action
                info['known_action'] = with_known.action
            if not extra:
                leader = cm.getCardLeader(seat)
                weather = LEADER_PICK.get(leader.templateRef.getFirstEffect()) if leader else None
                info['leader_weather_kept'] = weather is not None and leader.canBeUsed and any(
                    position.cards[k].effects[:1] == (weather,) for k in position.hand)
            extra.append(info)
        return result
    ResponseV8AIPlayerController.search = search
    try:
        base, log = bh.play(spec)
    finally:
        ResponseV8AIPlayerController.search = original
    decisions = []
    for index, (entry, info) in enumerate(zip(log, extra)):
        entry = dict(entry, **info)
        found = patterns(entry)
        if found:
            decisions.append(dict(index=index, patterns=found, round=entry['context'].round_index,
                                  chosen=bh.describe(entry['position'], entry['result'].action),
                                  reason=entry['result'].reason,
                                  known_action=info.get('known_action')))
    return dict(spec=spec, winner=base['winner'], decisions=len(log), flagged=decisions, decks=base['decks'])


def fix_action(spec, index, kind, flagged):
    _, log = bh.play(spec)
    entry = log[index]; position, result = entry['position'], entry['result']
    if kind == 'pass':
        return None
    if kind == 'known':
        return flagged['known_action']
    for alt in result.alternatives or ():
        action = response_v8.alternative_action(alt['action'])
        if action == result.action:
            continue
        g = gain(position, action)
        card = position.cards.get(action.source)
        if g is not None and g > 0 and not (card is not None and card.is_type(C.CardType_Weather) and g <= 0):
            return action
    return None


def judge(task):
    spec, flagged, name, kind = task
    index = flagged['index']
    _, log = bh.play(spec)
    chosen = log[index]['result'].action
    fix = fix_action(spec, index, kind, flagged)
    a, ra, _ = bh.option_value(spec, index, chosen)
    b, rb, _ = bh.option_value(spec, index, fix)
    return dict(pattern=name, spec=spec, index=index, chosen=flagged['chosen'],
                fix=bh.describe(log[index]['position'], fix), chosenValue=a, fixValue=b)


def parse_pairs(text):
    a, _, b = text.partition('-')
    return range(int(a), int(b or a) + 1)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pairs', default='0-499')
    ap.add_argument('--step', type=int, default=1)
    ap.add_argument('--seed', type=int, default=401)
    ap.add_argument('--profile', default='hard')
    ap.add_argument('--decks', default='balanced')
    ap.add_argument('--faction', type=int, help='only matchups where the NPC or the player has this faction')
    ap.add_argument('--judge', type=int, default=20, help='flagged decisions judged per pattern')
    ap.add_argument('--jobs', type=int, default=10)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(argv)
    from evaluate_pool import player_setup
    setups = player_setup()
    specs = []
    for pair in list(parse_pairs(args.pairs))[::args.step]:
        npc, player = setups[pair]
        if args.faction is not None and args.faction not in (npc.faction, player.faction):
            continue
        for swap in (False, True):
            specs.append(dict(source='player', pair=pair, seed=args.seed, swap=swap, seat=0 if swap else 1,
                              profile=args.profile, npc_decks=args.decks,
                              npcFaction=npc.faction, playerFaction=player.faction))
    with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
        matches = pool.map(collect, specs, chunksize=1)
        by_pattern = defaultdict(list)
        for m in matches:
            for d in m['flagged']:
                for name, kind in d['patterns']:
                    by_pattern[name].append((m['spec'], d, name, kind))
        tasks = [t for name, items in by_pattern.items() for t in items[:args.judge] if t[3] is not None]
        judged = pool.map(judge, tasks, chunksize=1)
    decisions = sum(m['decisions'] for m in matches)
    counts = Counter(name for items in by_pattern.values() for _, _, name, _ in items)
    per_faction = defaultdict(Counter)
    for m in matches:
        npc_faction = m['spec']['npcFaction'] if not m['spec']['swap'] else m['spec']['npcFaction']
        per_faction[npc_faction]['decisions'] += m['decisions']
        for d in m['flagged']:
            for name, _ in d['patterns']:
                per_faction[npc_faction][name] += 1
    summary = {}
    for name in counts:
        rows = [j for j in judged if j['pattern'] == name]
        summary[name] = dict(count=counts[name], perThousandDecisions=1000.0 * counts[name] / max(1, decisions),
                             judged=len(rows), fixBetter=sum(r['fixValue'] > r['chosenValue'] for r in rows),
                             fixWorse=sum(r['fixValue'] < r['chosenValue'] for r in rows),
                             meanGain=sum(r['fixValue'] - r['chosenValue'] for r in rows) / len(rows) if rows else None)
    report = dict(args={k: str(v) for k, v in vars(args).items()}, matches=len(matches), decisions=decisions,
                  npcWins=sum(m['winner'] == m['spec']['seat'] for m in matches), summary=summary,
                  perNpcFaction={str(k): dict(v) for k, v in per_faction.items()}, judged=judged,
                  examples={name: [dict(spec=s, decision=d) for s, d, _, _ in items[:5]] for name, items in by_pattern.items()})
    args.output.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(dict(matches=len(matches), decisions=decisions, summary=summary,
                          perNpcFaction=report['perNpcFaction']), indent=1, default=str))


if __name__ == '__main__':
    main(sys.argv[1:])
