"""Exhaustive deterministic round search after the opponent passes.

Exactness concerns reachable modeled round stops, ranked by the supplied V7
match-resource utility and reserve. Future-round win probabilities remain heuristic.
Unresolved draws, omitted effects, or a budget stop explicitly invalidate completeness.
This module is not connected to V7 and must not change its benchmark reference.
"""
from dataclasses import dataclass,asdict
from time import perf_counter
from . import constants as C
from .position import UnsupportedPosition,LEADER_PICK
from .sequence_search import utility,public_opponent_average


@dataclass(frozen=True)
class PassedResult:
    action:object
    sequence:tuple
    value:float
    reserve:float
    pass_value:float
    nodes:int
    complete:bool
    limitations:tuple
    reason:str
    revision:str='passed-exhaustive-v1'

    def audit(self):return asdict(self)


def state_key(state):
    # Keep grave order and individual effects: no sorting-away of the runtime
    # ordering discrepancy or merging distinct Medic/Decoy choices.
    return (state.player,state.hand,tuple(sorted(state.board.items())),
        tuple(sorted(state.grave.items())),tuple(sorted(state.effects.items())),
        tuple(sorted(state.counts.items())),tuple(sorted(state.cards.items())),
        tuple(sorted((state.leader_ready or {}).items())),state.unknown_draws,
        state.draw_value,state.next_key)


def choose_passed(position,context,*,max_nodes=100000,time_limit=None,clock=perf_counter,
                  stop_at_terminal_win=False):
    """Enumerate every modeled continuation, including stopping after each move.

    Budget truncation never yields a complete result. A sampled/unknown draw is a
    chance boundary, not a deterministic leaf. No beam/depth cutoff is used. The
    caller may use an incomplete result provisionally, but cannot claim exactness.
    """
    if not context.opponent_passed:raise ValueError('opponent must have passed')
    if max_nodes is not None and max_nodes<0:raise ValueError('negative node budget')
    if time_limit is not None and time_limit<0:raise ValueError('negative time budget')
    started=clock();nodes=0;limitations=set();memo={};active=set()
    mean=public_opponent_average(position);reserves={}
    def evaluate(state):
        key=state.reserve_key()
        if key not in reserves:reserves[key]=state.reserve()
        r=reserves[key]
        return utility(state,context,0,r,mean,passing=True),r
    initial_value,initial_reserve=evaluate(position)
    # A public, already secured match finish is a proof at the upper reward bound.
    # No hypothetical recovery, draw or unused leader can improve on ending now.
    if initial_value==1 and (context.opponent_losses>=1 or context.round_index==2):
        return PassedResult(None,(),1,initial_reserve,1,0,True,(),'pass_for_match_resources')
    def visit(state):
        nonlocal nodes
        key=state_key(state)
        if key in memo:return memo[key]
        value,reserve=evaluate(state);best=(value,reserve,())
        if key in active:
            limitations.add('resource_cycle');return best
        if (max_nodes is not None and nodes>=max_nodes) or (
                time_limit is not None and clock()-started>=time_limit):
            limitations.add('budget');return best
        nodes+=1
        if state.unknown_draws:
            limitations.add('unknown_draws');return best
        if state.leader_unmodeled(state.player):limitations.add('unsupported_leader')
        effect=state.leader_effect(state.player)
        if state.leader_modeled(state.player) and effect in LEADER_PICK and len(state.weather_templates(*LEADER_PICK[effect]))>1:
            limitations.add('ambiguous_weather_leader')
        if any(not state.supported(state.cards[k]) for k in state.hand):
            limitations.add('unsupported_hand')
        # actions() omits unsupported recovery targets, so check this omission
        # explicitly rather than treating the remaining choices as exhaustive.
        if any(state.cards[k].has(C.CardEffect_Nurse) for k in state.hand):
            if any(not state.supported(state.cards[k]) for k in state.recovery_targets(state.player)):
                limitations.add('unsupported_recovery')
        active.add(key)
        for action in state.actions():
            if (max_nodes is not None and nodes>=max_nodes) or (
                    time_limit is not None and clock()-started>=time_limit):
                limitations.add('budget');break
            try:after=state.apply(action)
            except UnsupportedPosition:
                limitations.add('unsupported_transition');continue
            child_value,child_reserve,tail=visit(after)
            path=(action,)+tail
            if (child_value,child_reserve,-len(path))>(best[0],best[1],-len(best[2])):
                best=(child_value,child_reserve,path)
            # A concrete terminal win attains the reward upper bound. Other
            # branches need not be solved to establish existence of this line.
            # Keep completeness false: cheapest line / all choices are unproven.
            if stop_at_terminal_win and best[0]==1 and (
                    context.opponent_losses>=1 or context.round_index==2):
                limitations.add('winning_witness_early_stop');break
        active.remove(key)
        # Truncated entries are lower bounds only; avoid reusing them as solved.
        if not limitations:memo[key]=best
        return best
    value,reserve,sequence=visit(position)
    complete=not limitations
    return PassedResult(sequence[0] if sequence else None,sequence,value,reserve,
        initial_value,nodes,complete,tuple(sorted(limitations)),
        'supported_sequence' if sequence else 'pass_for_match_resources' if complete else 'incomplete_passed_search')
