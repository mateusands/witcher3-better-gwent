"""Original V7 refinement using the hybrid's deterministic passed-round solver.

Open rounds retain V7. Only a verified deterministic winning line or a completed terminal improvement replaces V7.
Future-match utility remains heuristic; unknown effects/draws and budget exhaustion
use the unchanged V7 reference. Simulator experiment, not production dispatch.
"""
from dataclasses import dataclass,asdict
from time import perf_counter
from .options import Difficulty
from .position import UnsupportedPosition,LEADER_PICK
from .passed_search import choose_passed
from .response_search import choose_response
from .sequence_search import choose_sequence,utility,public_opponent_average

EXACT_NODES=(256,1024,4096,16384)


@dataclass(frozen=True)
class RefinementResult:
    action:object
    reason:str
    value:float
    mode:str
    elapsed_seconds:float
    exact_complete:bool|None=None
    exact_nodes:int=0
    limitations:tuple=()
    fallback:dict|None=None
    reference:dict|None=None
    winning_witness:dict|None=None
    revision:str='response-pass-v8.2'

    def audit(self):return asdict(self)


def verify_terminal_witness(position,context,sequence):
    """Verify existence of a winning line, independently of search completeness.

    The opponent has passed and every chosen transition must be deterministic.
    Unexplored alternatives may remain unsupported; they are not used as proof.
    This certifies a win, not the cheapest line or complete rule coverage.
    """
    if not context.opponent_passed or not sequence or not (
            context.opponent_losses>=1 or context.round_index==2 or
            context.own_losses>=1 and context.opponent_losses>=1):return None
    state=position
    for action in sequence:
        if state.unknown_draws or action not in state.actions():return None
        if action.source==(state.leaders or {}).get(state.player):
            effect=state.leader_effect(state.player)
            if effect in LEADER_PICK and len(state.weather_templates(*LEADER_PICK[effect]))>1:
                return None
        try:state=state.apply(action)
        except (UnsupportedPosition,ValueError):return None
        if state.unknown_draws:return None
    value=utility(state,context,0,state.reserve(),public_opponent_average(position),passing=True)
    if value!=1:return None
    return dict(sequence=[asdict(a) for a in sequence],scores=state.scores(),
        terminalValue=value,opponentPassed=True,deterministicTransitions=True,
        cheapestLineProven=False)


def choose_refinement(position,context,difficulty=Difficulty.HARD,*,max_nodes=None,time_limit=None):
    difficulty=Difficulty(difficulty);started=perf_counter()
    reference=choose_response(position,context,difficulty)
    terminal_round=context.round_index==2 or context.own_losses>=1 and context.opponent_losses>=1
    # Future reserve utility is not a proof of a better match result. Search only
    # decisive rounds or an opportunity to end the match with a second win now.
    eligible=context.opponent_passed and (terminal_round or context.opponent_losses>=1)
    if not eligible:
        return RefinementResult(reference.action,reference.reason,reference.value,
            'v7_open_round' if not context.opponent_passed else 'v7_future_round',
            perf_counter()-started,reference=reference.audit())
    # V7 adds tiny reserve/length tie-breaks to its ranking value, so compare
    # outcome utility from its actual plan rather than treating that rank as
    # a probability. Do not alter the reference ranking or execution.
    plan=choose_sequence(position,context,difficulty)
    projected=position
    for action in plan.sequence:projected=projected.apply(action)
    reference_value=utility(projected,context,0,projected.reserve(),
        public_opponent_average(position),passing=True)
    if reference_value==1:
        return RefinementResult(reference.action,reference.reason,reference.value,
            'v7_terminal_upper_bound',perf_counter()-started,reference=reference.audit())
    exact=choose_passed(position,context,
        max_nodes=EXACT_NODES[int(difficulty)] if max_nodes is None else max_nodes,
        time_limit=time_limit,stop_at_terminal_win=True)
    proven_terminal=terminal_round or exact.value==1
    improved=exact.value>reference_value+1e-12
    witness=verify_terminal_witness(position,context,exact.sequence)
    if improved and witness is not None:
        return RefinementResult(exact.action,exact.reason,1,'verified_terminal_witness',
            perf_counter()-started,exact.complete,exact.nodes,exact.limitations,
            reference=reference.audit(),winning_witness=witness)
    if exact.complete and proven_terminal and improved:
        return RefinementResult(exact.action,exact.reason,exact.value,'completed_terminal_improvement',
            perf_counter()-started,True,exact.nodes,reference=reference.audit())
    mode='v7_incomplete_passed_search' if not exact.complete else 'v7_no_proven_terminal_improvement'
    return RefinementResult(reference.action,reference.reason,reference.value,mode,perf_counter()-started,
        exact.complete,exact.nodes,exact.limitations,
        None if exact.complete else dict(policy='response-v7',detail=reference.audit()),reference.audit())
