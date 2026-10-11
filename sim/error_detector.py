#!/usr/bin/env python3
"""Diagnostic error detector: compares V7 decisions against a full-information oracle.

This tool is strictly diagnostic. The cheating oracle inspects the true cards of both
players only to categorize blunders (e.g. overplaying after an opponent pass, passing
when able to win, self-destructive scorch/weather, or wasting cards in an unwinnable round).
The actual AI never accesses opponent private information.
"""
import argparse
import glob
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import patch

from gwentsim import constants as C
from gwentsim.data import load_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.gwint_game_flow_controller import GwintGameFlowController
from gwentsim.gwint.base_player_controller import ROUND_PLAYER_STATUS_DONE
from gwentsim.gwint.ai_player_controller import TACTIC_PASS
from gwentsim.gwint.match import run_match
from gwentsim.gwint.headless import SimulationStall
from gwentsim.position import Position, UnsupportedPosition, ROWS
from gwentsim.rng import SeededRandom

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Blunder:
    error_type: str
    record: str
    seed: int
    swap: bool
    round_index: int
    turn_index: int
    player: int
    score_own: int
    score_opp: int
    hand_count_own: int
    hand_count_opp: int
    opponent_passed: bool
    v7_decision: str
    oracle_recommendation: str
    severity: str
    details: Dict[str, Any]

    def to_dict(self):
        return asdict(self)


def calculate_max_possible_points(position: Position) -> int:
    """Generous upper bound on points V7 can gain from all cards in hand."""
    total = 0
    hand_cards = [position.cards[k] for k in position.hand]
    has_horn = any(c.has(C.CardEffect_Horn) or c.has(C.CardEffect_Melee_Horn) or 
                   c.has(C.CardEffect_Range_Horn) or c.has(C.CardEffect_Siege_Horn) for c in hand_cards)
    multiplier = 2 if has_horn else 1

    for card in hand_cards:
        if card.is_type(C.CardType_Creature):
            # Optimistic multiplier (Bond / Morale / Horn)
            total += card.power * 2 * multiplier + 2
        elif card.has(C.CardEffect_Clear_Weather):
            total += 30
        elif card.has(C.CardEffect_Scorch):
            total += 15
    return total


def check_scorch_outcome(position: Position, action) -> Dict[str, Any]:
    own = position.player
    other = 1 - own
    card = position.cards[action.source]
    is_global_scorch = card.has(C.CardEffect_Scorch)
    is_row_scorch = any(card.has(e) for e in (C.CardEffect_MeleeScorch, C.CardEffect_RangedScorch, C.CardEffect_Siege_Scorch))
    
    if not (is_global_scorch or is_row_scorch):
        return {"is_scorch": False}

    before_scores = position.scores()
    try:
        after = position.apply(action)
        after_scores = after.scores()
    except UnsupportedPosition:
        return {"is_scorch": True, "unsupported": True}

    friendly_destroyed = [k for row in ROWS for k in position.board[own, row] if k not in after.board[own, row]]
    enemy_destroyed = [k for row in ROWS for k in position.board[other, row] if k not in after.board[other, row]]

    friendly_power_loss = sum(position.power(k) for k in friendly_destroyed)
    enemy_power_loss = sum(position.power(k) for k in enemy_destroyed)
    net_swing = (after_scores[own] - before_scores[own]) - (after_scores[other] - before_scores[other])

    self_destructive = (len(friendly_destroyed) > 0 and len(enemy_destroyed) == 0) or (net_swing < 0) or (friendly_power_loss > enemy_power_loss)
    return {
        "is_scorch": True,
        "self_destructive": self_destructive,
        "friendly_destroyed": len(friendly_destroyed),
        "enemy_destroyed": len(enemy_destroyed),
        "friendly_loss": friendly_power_loss,
        "enemy_loss": enemy_power_loss,
        "net_swing": net_swing
    }


