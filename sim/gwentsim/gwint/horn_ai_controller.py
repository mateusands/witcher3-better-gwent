"""Original experimental adapter: corrected Horn estimates plus round-pass-v1."""
from dataclasses import asdict

from .. import constants as C
from ..horn_evaluation import horn_alternatives, best_horn_alternative
from .planning_ai_controller import PlanningAIPlayerController
from .card_manager import CardManager
from .small import CardTransaction


class HornPlanningAIPlayerController(PlanningAIPlayerController):
    def ChooseAttitude(self):
        # Native state_begin_ChoseMove has already recalculated the hand. Correct
        # only candidate-local Horn caches before vanilla tactical sorting.
        cm = CardManager.getInstance()
        self.horn_evaluations = []
        for card in cm.getCardInstanceList(1, self.playerID):
            if not card.templateRef.isType(C.CardType_Row_Modifier) or not card.templateRef.hasEffect(C.CardEffect_Horn):
                continue
            alternatives = horn_alternatives(cm, card, self.playerID)
            best = best_horn_alternative(alternatives)
            old = card.getOptimalTransaction()
            tx = CardTransaction()
            tx.sourceCardInstanceRef = card
            tx.targetPlayerID = self.playerID
            if best is None:
                tx.powerChangeResult, tx.strategicValue = -1, -1
            else:
                tx.targetSlotID = best.modifier_slot
                tx.powerChangeResult = best.gain
                # Retain the native strategic scale; improve measured gain/row only.
                value = cm.cardValues.hornCardValue
                tx.strategicValue = max(0, value * 2 - best.gain) if best.gain > value else value
            self.horn_evaluations.append(dict(card=[card.templateId, card.instanceId],
                vanillaGain=old.powerChangeResult, vanillaSlot=old.targetSlotID,
                correctedGain=tx.powerChangeResult, correctedSlot=tx.targetSlotID,
                alternatives=[asdict(option) for option in alternatives]))
            card._lastCalculatedPowerPotential = tx
        super().ChooseAttitude()

    def state_begin_ChoseMove(self):
        super().state_begin_ChoseMove()
        self.policy_decisions[-1]['hornEvaluations'] = self.horn_evaluations
