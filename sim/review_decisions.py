#!/usr/bin/env python3
"""Review vanilla decisions during strict replay; flags are prompts, not optimality proofs."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import replay
from gwentsim import constants as C
from gwentsim.gwint.base_player_controller import ROUND_PLAYER_STATUS_DONE
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.gwint_game_flow_controller import GwintGameFlowController
from gwentsim.gwint.match import Recorder


def flag_decision(state):
    """Use only own decision data and public observations; no opponent card identities."""
    flags = []
    if state['transaction'] is None:
        return flags
    if state['duplicateWeather'] and state['estimatedGain'] <= 0:
        flags.append('duplicate_weather_without_estimated_gain')
    if state['opponentPassed'] and state['score'] > state['opponentScore']:
        flags.append('spending_after_opponent_passed_while_ahead')
    can_concede = state['roundIndex'] == 1 and state['roundWins'] == 1 and state['opponentRoundWins'] == 0
    if can_concede and state['spendsHandCard'] and state['handCount'] <= 2:
        flags.append('round_two_reserve_at_risk')
    if state['spendsHandCard'] and state['handCount'] == 1 and state['score'] < state['opponentScore'] and state['estimatedGain'] <= 0:
        flags.append('last_hand_card_without_estimated_gap_reduction')
    return flags


def capture(event, index):
    cm = CardManager.getInstance()
    flow = GwintGameFlowController.getInstance()
    player = event['player']
    other = 1 - player
    hand = cm.getCardInstanceList(cm.CARD_LIST_LOC_HAND, player)
    tx = event['tx']
    source = cm.getCardInstance(tx['source'][1]) if tx else None
    weather = cm.getCardInstanceList(cm.CARD_LIST_LOC_WEATHERSLOT, -1)
    state = dict(eventIndex=index, player=player, roundIndex=flow.currentRound,
                 roundWins=sum(r.played and r.winningPlayer == player for r in cm.roundResults),
                 opponentRoundWins=sum(r.played and r.winningPlayer == other for r in cm.roundResults),
                 score=cm.currentPlayerScores[player], opponentScore=cm.currentPlayerScores[other],
                 handCount=len(hand), opponentHandCount=len(cm.getCardInstanceList(cm.CARD_LIST_LOC_HAND, other)),
                 opponentPassed=flow.playerControllers[other].currentRoundStatus == ROUND_PLAYER_STATUS_DONE,
                 tactic=event['attitude'], transaction=tx,
                 spendsHandCard=source in hand if source else False,
                 duplicateWeather=bool(source and source.templateRef.isType(C.CardType_Weather) and
                                       any(c.templateId == source.templateId for c in weather)),
                 estimatedGain=tx['powerChange'] if tx else 0)
    # These are the vanilla cached estimates, not counterfactual rollouts or oracle scores.
    state['ownHandCandidates'] = [dict(card=[c.templateId, c.instanceId],
                                      estimatedGain=c.getOptimalTransaction().powerChangeResult,
                                      strategic=c.getOptimalTransaction().strategicValue)
                                   for c in hand]
    state['flags'] = flag_decision(state)
    return state


def review(path):
    decisions = []
    index = 0
    original = Recorder._emit

    def observed(recorder, event):
        nonlocal index
        if event['k'] == 'A':
            decisions.append(capture(event, index))
        index += 1
        return original(recorder, event)

    with patch.object(Recorder, '_emit', observed):
        match, compared, divergence = replay.replay(str(path))
    return dict(record=Path(path).name, status='exact_replay' if divergence is None else 'diverged',
                comparedEvents=compared, totalEvents=len(match.events),
                divergence=None if divergence is None else dict(eventIndex=divergence.index, detail=divergence.detail),
                scope='Vanilla decision review. Flags are heuristic concerns, not proofs of optimal alternatives.',
                decisions=decisions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = review(args.record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('%s: %s, %d decisions, %d flagged; report %s' % (
        report['record'], report['status'], len(report['decisions']),
        sum(bool(d['flags']) for d in report['decisions']), args.output))
    return int(report['divergence'] is not None)


if __name__ == '__main__':
    raise SystemExit(main())
