"""Original experimental hybrid Gwent ISMCTS policy, simulator only.

Uses fair sampled information sets, V7-guided bounded full-match playouts and
exhaustive deterministic passed-round search when complete. Unsupported effects
and finite rollouts remain explicit limitations; V7 stays the reference policy.
"""
from dataclasses import dataclass,asdict
from time import perf_counter
from .ismcts import search
from .ismcts_gwent import determinize,GwentState,move_key,self_scorch_without_recovery
from .passed_search import choose_passed
from .opponent_belief import public_seed
from .options import Difficulty
from .sequence_search import utility,public_opponent_average
from .response_search import choose_response,inert_discard
from .position import UnsupportedPosition

# Provisional deterministic offline budgets; actual Scaleform timing remains
# unmeasured. They bound search work, not a validated difficulty progression.
BUDGETS=((8,8,256),(24,16,1024),(64,32,4096),(128,64,16384))


@dataclass(frozen=True)
class HybridResult:
    action:object
    reason:str
    value:float
    iterations:int
    elapsed_seconds:float
    rollout_steps:int
    terminal_rollouts:int
    cutoff_rollouts:int
    limitations:tuple
    exact_complete:bool|None=None
    exact_nodes:int=0
    alternatives:tuple=()
    fallback:dict|None=None
    revision:str='ismcts-hybrid-v1.3'
    coverage_cutoffs:int=0

    def audit(self):return asdict(self)


def choose_ismcts(position,context,difficulty=Difficulty.HARD,*,iterations=None,time_limit=None):
    limit,steps,exact_nodes=BUDGETS[int(Difficulty(difficulty))]
    if iterations is not None:limit=iterations
    if context.opponent_passed:
        started=perf_counter()
        exact=choose_passed(position,context,max_nodes=exact_nodes,time_limit=time_limit)
        if exact.complete:
            return HybridResult(exact.action,exact.reason,exact.value,0,perf_counter()-started,0,0,0,(),True,exact.nodes)
        fallback=choose_response(position,context,difficulty)
        return HybridResult(fallback.action,fallback.reason,fallback.value,0,perf_counter()-started,0,0,0,
            exact.limitations,False,exact.nodes,fallback=dict(policy='response-v7',detail=fallback.audit()))
    roots={('pass',):None}
    for action in position.actions():
        try:after=position.apply(action)
        except UnsupportedPosition:continue
        if not inert_discard(position,after,action) and not self_scorch_without_recovery(position,after,action,context):
            roots.setdefault(move_key(position,action),action)
    reserve_cache={};limitations=set();total_steps=0;terminal=0;cutoff=0;coverage_cutoffs=0
    def reserve(state):
        key=state.reserve_key()
        if key not in reserve_cache:reserve_cache[key]=state.reserve()
        return reserve_cache[key]
    def sample(rng):return GwentState.from_sample(determinize(position,context,rng),context)
    def coverage_cutoff(state,observer):
        nonlocal cutoff,coverage_cutoffs
        unresolved=state.unresolved_choices()
        limitations.update(state.limitations)
        if not unresolved:return None
        limitations.update(unresolved);limitations.add('incomplete_action_set_cutoff')
        cutoff+=1;coverage_cutoffs+=1
        return state.heuristic(observer)
    def rollout(state,rng,observer):
        nonlocal total_steps,terminal,cutoff
        for _ in range(steps):
            reward=state.terminal_reward(observer)
            if reward is not None:terminal+=1;return reward
            reward=coverage_cutoff(state,observer)
            if reward is not None:return reward
            actor=state.to_move;own=state.positions[actor];other=state.positions[1-actor]
            legal=state.legal_actions();limitations.update(state.limitations)
            if len(legal)==1 and (own.hand or own.leader_unmodeled(actor)):
                limitations.add('unresolved_rollout_choices');break
            # The V7 utility guides simulated choices; no search of the real
            # opponent collection takes place. This perfect-information rollout
            # inside a sampled world is a strategy-fusion limitation of SO-ISMCTS.
            ctx=state.context(actor);mean=public_opponent_average(own);opposing=reserve(other)
            scored=[]
            for key,action in legal.items():
                after=own if action is None else state._after[key]
                value=utility(after,ctx,0 if action is None else 1,reserve(after),mean,
                    passing=action is None,opponent_reserve=opposing)
                scored.append((value,key,action))
            maximum=max(v for v,key,action in scored)
            best=[(key,action) for value,key,action in scored if abs(value-maximum)<1e-12]
            key,action=rng.choice(best if rng.random()>=0.1 else list(legal.items()))
            try:state=state.next_state(action,rng)
            except UnsupportedPosition:
                limitations.add('unsupported_round_transition');break
            total_steps+=1
        reward=state.terminal_reward(observer)
        if reward is not None:terminal+=1;return reward
        cutoff+=1;return state.heuristic(observer)
    try:
        result=search(sample,rollout,position.player,iterations=limit,
            seed=public_seed(position,context)^0x49534d435453,time_limit=time_limit,max_tree_depth=64,
            cutoff=coverage_cutoff)
    except UnsupportedPosition as exc:
        fallback=choose_response(position,context,difficulty)
        return HybridResult(fallback.action,fallback.reason,fallback.value,0,0,total_steps,terminal,cutoff,
            tuple(sorted(limitations|{str(exc)})),fallback=dict(policy='response-v7',detail=fallback.audit()),
            coverage_cutoffs=coverage_cutoffs)
    if result.move is None:
        fallback=choose_response(position,context,difficulty)
        return HybridResult(fallback.action,fallback.reason,fallback.value,result.iterations,
            result.elapsed_seconds,total_steps,terminal,cutoff,tuple(sorted(limitations|{'empty_search'})),
            fallback=dict(policy='response-v7',detail=fallback.audit()),coverage_cutoffs=coverage_cutoffs)
    if result.move not in roots:raise RuntimeError('sampled root move does not map to observer action')
    arm=next(a for a in result.arms if a.move==result.move)
    action=roots[result.move]
    return HybridResult(action,'supported_sequence' if action is not None else 'pass_for_match_resources',
        arm.mean,result.iterations,result.elapsed_seconds,total_steps,terminal,cutoff,
        tuple(sorted(limitations)),alternatives=tuple(asdict(a) for a in result.arms),
        coverage_cutoffs=coverage_cutoffs)
