"""Separate acting-side coverage from hypothetical-opponent coverage.

These are diagnostic ablations, not claims that the opponent cannot transform.
Observed public cards always keep their actual native templates and effects.
"""
from contextlib import contextmanager
from dataclasses import replace, asdict
from time import perf_counter
from gwentsim.position import Position, Action
from gwentsim.gwint import sequence_ai_controller as controllers
from mushroom_position import MushroomPosition
import mushroom_policy


def role_position(seat, role):
    if role not in ('own', 'opponent', 'both'):
        raise ValueError('unknown projection role')
    class ScopedMushroomPosition(MushroomPosition):
        def supported(self, card):
            enabled = role == 'both' or (self.player == seat) == (role == 'own')
            return super().supported(card) if enabled else Position.supported(self, card)
    return ScopedMushroomPosition


@contextmanager
def mushroom_role_hook(seat, role, audit):
    original = mushroom_policy.MushroomPosition
    mushroom_policy.MushroomPosition = role_position(seat, role)
    try:
        with mushroom_policy.mushroom_hook(seat, audit):
            yield
    finally:
        mushroom_policy.MushroomPosition = original


@contextmanager
def mushroom_roles_hook(roles, audits):
    """Two independent acting policies; each sees only its own captured position."""
    models = {seat: role_position(seat, role) for seat, role in roles.items()}
    cls = controllers.ResponseAIPlayerController
    original_search, original_begin = cls.search, cls.state_begin_ChoseMove
    original_position = controllers.Position
    owned_begin = 'state_begin_ChoseMove' in cls.__dict__
    def begin(controller):
        previous = controllers.Position
        controllers.Position = models.get(controller.playerID, original_position)
        try:
            return original_begin(controller)
        finally:
            controllers.Position = previous
    def search(controller, position, context):
        seat = controller.playerID
        if seat not in roles:
            return original_search(controller, position, context)
        baseline = original_position(**position.__dict__)
        native = getattr(controller, '_decidedCardTransaction', None)
        source = native.sourceCardInstanceRef if native else None
        intent = Action(source.instanceId, native.targetSlotID,
            native.targetCardInstanceRef.instanceId if native.targetCardInstanceRef else -1) if source else None
        reference = original_search(controller, baseline, context)
        pass_reasons = ('pass_for_match_resources', 'proven_no_supported_overtake')
        unsupported_native = bool(source and source.instanceId in baseline.hand
                                  and not baseline.supported(baseline.cards[source.instanceId]))
        reference_fallback = unsupported_native or reference.action is None and reference.reason not in pass_reasons
        reference_intent = intent if reference_fallback else reference.action
        started = perf_counter()
        candidate = replace(original_search(controller, position, context),
                            revision=f'mushroom-role-{roles[seat]}-v1')
        candidate_fallback = candidate.action is None and candidate.reason not in pass_reasons
        candidate_intent = intent if candidate_fallback else candidate.action
        audits.setdefault(seat, []).append(dict(changed=candidate_intent != reference_intent,
            round=context.round_index, scores=position.scores(), role=roles[seat],
            reference=reference.audit(), candidate=candidate.audit(),
            referenceFallback=reference_fallback, candidateFallback=candidate_fallback,
            effectiveReferenceAction=asdict(reference_intent) if reference_intent else None,
            effectiveCandidateAction=asdict(candidate_intent) if candidate_intent else None,
            refinementSeconds=perf_counter()-started))
        return candidate
    cls.state_begin_ChoseMove, cls.search = begin, search
    try:
        yield
    finally:
        cls.search = original_search
        if owned_begin:
            cls.state_begin_ChoseMove = original_begin
        else:
            delattr(cls, 'state_begin_ChoseMove')
        controllers.Position = original_position
