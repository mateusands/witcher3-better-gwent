"""Explicit simulator-only candidate seat hook for the isolated Mushroom model.

Native FX/rules still execute every selected action. Reference search audits are
distinguished from native fallback choices; the paired baseline is unmodified V7.
Future-resource estimates/budgets/belief priors remain V7 for this first ablation.
"""
from contextlib import contextmanager
from dataclasses import replace,asdict
from time import perf_counter
from gwentsim.gwint import sequence_ai_controller as controllers
from gwentsim.position import Action
from mushroom_position import MushroomPosition


@contextmanager
def mushroom_hook(seat,audit):
    cls=controllers.ResponseAIPlayerController
    original_search=cls.search;original_begin=cls.state_begin_ChoseMove
    original_position=controllers.Position
    owned_begin='state_begin_ChoseMove' in cls.__dict__
    def begin(controller):
        previous=controllers.Position
        controllers.Position=MushroomPosition if controller.playerID==seat else original_position
        try:return original_begin(controller)
        finally:controllers.Position=previous
    def search(controller,position,context):
        if controller.playerID!=seat:return original_search(controller,position,context)
        baseline=original_position(**position.__dict__)
        native=getattr(controller,'_decidedCardTransaction',None)
        source=native.sourceCardInstanceRef if native else None
        unsupported_native=bool(source and source.instanceId in baseline.hand and not baseline.supported(baseline.cards[source.instanceId]))
        native_action=Action(source.instanceId,native.targetSlotID,
            native.targetCardInstanceRef.instanceId if native.targetCardInstanceRef else -1) if source else None
        pass_reasons=('pass_for_match_resources','proven_no_supported_overtake')
        reference=original_search(controller,baseline,context)
        fallback=unsupported_native or reference.action is None and reference.reason not in pass_reasons
        reference_action=reference.action
        reference_audit=reference.audit()
        if fallback:
            reference_action=native_action
            reference_audit=dict(action=asdict(native_action) if native_action else None,
                reason='native_unsupported_choice' if unsupported_native else 'native_fallback_after_search')
        started=perf_counter()
        candidate=replace(original_search(controller,position,context),revision='mushroom-projection-v1')
        candidate_fallback=candidate.action is None and candidate.reason not in pass_reasons
        candidate_action=native_action if candidate_fallback else candidate.action
        candidate_audit=candidate.audit()
        if candidate_fallback:
            candidate_audit=dict(action=asdict(native_action) if native_action else None,
                reason='native_fallback_after_search',search=candidate_audit)
        audit.append(dict(changed=candidate_action!=reference_action,round=context.round_index,
            scores=position.scores(),reference=reference_audit,candidate=candidate_audit,
            referenceSearchIsRuntimePolicy=not fallback,
            referenceSearchOnCandidateContext=reference.audit(),
            refinementSeconds=perf_counter()-started))
        return candidate
    cls.state_begin_ChoseMove=begin;cls.search=search
    try:yield
    finally:
        cls.search=original_search
        if owned_begin:cls.state_begin_ChoseMove=original_begin
        else:delattr(cls,'state_begin_ChoseMove')
        controllers.Position=original_position
