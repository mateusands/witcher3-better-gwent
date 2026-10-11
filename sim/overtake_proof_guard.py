"""Do not certify an impossible chase while omitting recovery or a ready leader.

The reference bound counts board/hand units but not a Medic's graveyard targets
or active leader effects. Returning None declines that proof and leaves the same
bounded V7 sequence search to choose a move/pass. No card or match rules change.
"""
from contextlib import contextmanager
from gwentsim import constants as C,sequence_search
from gwentsim.position import ROWS

original_bounds=sequence_search.overtaking_bounds


def guarded_bounds(position):
    own=position.player
    hand=[position.cards[k] for k in position.hand]
    if position.leader_modeled(own):return None
    if any(c.has(C.CardEffect_Nurse) for c in hand):return None
    if any(c.has(C.CardEffect_UnsummonDummy) for c in hand) and any(
        position.cards[k].has(C.CardEffect_Nurse) for row in ROWS for k in position.board[own,row]):
        return None
    return original_bounds(position)


@contextmanager
def proof_guard():
    original=sequence_search.overtaking_bounds
    sequence_search.overtaking_bounds=guarded_bounds
    try:yield
    finally:sequence_search.overtaking_bounds=original


@contextmanager
def proof_guard_hook(seat,audit):
    from dataclasses import replace,asdict
    from time import perf_counter
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    from gwentsim.position import Action
    original=ResponseAIPlayerController.search
    def search(controller,position,context):
        reference=original(controller,position,context)
        if controller.playerID!=seat:return reference
        started=perf_counter()
        with proof_guard():candidate=replace(original(controller,position,context),revision='overtake-proof-guard-v1')
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
    finally:ResponseAIPlayerController.search=original
