"""Experimental V3: exact supported row gains and guarded combination-aware passing."""
from dataclasses import asdict

from .. import constants as C
from ..round_policy import decide_pass, PassDecision
from ..unit_evaluation import supported_unit, unit_alternatives
from .horn_ai_controller import HornPlanningAIPlayerController
from .card_manager import CardManager
from .small import CardTransaction


class TacticalPlanningAIPlayerController(HornPlanningAIPlayerController):
    def ChooseAttitude(self):
        manager = CardManager.getInstance()
        hand = manager.getCardInstanceList(1, self.playerID)
        self.unit_evaluations = []
        self.combo_extra = 0
        self.combo_coverage_complete = all(supported_unit(c) or (
            c.templateRef.isType(C.CardType_Row_Modifier) and c.templateRef.hasEffect(C.CardEffect_Horn))
            or (c.templateRef.isType(C.CardType_Weather) and not c.templateRef.hasEffect(C.CardEffect_ClearSky)) for c in hand)
        for card in hand:
            alternatives = unit_alternatives(manager, card, self.playerID)
            if not alternatives:
                continue
            old = card.getOptimalTransaction()
            best = max(alternatives, key=lambda option: option.gain)
            tx = CardTransaction()
            tx.sourceCardInstanceRef, tx.targetPlayerID = card, self.playerID
            tx.targetSlotID, tx.powerChangeResult = best.row, best.gain
            tx.strategicValue = old.strategicValue
            card._lastCalculatedPowerPotential = tx
            self.unit_evaluations.append(dict(card=[card.templateId, card.instanceId],
                vanillaGain=old.powerChangeResult, correctedGain=best.gain,
                vanillaSlot=old.targetSlotID, correctedSlot=best.row,
                alternatives=[asdict(option) for option in alternatives]))
        super().ChooseAttitude()
        # A supported two-card continuation is evidence that independent estimates
        # missed an attainable score. It does not prove that chasing is worthwhile.
        for unit in hand:
            extra = 0
            for horn in hand:
                if not horn.templateRef.isType(C.CardType_Row_Modifier) or not horn.templateRef.hasEffect(C.CardEffect_Horn):
                    continue
                for option in unit_alternatives(manager, unit, self.playerID, horn):
                    if option.horn_sequence_gain is not None:
                        independent = max(0, unit.getOptimalTransaction().powerChangeResult) + max(0, horn.getOptimalTransaction().powerChangeResult)
                        extra = max(extra, option.horn_sequence_gain - independent)
            self.combo_extra += extra
        # Multiple future Bond/morale units and weather changes need a full sequence
        # model. Do not assert impossibility from our limited two-card coverage.
        if any(any(effect != C.CardEffect_None for effect in c.templateRef.effectFlags) for c in hand if supported_unit(c)):
            self.combo_coverage_complete = False

    def decide_round_pass(self, state):
        decision = decide_pass(state)
        if decision.reason == 'preserve_round_three':
            return PassDecision(False, 'costly_chase_requires_continuation_model')
        if decision.reason == 'no_estimated_catchup':
            gap = state.opponent_score - state.score + (0 if state.wins_ties else 1)
            capacity = sum(max(0, c.gain) for c in state.hand) + self.combo_extra
            if not self.combo_coverage_complete or capacity >= gap:
                return PassDecision(False, 'possible_combination_or_unmodeled_continuation')
        return decision

    def state_begin_ChoseMove(self):
        super().state_begin_ChoseMove()
        self.policy_decisions[-1].update(unitEvaluations=self.unit_evaluations,
            comboExtra=self.combo_extra, comboCoverageComplete=self.combo_coverage_complete)
