"""Simulator-only round planner layered over the unmodified vanilla controller."""
from dataclasses import asdict
from math import isfinite

from .. import constants as C
from ..round_policy import HandEstimate, RoundObservation, decide_pass
from .ai_player_controller import AIPlayerController, TACTIC_PASS
from .base_player_controller import ROUND_PLAYER_STATUS_DONE
from .card_manager import CardManager


class PlanningAIPlayerController(AIPlayerController):
    def __init__(self, fsm_name='Planning AI'):
        super().__init__(fsm_name)
        self.policy_decisions = []

    def state_begin_ChoseMove(self):
        super().state_begin_ChoseMove()
        cm = CardManager.getInstance()
        player, opponent = self.playerID, self.opponentID
        hand = cm.getCardInstanceList(cm.CARD_LIST_LOC_HAND, player)
        tx = self._decidedCardTransaction
        source = tx.sourceCardInstanceRef if tx else None
        # Hand identities are private to this player; only the other hand's count
        # is observed. Native estimates consult own cards and the public board.
        own_faction = cm.playerDeckDefinitions[player].getDeckFaction()
        other_faction = cm.playerDeckDefinitions[opponent].getDeckFaction()
        estimates = tuple(HandEstimate(
            gain=max(0, card.getOptimalTransaction().powerChangeResult),
            reserve_value=max(0, card.templateRef.power)) for card in hand)
        state = RoundObservation(
            round_index=self.gameFlowControllerRef.currentRound,
            own_losses=sum(r.played and r.winningPlayer != player for r in cm.roundResults),
            opponent_losses=sum(r.played and r.winningPlayer != opponent for r in cm.roundResults),
            score=cm.currentPlayerScores[player], opponent_score=cm.currentPlayerScores[opponent],
            wins_ties=own_faction == C.FactionId_Nilfgaard and other_faction != own_faction,
            opponent_passed=self.gameFlowControllerRef.playerControllers[opponent].currentRoundStatus == ROUND_PLAYER_STATUS_DONE,
            opponent_hand_count=len(cm.getCardInstanceList(cm.CARD_LIST_LOC_HAND, opponent)),
            hand=estimates,
            leader_available=bool(cm.getCardLeader(player) and cm.getCardLeader(player).canBeUsed),
            resource_action=bool(source and any(source.templateRef.hasEffect(effect) for effect in (
                C.CardEffect_Draw2, C.CardEffect_UnsummonDummy, C.CardEffect_Nurse,
                C.CardEffect_Draw, C.CardEffect_Resurect, C.CardEffect_Resurect_Enemy,
                C.CardEffect_Bin2_Pick1, C.CardEffect_SuicideSummon))))
        decision = self.decide_round_pass(state)
        audit = asdict(decision)
        if not isfinite(audit['estimated_chase_cards']):
            audit['estimated_chase_cards'] = None
        audit.update(player=player, observation=asdict(state),
                     changed=decision.override and tx is not None,
                     vanilla_source=None if source is None else [source.templateId, source.instanceId])
        self.policy_decisions.append(audit)
        if decision.override:
            self.attitude = TACTIC_PASS
            self._decidedCardTransaction = None

    def decide_round_pass(self, state):
        return decide_pass(state)
