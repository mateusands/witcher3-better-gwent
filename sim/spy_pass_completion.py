"""Apply owned-deck Spy reserve accounting to completed pass scenarios.

Printed Spy power belongs to the opposing board. Retained draw value uses only
our own remaining composition and the existing joint draw-capacity estimate.
Root replies, hypothetical enemy reserves, cards and game randomness are unchanged.
This remains a power heuristic; Medic chains and draw synergies are not solved.
"""
from contextlib import contextmanager
from dataclasses import replace
import pass_completion
from gwentsim.resource_value import spy_reserve_adjustment
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController


def corrected_completion_utility(position, context, depth, reserve, opponent_mean,
        passing=False, opponent_reserve=None):
    from gwentsim.sequence_search import utility
    return utility(position, context, depth, reserve + spy_reserve_adjustment(position),
        opponent_mean, passing=passing, opponent_reserve=opponent_reserve)


@contextmanager
def spy_completion_hook(seat, audit):
    previous_utility = pass_completion.utility
    pass_completion.utility = corrected_completion_utility
    try:
        with pass_completion.completion_hook(seat, audit):
            previous_search = ResponseAIPlayerController.search
            def labeled_search(controller, position, context):
                result = previous_search(controller, position, context)
                if controller.playerID != seat:
                    return result
                result = replace(result, revision='pass-completion-owned-spy-v1')
                audit[-1]['candidate']['revision'] = result.revision
                return result
            ResponseAIPlayerController.search = labeled_search
            try:
                yield
            finally:
                ResponseAIPlayerController.search = previous_search
    finally:
        pass_completion.utility = previous_utility
