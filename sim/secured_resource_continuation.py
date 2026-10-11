"""Original diagnostic: retain known restorations across temporary deficits.

The V7 passed-opponent branch adds a small reserve bonus to moves but not pass.
When the heuristic saturates, that bonus can outweigh keeping a useful card.
This candidate uses symmetric utility and known-hand continuations. An unsafe
first move is allowed only if it is already the unchanged V7 choice. Unknown drawn
identities are never invented; existing known cards can still restore the score.
Execution replans, so full native trajectory tests remain required. Future value
is heuristic, not a solved match or a guaranteed strength improvement.
"""
from dataclasses import replace
from gwentsim.options import Difficulty,PROFILES
from gwentsim.position import UnsupportedPosition
from gwentsim.response_search import secured
from gwentsim.sequence_search import utility,public_opponent_average,faction_carry


def refine_secured_continuation(position,context,result,difficulty=Difficulty.EXPERT):
    if not context.opponent_passed or not secured(position,context):return result
    if context.opponent_losses>=1 or context.round_index>=2:return result
    profile=PROFILES[Difficulty(difficulty)]
    cap=max(32,profile.search_depth*profile.beam_width*12)
    mean=public_opponent_average(position)
    cache={}
    def reserve(state):
        key=state.reserve_key()
        if key not in cache:cache[key]=state.reserve()
        return cache[key]
    def rank(state,path):
        value=utility(state,context,len(path),reserve(state),mean,passing=not path)
        future=reserve(state)+faction_carry(state,state.player,context.own_faction,context.round_index+1)
        return value,future,-len(path)
    best=rank(position,());best_path=();beam=[(position,())]
    nodes=0;unsupported=0
    for _ in range(profile.search_depth):
        candidates=[]
        for state,path in beam:
            for action in state.actions():
                if nodes>=cap:break
                nodes+=1
                try:after=state.apply(action)
                except UnsupportedPosition:unsupported+=1;continue
                # Keep a temporarily losing continuation in the beam, but never
                # score it as a completed winning plan. Unknown draws have no
                # identities in this model; actions use the still-known hand.
                # Do not introduce a new losing first move: only the reference
                # V7 action may cross that boundary before runtime replanning.
                if not path and not secured(after,context) and action!=result.action:
                    continue
                following=path+(action,);key=rank(after,following)
                if secured(after,context) and key>best:best,best_path=key,following
                candidates.append((key,after,following))
            if nodes>=cap:break
        candidates.sort(key=lambda entry:entry[0],reverse=True)
        beam=[(state,path) for key,state,path in candidates[:profile.beam_width]]
        if not beam or nodes>=cap:break
    return replace(result,action=best_path[0] if best_path else None,value=best[0],
        pass_value=rank(position,())[0],nodes=result.nodes+nodes,
        unsupported=result.unsupported+unsupported,
        reason='supported_sequence' if best_path else 'pass_for_match_resources',
        revision='secured-continuation-v1',budget_exhausted=nodes>=cap)
