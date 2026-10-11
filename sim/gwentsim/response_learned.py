"""Experimental PoC policy: V8 search with a learned leaf evaluator.

Integration point (Integration B): the leaf `utility` used by
response_search.choose_response. Everything else is V8 unchanged:
- same node budget, samples and beam width;
- all V8 post-search tactical guards (choose_response_v8);
- exact terminal values (0, 0.5, 1) from the hand-crafted utility are kept;
  the learned model only replaces uncertain, non-terminal leaf values.

Simulator-only. Not used by the game package.
"""
from dataclasses import replace
from contextlib import contextmanager

from . import response_search
from .response_v8 import choose_response_v8
from .learned_evaluator import predict_win_probability

EXACT = (0.0, 0.5, 1.0)


def learned_utility(original):
    def utility(position, context, *args, **kwargs):
        value = original(position, context, *args, **kwargs)
        if value in EXACT:
            return value
        return predict_win_probability(position, context)
    return utility


@contextmanager
def learned_leaves():
    original = response_search.utility
    response_search.utility = learned_utility(original)
    try:
        yield
    finally:
        response_search.utility = original


def choose_response_learned(position, context, profile):
    with learned_leaves():
        result = choose_response_v8(position, context, profile)
    return replace(result, revision='learned-v8-poc')
