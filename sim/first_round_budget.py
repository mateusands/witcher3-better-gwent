"""Original V7 experiment: losing round one requires two future wins.

V7 compares the whole future hand against one opponent-hand strength, with a
one-average-card penalty for needing two wins. This candidate divides the acting
future resource estimate between those two required rounds in the loss branch.
The winning branch and actual tie endpoints remain V7. This is a conservative
allocation heuristic, not a guaranteed strategy or calibrated win probability.
Draw/combinations/opponent allocation retain reference limitations.
"""
from contextlib import contextmanager
from dataclasses import replace,asdict
from math import sqrt
from time import perf_counter
from gwentsim import constants as C,response_search,sequence_search
from gwentsim.sequence_search import utility as original_utility,sigmoid,faction_carry
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from gwentsim.position import Action


def first_round_budget_utility(position,context,depth,reserve,opponent_mean,passing=False,opponent_reserve=None):
    reference=original_utility(position,context,depth,reserve,opponent_mean,passing,opponent_reserve)
    if context.round_index!=0 or context.own_losses or context.opponent_losses:return reference
    own=position.player;other=1-own;scores=position.scores()
    replies=0 if context.opponent_passed else max(0,depth-1)
    count=max(0,context.opponent_hand_count-replies)
    gap=scores[own]-scores[other]-replies*opponent_mean
    # This actual first-round draw removes a life from both sides. Only one
    # future round remains; dividing the hand between two would be incorrect.
    if context.opponent_passed and gap==0 and (context.own_faction==context.opponent_faction or
            C.FactionId_Nilfgaard not in (context.own_faction,context.opponent_faction)):
        return reference
    opposing=(count*opponent_mean if opponent_reserve is None else opponent_reserve)+(3 if context.opponent_leader_available else 0)
    scale=4+sqrt(max(1,count))*2
    wins=gap>=0 if context.wins_ties else gap>0
    if not position.hand and not position.unknown_draws and not context.own_leader_available and not position.leader_modeled(own):passing=True
    if context.opponent_passed:p=float(wins)
    elif passing:p=sigmoid((gap-opposing)/scale) if wins else 0
    else:p=sigmoid((gap+(reserve-opposing)*.25)/scale)
    own_future=reserve+faction_carry(position,own,context.own_faction,1)
    other_future=opposing+faction_carry(position,other,context.opponent_faction,1)
    enemy_draw=opponent_mean if context.opponent_faction==C.FactionId_Northern_Kingdom else 0
    old=sigmoid((own_future-other_future-enemy_draw-opponent_mean)/scale)
    split=sigmoid((own_future/2-other_future-enemy_draw-opponent_mean)/scale)
    return reference+(1-p)*(split-old)


@contextmanager
def first_round_budget_hook(seat,audit):
    original_search=ResponseAIPlayerController.search
    old_response=response_search.utility;old_sequence=sequence_search.utility
    def search(controller,position,context):
        reference=original_search(controller,position,context)
        if controller.playerID!=seat or context.round_index!=0 or context.own_losses or context.opponent_losses:return reference
        started=perf_counter()
        response_search.utility=sequence_search.utility=first_round_budget_utility
        try:candidate=replace(original_search(controller,position,context),revision='first-round-budget-v1')
        finally:response_search.utility=old_response;sequence_search.utility=old_sequence
        native=getattr(controller,'_decidedCardTransaction',None)
        source=native.sourceCardInstanceRef if native else None
        intent=Action(source.instanceId,native.targetSlotID,
            native.targetCardInstanceRef.instanceId if native.targetCardInstanceRef else -1) if source else None
        pass_reasons=('pass_for_match_resources','proven_no_supported_overtake')
        def fallback(r):return r.action is None and r.reason not in pass_reasons
        def effective(r):return intent if fallback(r) else r.action
        audit.append(dict(changed=effective(reference)!=effective(candidate),round=context.round_index,
            scores=position.scores(),reference=reference.audit(),candidate=candidate.audit(),
            referenceFallback=fallback(reference),candidateFallback=fallback(candidate),
            effectiveReferenceAction=asdict(effective(reference)) if effective(reference) else None,
            effectiveCandidateAction=asdict(effective(candidate)) if effective(candidate) else None,
            refinementSeconds=perf_counter()-started))
        return candidate
    ResponseAIPlayerController.search=search
    try:yield
    finally:
        ResponseAIPlayerController.search=original_search
        response_search.utility=old_response;sequence_search.utility=old_sequence
