"""Value a round-two pass after a supported hypothetical opponent catches up.

Only existing public-catalog hypotheses are consulted. At most three successive
opponent moves are searched with V7's existing bounded passed-round planner.
Unresolved effects/draws/leader or failure to complete are not proof of a win:
return None and retain the reference's one-reply pass estimate for that scenario.
This is a reserve-cost experiment, not a calibrated win probability.
"""
from dataclasses import replace, asdict
from contextlib import contextmanager
from time import perf_counter
from gwentsim import constants as C
from gwentsim.options import Difficulty
from gwentsim.position import Action, UnsupportedPosition
from gwentsim.opponent_belief import opponent_view
from gwentsim.sequence_search import choose_sequence, utility, public_opponent_average
from gwentsim.response_search import secured


def completion_value(position, context, hypothesis, difficulty=Difficulty.HARD, audit=None):
    if context.round_index != 1 or context.opponent_passed or (
            context.own_losses, context.opponent_losses) != (0, 1):
        return None
    view = opponent_view(position, hypothesis)
    flipped = replace(context, own_losses=context.opponent_losses,
        opponent_losses=context.own_losses, own_faction=context.opponent_faction,
        opponent_faction=context.own_faction, opponent_passed=True,
        opponent_hand_count=len(position.hand),
        own_leader_available=view.leader_unmodeled(view.player),
        opponent_leader_available=position.leader_unmodeled(position.player))
    if view.leader_unmodeled(view.player) or hypothesis.unsupported or view.unknown_draws:
        return None
    path = []
    nodes = 0
    for step in range(4):
        if view.unknown_draws:
            break
        if secured(view, flipped):
            own = view.clone()
            own.player = position.player
            own.hand = position.hand
            own.counts = dict(position.counts)
            own.unknown_draws = position.unknown_draws
            own.draw_value = position.draw_value
            ended = replace(context, opponent_passed=True,
                opponent_hand_count=len(view.hand),
                opponent_leader_available=view.leader_unmodeled(view.player))
            result = utility(own, ended, 1, own.reserve(), public_opponent_average(position),
                passing=True, opponent_reserve=view.reserve())
            if audit is not None:
                audit.append(dict(completed=True, moves=[asdict(a) for a in path],
                    nodes=nodes, scores=own.scores(), remainingHypotheticalCards=len(view.hand),
                    value=result))
            return result
        if step == 3:
            break
        selected = choose_sequence(view, flipped, difficulty)
        nodes += selected.nodes
        if selected.action is None:
            # Bounded failure is not an impossibility certificate.
            break
        try:
            following = view.apply(selected.action)
        except UnsupportedPosition:
            break
        path.append(selected.action)
        view = following
    if audit is not None:
        audit.append(dict(completed=False, moves=[asdict(a) for a in path], nodes=nodes))
    return None


@contextmanager
def completion_hook(seat, audit):
    """Change only the selected controller; native decks/deals/rules remain intact."""
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    from pass_completion_search import choose_response
    original = ResponseAIPlayerController.search
    def search(controller, position, context):
        reference = original(controller, position, context)
        if controller.playerID != seat:
            return reference
        started = perf_counter()
        candidate = choose_response(position, context, controller.search_profile)
        native = getattr(controller, '_decidedCardTransaction', None)
        source = native.sourceCardInstanceRef if native else None
        intent = Action(source.instanceId, native.targetSlotID,
            native.targetCardInstanceRef.instanceId if native.targetCardInstanceRef else -1) if source else None
        def effective(result):
            fallback = result.action is None and result.reason not in (
                'pass_for_match_resources', 'proven_no_supported_overtake')
            return intent if fallback else result.action
        audit.append(dict(changed=effective(reference) != effective(candidate),
            round=context.round_index, scores=position.scores(), reference=reference.audit(),
            candidate=candidate.audit(), effectiveReferenceAction=asdict(effective(reference)) if effective(reference) else None,
            effectiveCandidateAction=asdict(effective(candidate)) if effective(candidate) else None,
            refinementSeconds=perf_counter()-started))
        return candidate
    ResponseAIPlayerController.search = search
    try:
        yield
    finally:
        ResponseAIPlayerController.search = original