def check_weather_outcome(position: Position, action) -> Dict[str, Any]:
    own = position.player
    other = 1 - own
    card = position.cards[action.source]
    if not card.is_type(C.CardType_Weather):
        return {"is_weather": False}

    before_scores = position.scores()
    try:
        after = position.apply(action)
        after_scores = after.scores()
    except UnsupportedPosition:
        return {"is_weather": True, "unsupported": True}

    own_delta = after_scores[own] - before_scores[own]
    opp_delta = after_scores[other] - before_scores[other]
    net_swing = own_delta - opp_delta

    self_destructive = net_swing < 0 and own_delta < -2
    return {
        "is_weather": True,
        "self_destructive": self_destructive,
        "own_delta": own_delta,
        "opp_delta": opp_delta,
        "net_swing": net_swing
    }


class DiagnosticDetector:
    def __init__(self, record_name: str, seed: int, swap: bool):
        self.record_name = record_name
        self.seed = seed
        self.swap = swap
        self.blunders: List[Blunder] = []
        self.decisions_count = 0

    def inspect_decision(self, controller, position: Position, context, result):
        cm = CardManager.getInstance()
        flow = GwintGameFlowController.getInstance()
        player = controller.playerID
        other = controller.opponentID
        turn = self.decisions_count
        self.decisions_count += 1

        score_own = cm.currentPlayerScores[player]
        score_opp = cm.currentPlayerScores[other]
        opp_passed = flow.playerControllers[other].currentRoundStatus == ROUND_PLAYER_STATUS_DONE
        current_round = flow.currentRound

        round_wins_own = sum(r.played and r.winningPlayer == player for r in cm.roundResults)
        round_wins_opp = sum(r.played and r.winningPlayer == other for r in cm.roundResults)
        elimination_round = (round_wins_opp == 1 and round_wins_own == 0) or (current_round == 2)

        faction_own = cm.playerDeckDefinitions[player].getDeckFaction()
        faction_opp = cm.playerDeckDefinitions[other].getDeckFaction()
        wins_ties = (faction_own == C.FactionId_Nilfgaard and faction_opp != faction_own)

        # Did V7 decide to pass or play?
        action = result.action
        passed = (action is None or result.reason in ('pass_for_match_resources', 'proven_no_supported_overtake'))

        # 1. OVERPLAY_AFTER_OPPONENT_PASSED
        if opp_passed and (score_own > score_opp or (score_own == score_opp and wins_ties)):
            if not passed and action is not None:
                source_card = position.cards.get(action.source)
                is_spy = source_card and source_card.is_type(C.CardType_Spy)
                if not is_spy:
                    self.blunders.append(Blunder(
                        error_type="OVERPLAY_AFTER_OPPONENT_PASSED",
                        record=self.record_name,
                        seed=self.seed,
                        swap=self.swap,
                        round_index=current_round,
                        turn_index=turn,
                        player=player,
                        score_own=score_own,
                        score_opp=score_opp,
                        hand_count_own=len(position.hand),
                        hand_count_opp=len(cm.getCardInstanceList(1, other)),
                        opponent_passed=True,
                        v7_decision=f"played card {source_card.template if source_card else 'unknown'} (power={source_card.power if source_card else 0})",
                        oracle_recommendation="pass (round already won, card wasted)",
                        severity="major",
                        details={"wasted_card": source_card.template if source_card else None,
                                 "wasted_power": source_card.power if source_card else 0}
                    ))
                    return

        # 2. PASSED_WHEN_COULD_WIN
        if passed and (score_own < score_opp or (score_own == score_opp and not wins_ties)):
            # Could V7 have overtaken with 1 card?
            can_overtake = False
            winning_card = None
            for key in position.hand:
                card = position.cards[key]
                if position.supported(card):
                    for act in position.actions():
                        if act.source == key:
                            try:
                                after = position.apply(act)
                                sc = after.scores()
                                if sc[player] > sc[other] or (sc[player] == sc[other] and wins_ties):
                                    can_overtake = True
                                    winning_card = card
                                    break
                            except UnsupportedPosition:
                                pass
                    if can_overtake:
                        break

            if can_overtake:
                self.blunders.append(Blunder(
                    error_type="PASSED_WHEN_COULD_WIN",
                    record=self.record_name,
                    seed=self.seed,
                    swap=self.swap,
                    round_index=current_round,
                    turn_index=turn,
                    player=player,
                    score_own=score_own,
                    score_opp=score_opp,
                    hand_count_own=len(position.hand),
                    hand_count_opp=len(cm.getCardInstanceList(1, other)),
                    opponent_passed=opp_passed,
                    v7_decision="passed while trailing",
                    oracle_recommendation=f"play card {winning_card.template} to win round ({score_own}->win)",
                    severity="fatal" if elimination_round else "major",
                    details={"winning_card": winning_card.template, "elimination": elimination_round}
                ))
                return

        # 3. SELF_DESTRUCTIVE_SCORCH
        if not passed and action is not None:
            scorch_info = check_scorch_outcome(position, action)
            if scorch_info.get("self_destructive"):
                card = position.cards[action.source]
                self.blunders.append(Blunder(
                    error_type="SELF_DESTRUCTIVE_SCORCH",
                    record=self.record_name,
                    seed=self.seed,
                    swap=self.swap,
                    round_index=current_round,
                    turn_index=turn,
                    player=player,
                    score_own=score_own,
                    score_opp=score_opp,
                    hand_count_own=len(position.hand),
                    hand_count_opp=len(cm.getCardInstanceList(1, other)),
                    opponent_passed=opp_passed,
                    v7_decision=f"played scorch {card.template} (net={scorch_info['net_swing']})",
                    oracle_recommendation="do not scorch own units",
                    severity="major",
                    details=scorch_info
                ))
                return

        # 4. SELF_DESTRUCTIVE_WEATHER
        if not passed and action is not None:
            weather_info = check_weather_outcome(position, action)
            if weather_info.get("self_destructive"):
                card = position.cards[action.source]
                self.blunders.append(Blunder(
                    error_type="SELF_DESTRUCTIVE_WEATHER",
                    record=self.record_name,
                    seed=self.seed,
                    swap=self.swap,
                    round_index=current_round,
                    turn_index=turn,
                    player=player,
                    score_own=score_own,
                    score_opp=score_opp,
                    hand_count_own=len(position.hand),
                    hand_count_opp=len(cm.getCardInstanceList(1, other)),
                    opponent_passed=opp_passed,
                    v7_decision=f"played weather {card.template} (net={weather_info['net_swing']})",
                    oracle_recommendation="do not play weather against own board",
                    severity="major",
                    details=weather_info
                ))
                return

        # 5. CHASED_UNWINNABLE_ROUND
        if opp_passed and (score_own < score_opp) and not passed and action is not None:
            max_possible = score_own + calculate_max_possible_points(position)
            if max_possible < score_opp:
                card = position.cards.get(action.source)
                self.blunders.append(Blunder(
                    error_type="CHASED_UNWINNABLE_ROUND",
                    record=self.record_name,
                    seed=self.seed,
                    swap=self.swap,
                    round_index=current_round,
                    turn_index=turn,
                    player=player,
                    score_own=score_own,
                    score_opp=score_opp,
                    hand_count_own=len(position.hand),
                    hand_count_opp=len(cm.getCardInstanceList(1, other)),
                    opponent_passed=True,
                    v7_decision=f"played {card.template if card else 'card'} in unwinnable chase (max={max_possible} vs opp={score_opp})",
                    oracle_recommendation="pass immediately to save hand for subsequent rounds",
                    severity="major",
                    details={"max_possible": max_possible, "target": score_opp}
                ))
                return


