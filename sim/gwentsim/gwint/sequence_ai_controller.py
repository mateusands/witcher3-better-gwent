"""Simulator-only original sequence controller with unchanged native execution."""
from dataclasses import replace
from .. import constants as C
from ..position import Position
from ..sequence_search import Context,choose_sequence
from ..options import Difficulty
from .tactical_ai_controller import TacticalPlanningAIPlayerController
from .card_manager import CardManager
from .small import CardTransaction
from .ai_player_controller import TACTIC_PASS,TACTIC_MAXIMIZE_WIN
from .. import known_hand  # noqa: F401  (tracks cards returned to a hand from the board)
from .base_player_controller import ROUND_PLAYER_STATUS_DONE


class SequenceAIPlayerController(TacticalPlanningAIPlayerController):
    def __init__(self,fsm_name='Sequence AI',profile=Difficulty.HARD):
        super().__init__(fsm_name)
        self.search_profile=Difficulty(profile)

    def search(self,position,context):
        return choose_sequence(position,context,self.search_profile)

    def state_begin_ChoseMove(self):
        super().state_begin_ChoseMove()
        cm=CardManager.getInstance();own,other=self.playerID,self.opponentID
        native=self._decidedCardTransaction
        source=native.sourceCardInstanceRef if native else None
        # A plan from an earlier, unexecuted decision must never steer a later one.
        for unit in cm.getCardInstanceList(1,own):unit.__dict__.pop('candidateRecoveryPlan',None)
        leader=cm.getCardLeader(own)
        if leader:
            for name in ('candidateResurrectTarget','candidateWeatherTemplate'):leader.__dict__.pop(name,None)
        position=Position.from_manager(cm,own)
        from .. import response_v8
        # Shipped since 0.9.0 (the game's AS3 model plays the Skellige cards); "no-skellige"
        # restores the earlier model for comparisons.
        if not response_v8.flag('no-skellige',own):
            from skellige_position import SkelligePosition
            position=SkelligePosition(**position.__dict__)
        context=Context(self.gameFlowControllerRef.currentRound,
            sum(r.played and r.winningPlayer!=own for r in cm.roundResults),
            sum(r.played and r.winningPlayer!=other for r in cm.roundResults),
            self.gameFlowControllerRef.playerControllers[other].currentRoundStatus==ROUND_PLAYER_STATUS_DONE,
            len(cm.getCardInstanceList(1,other)),cm.playerDeckDefinitions[own].getDeckFaction(),
            cm.playerDeckDefinitions[other].getDeckFaction(),
            # Only leaders the model cannot search block passing / keep the
            # generic credit; modeled leaders are explicit actions and reserve.
            position.leader_unmodeled(own),position.leader_unmodeled(other))
        from .. import response_v8
        if response_v8.flag('known-hand',own):
            from ..known_hand import known_templates
            known=known_templates(cm,other)
            if known:context=replace(context,opponent_known=known)
        # An unsupported native recovery/leader choice remains executable. Search
        # must not replace it by pretending its effect does not exist.
        native_leader=source is not None and source.instanceId==position.leaders.get(own)
        if source is not None and not (native_leader and position.leader_modeled(own)) and (
                source.instanceId not in position.hand or not position.supported(position.cards[source.instanceId])):
            self.policy_decisions[-1]['sequenceSearch']=dict(reason='native_unsupported_choice',changed=False)
            return
        result=self.search(position,context)
        audit=result.audit();audit['changed']=False
        if result.reason in ('pass_for_match_resources','proven_no_supported_overtake'):
            self.attitude=TACTIC_PASS;self._decidedCardTransaction=None
            audit['changed']=native is not None
        elif result.action is not None:
            action=result.action;card=cm.getCardInstance(action.source)
            tx=CardTransaction();tx.sourceCardInstanceRef=card
            if action.source==position.leaders.get(own):
                after=position.apply(action);old_scores=position.scores();new_scores=after.scores()
                tx.powerChangeResult=new_scores[own]-old_scores[own]-new_scores[other]+old_scores[other]
                effect=position.leader_effect(own)
                if effect in (C.CardEffect_Resurect,C.CardEffect_Resurect_Enemy):card.candidateResurrectTarget=action.target
                if effect==C.CardEffect_Pick_Weather:card.candidateWeatherTemplate=action.target
                audit['leaderAction']=dict(effect=effect,slot=action.slot,target=action.target)
                audit['changed']=native is None or native.sourceCardInstanceRef is not card
                self._decidedCardTransaction=tx;self.attitude=TACTIC_MAXIMIZE_WIN
                self.policy_decisions[-1]['sequenceSearch']=audit
                return
            tx.targetSlotID=action.slot
            tx.targetPlayerID=other if card.templateRef.isType(C.CardType_Spy) else own
            # Spell Scorch only: a unit with Scorch (Clan Dimun Pirate) is placed on its own row.
            if card.templateRef.isType(C.CardType_Weather) or (card.templateRef.hasEffect(C.CardEffect_Scorch)
                    and not card.templateRef.isType(C.CardType_Creature)):tx.targetPlayerID=-1
            if action.target!=-1:tx.targetCardInstanceRef=cm.getCardInstance(action.target)
            if action.chain:card.candidateRecoveryPlan=action.chain
            after=position.apply(action);old_scores=position.scores();new_scores=after.scores()
            tx.powerChangeResult=new_scores[own]-old_scores[own]-new_scores[other]+old_scores[other]
            tx.strategicValue=card.getOptimalTransaction().strategicValue
            audit['changed']=native is None or (native.sourceCardInstanceRef.instanceId,native.targetSlotID,
                native.targetCardInstanceRef.instanceId if native.targetCardInstanceRef else -1)!=(action.source,action.slot,action.target)
            if action.chain:audit['recoveryChain']=[list(x) for x in action.chain]
            self._decidedCardTransaction=tx;self.attitude=TACTIC_MAXIMIZE_WIN
        self.policy_decisions[-1]['sequenceSearch']=audit


class ResponseAIPlayerController(SequenceAIPlayerController):
    def search(self,position,context):
        from ..response_search import choose_response
        return choose_response(position,context,self.search_profile)


class ISMCTSAIPlayerController(SequenceAIPlayerController):
    def search(self,position,context):
        from ..ismcts_search import choose_ismcts
        return choose_ismcts(position,context,self.search_profile)


class PassedRefinementAIPlayerController(SequenceAIPlayerController):
    def search(self,position,context):
        from ..passed_refinement import choose_refinement
        return choose_refinement(position,context,self.search_profile)


class ResourceAIPlayerController(SequenceAIPlayerController):
    def search(self,position,context):
        from dataclasses import replace
        from ..resource_value import ResourcePosition
        from ..response_search import choose_response
        corrected=ResourcePosition(**position.__dict__)
        return replace(choose_response(corrected,context,self.search_profile),revision='resource-v9.2')


class ResponseV8AIPlayerController(SequenceAIPlayerController):
    def search(self,position,context):
        from ..response_v8 import choose_response_v8
        from .. import tuning
        tuning.use_seat(self.playerID)
        from .. import response_v8
        if response_v8.flag('reserve35',self.playerID):
            # Experiment: value kept resources more, so a led round is passed sooner.
            tuning.ACTIVE=dict(tuning.ACTIVE,reserve_weight=0.35)
        try:
            return choose_response_v8(position,context,self.search_profile)
        finally:
            tuning.reset()

