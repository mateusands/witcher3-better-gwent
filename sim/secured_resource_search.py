"""Original V7 experiment: compare pass and moves on the same resource scale.

The V7 passed-opponent branch adds a small reserve bonus to moves but not pass.
When the heuristic saturates, that bonus can outweigh keeping a useful card.
This prototype instead uses utility, future resources and action count as separate
ranking keys. Its future estimate remains heuristic; it is not a solved match.
"""
from dataclasses import replace
from gwentsim.options import Difficulty,PROFILES
from gwentsim.position import UnsupportedPosition
from gwentsim.response_search import secured
from gwentsim.sequence_search import utility,public_opponent_average,faction_carry


def refine_secured_resources(position,context,result,difficulty=Difficulty.EXPERT):
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
            if state.unknown_draws:continue
            for action in state.actions():
                if nodes>=cap:break
                nodes+=1
                try:after=state.apply(action)
                except UnsupportedPosition:unsupported+=1;continue
                # Execution replans after every real move. Keep every prefix secured;
                # an unsafe prefix must not rely on a continuation the next
                # decision could discard, especially after a recovery or draw.
                if not secured(after,context):continue
                following=path+(action,);key=rank(after,following)
                if key>best:best,best_path=key,following
                candidates.append((key,after,following))
            if nodes>=cap:break
        candidates.sort(key=lambda entry:entry[0],reverse=True)
        beam=[(state,path) for key,state,path in candidates[:profile.beam_width]]
        if not beam or nodes>=cap:break
    return replace(result,action=best_path[0] if best_path else None,value=best[0],
        pass_value=rank(position,())[0],nodes=result.nodes+nodes,
        unsupported=result.unsupported+unsupported,
        reason='supported_sequence' if best_path else 'pass_for_match_resources',
        revision='secured-resources-v1.1',budget_exhausted=nodes>=cap)