def analyze_match(path, seed, swap=False, seat=0, policy='response-v6', profile=2):
    """Executes a match with the DiagnosticDetector attached to V7."""
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController

    detector = DiagnosticDetector(Path(path).name, seed, swap)
    original_search = ResponseAIPlayerController.search

    def hooked_search(self, position, context):
        res = original_search(self, position, context)
        if self.playerID == seat:
            detector.inspect_decision(self, position, context, res)
        return res

    match = load_match(path)
    decks = list(reversed(match.decks)) if swap else match.decks
    random = SeededRandom(seed)

    with patch.object(ResponseAIPlayerController, 'search', hooked_search):
        recorder, flow = run_match(
            match.templates.values(), decks, match.card_values, random,
            coin_toss_choice=lambda: True, candidate_player=seat,
            candidate_policy=policy, candidate_profile=profile
        )

    won = (flow.gameWinner == seat)
    rounds = [{'scores': [r.getPlayerScore(0), r.getPlayerScore(1)], 'winner': r.winningPlayer}
              for r in flow.cardManager.roundResults if r.played]

    return {
        "record": Path(path).name,
        "seed": seed,
        "swap": swap,
        "seat": seat,
        "winner": flow.gameWinner,
        "won": won,
        "rounds": rounds,
        "blunders": [b.to_dict() for b in detector.blunders],
        "blunders_count": len(detector.blunders)
    }


