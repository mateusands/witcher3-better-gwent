"""Experimental V4: distinguish current gain from next-round marginal reserve."""
from ..future_value import describe_hand, reserve_marginals
from .tactical_ai_controller import TacticalPlanningAIPlayerController
from .ai_player_controller import TACTIC_MINIMAL_WIN
from .card_manager import CardManager
from .base_player_controller import ROUND_PLAYER_STATUS_DONE
from .. import constants as C


class ReservePlanningAIPlayerController(TacticalPlanningAIPlayerController):
    def decideWhichCardToPlay(self):
        self.reserve_evaluation=None
        native=super().decideWhichCardToPlay()
        if self.attitude!=TACTIC_MINIMAL_WIN or native is None or self.gameFlowControllerRef.currentRound>=2:
            return native
        cm=CardManager.getInstance()
        opponent=self.gameFlowControllerRef.playerControllers[self.opponentID]
        if opponent.currentRoundStatus==ROUND_PLAYER_STATUS_DONE:
            return native
        hand=cm.getCardInstanceList(1,self.playerID)
        gap=cm.currentPlayerScores[self.opponentID]-cm.currentPlayerScores[self.playerID]
        marginals=reserve_marginals(describe_hand(hand,cm.cardValues))
        options=[]
        for card in hand:
            tx=card.getOptimalTransaction()
            # Preserve resource/summon/recovery policies and unsupported move effects.
            supported=any(e['card'][1]==card.instanceId for e in self.unit_evaluations) or (
                card.templateRef.isType(C.CardType_Row_Modifier) and card.templateRef.hasEffect(C.CardEffect_Horn)) or card.templateRef.isType(C.CardType_Weather)
            if supported and tx.targetSlotID!=-1 and tx.powerChangeResult>abs(gap):
                options.append((marginals[card.instanceId],tx.powerChangeResult,card.instanceId,tx))
        if not options:return native
        best=min(options,key=lambda option:option[:3])
        self.reserve_evaluation=dict(gap=gap,marginals=marginals,
            nativeSource=native.sourceCardInstanceRef.instanceId,chosenSource=best[2],
            changed=best[2]!=native.sourceCardInstanceRef.instanceId,
            scope='Own-hand normal-clear potential; unsupported reserve weights are provisional.')
        return best[3]

    def state_begin_ChoseMove(self):
        super().state_begin_ChoseMove()
        self.policy_decisions[-1]['reserveEvaluation']=self.reserve_evaluation
