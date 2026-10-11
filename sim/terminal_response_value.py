"""Original V7 diagnostic: remove move-only tie bonuses from future utilities.

choose_sequence adds a tiny reserve/action-count tie bonus to its selected move.
That aids local ranking, but choose_response uses its returned value as a future
outcome, where even a value above one can beat a resource-preserving alternative.
Keep its selected supported sequence and bounded search; recompute the actual
heuristic utility of that same terminal state. This does not solve round planning
or calibrate the utility, and does not change already-passed real decisions.
"""
from contextlib import contextmanager
from dataclasses import replace
from gwentsim import response_search
from gwentsim.sequence_search import utility,public_opponent_average


def terminal_value(position,context,result):
    if not context.opponent_passed:return result
    state=position
    for action in result.sequence:state=state.apply(action)
    value=utility(state,context,len(result.sequence),state.reserve(),
        public_opponent_average(position),passing=not result.sequence)
    return replace(result,utility=value,revision='terminal-response-value-v1')


@contextmanager
def terminal_values():
    """Caller scopes this to one candidate search, not real native execution."""
    original=response_search.choose_sequence
    def corrected(position,context,difficulty):
        return terminal_value(position,context,original(position,context,difficulty))
    response_search.choose_sequence=corrected
    try:yield
    finally:response_search.choose_sequence=original


@contextmanager
def terminal_response_hook(seat,audit):
    from time import perf_counter
    from dataclasses import asdict
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    from gwentsim.position import Action
    original=ResponseAIPlayerController.search
    def search(controller,position,context):
        reference=original(controller,position,context)
        if controller.playerID!=seat or context.opponent_passed:return reference
        started=perf_counter()
        with terminal_values():candidate=replace(original(controller,position,context),revision='terminal-response-value-v1')
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