def analyze_report(report_path: Path):
    data = json.loads(report_path.read_text())
    trials = data.get('trials', [])
    blunders_by_type = {}
    matches_analyzed = 0
    total_losses = 0
    losses_with_blunders = 0
    from gwentsim.data import load_match
    # Load all template definitions
    templates_cache = {}
    for p in (ROOT / 'game/records').glob('g*.json'):
        try:
            m = load_match(p)
            templates_cache.update(m.templates)
        except Exception:
            pass

    for t in trials:
        if 'candidatePlayer' not in t:
            continue
        matches_analyzed += 1
        won = t.get('candidateWon', False)
        if not won:
            total_losses += 1

        match_blunders = []
        decisions = t.get('policyDecisions', [])
        for idx, d in enumerate(decisions):
            obs = d.get('observation', {})
            if not obs:
                continue
            round_idx = obs.get('round_index', 0)
            score_own = obs.get('score', 0)
            score_opp = obs.get('opponent_score', 0)
            opp_passed = obs.get('opponent_passed', False)
            wins_ties = obs.get('wins_ties', False)
            hand = obs.get('hand', [])

            seq = d.get('sequenceSearch', {})
            action = seq.get('action')

            # 1. OVERPLAY_AFTER_OPPONENT_PASSED (non-spy card played when already winning)
            if opp_passed and (score_own > score_opp or (score_own == score_opp and wins_ties)):
                if action is not None:
                    src = action.get('source')
                    is_spy = False
                    for u in d.get('unitEvaluations', []):
                        if u.get('card', [None, None])[1] == src:
                            tid = u['card'][0]
                            tmpl = templates_cache.get(tid)
                            if tmpl and tmpl.is_type(C.CardType_Spy):
                                is_spy = True
                                break
                    if not is_spy:
                        match_blunders.append({
                            "error_type": "OVERPLAY_AFTER_OPPONENT_PASSED",
                            "round": round_idx,
                            "turn": idx,
                            "score_own": score_own,
                            "score_opp": score_opp,
                            "hand_count": len(hand),
                            "action": action
                        })

            # 2. PASSED_WHEN_COULD_WIN
            if action is None and (score_own < score_opp or (score_own == score_opp and not wins_ties)):
                gap = score_opp - score_own if not wins_ties else score_opp - score_own - 1
                can_win = any(h.get('gain', 0) > gap for h in hand)
                if can_win:
                    match_blunders.append({
                        "error_type": "PASSED_WHEN_COULD_WIN",
                        "round": round_idx,
                        "turn": idx,
                        "score_own": score_own,
                        "score_opp": score_opp,
                        "gap": gap,
                        "hand_count": len(hand)
                    })

            # 3. CHASED_UNWINNABLE_ROUND
            if opp_passed and (score_own < score_opp) and action is not None:
                gap = score_opp - score_own
                max_gain = sum(h.get('gain', 0) for h in hand)
                if max_gain < gap:
                    match_blunders.append({
                        "error_type": "CHASED_UNWINNABLE_ROUND",
                        "round": round_idx,
                        "turn": idx,
                        "score_own": score_own,
                        "score_opp": score_opp,
                        "gap": gap,
                        "max_gain": max_gain,
                        "action": action
                    })

        if match_blunders:
            if not won:
                losses_with_blunders += 1
            for b in match_blunders:
                blunders_by_type.setdefault(b['error_type'], []).append({
                    "record": t.get('record') or t.get('pair'),
                    "seed": t.get('seed'),
                    "swapped": t.get('swapped'),
                    "seat": t.get('candidatePlayer'),
                    "won": won,
                    "blunder": b
                })

    print(f"\n=== REPORT ANALYSIS: {report_path.name} ===")
    print(f"Candidate matches analyzed: {matches_analyzed}, Losses: {total_losses}")
    total_blunders = sum(len(v) for v in blunders_by_type.values())
    print(f"Total blunders detected: {total_blunders}")
    print(f"Matches lost that had blunders: {losses_with_blunders}/{total_losses}")
    print("\nBreakdown by error type:")
    for k, v in sorted(blunders_by_type.items(), key=lambda x: len(x[1]), reverse=True):
        cost_losses = sum(1 for item in v if not item['won'])
        print(f"  - {k}: {len(v)} occurrences (in {cost_losses} lost matches)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-report', type=Path, help='analyze pre-existing evaluation JSON report')
    parser.add_argument('--records', nargs='+', default=[str(p) for p in sorted((ROOT / 'game/records').glob('g[0-9][0-9][0-9].json'))])
    parser.add_argument('--seeds', nargs='+', type=int, default=[150])
    parser.add_argument('--swap', action='store_true')
    parser.add_argument('--profile', choices=['easy', 'medium', 'hard', 'expert'], default='hard')
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--output')
    args = parser.parse_args()

    if args.from_report:
        analyze_report(args.from_report)
        return 0

    if not args.output:
        parser.error('--output is required when running matches')

    profile_idx = ['easy', 'medium', 'hard', 'expert'].index(args.profile)
    tasks = [(r, s, w, seat, 'response-v6', profile_idx)
             for r in args.records
             for s in args.seeds
             for w in ([False, True] if args.swap else [False])
             for seat in (0, 1)]

    print(f"Running error detection across {len(tasks)} matches...")
    if args.jobs > 1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
            results = pool.starmap(analyze_match, tasks, chunksize=1)
    else:
        results = [analyze_match(*t) for t in tasks]

    # Aggregate blunders
    by_type = {}
    losses_with_blunders = 0
    total_losses = sum(not r['won'] for r in results)
    total_blunders = sum(len(r['blunders']) for r in results)

    for r in results:
        if r['blunders']:
            if not r['won']:
                losses_with_blunders += 1
            for b in r['blunders']:
                by_type.setdefault(b['error_type'], []).append({
                    "record": r['record'],
                    "seed": r['seed'],
                    "swap": r['swap'],
                    "seat": r['seat'],
                    "won": r['won'],
                    "blunder": b
                })

    report = {
        "total_matches": len(results),
        "total_losses": total_losses,
        "total_blunders": total_blunders,
        "losses_with_blunders": losses_with_blunders,
        "by_type_summary": {k: len(v) for k, v in by_type.items()},
        "by_type_details": by_type,
        "matches": results
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    print("\n=== BLUNDER DETECTION REPORT ===")
    print(f"Matches analyzed: {len(results)}, Losses: {total_losses}")
    print(f"Total blunders detected: {total_blunders}")
    print(f"Matches lost that had blunders: {losses_with_blunders}/{total_losses}")
    print("\nBreakdown by error type:")
    for k, v in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
        cost_losses = sum(1 for item in v if not item['won'])
        print(f"  - {k}: {len(v)} occurrences (in {cost_losses} lost matches)")

    return 0


if __name__ == '__main__':
    main()

