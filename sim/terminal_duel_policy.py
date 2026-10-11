"""Conservative V7 refinement from fully solved small hypothetical endgames.

All existing public hypotheses must finish within the shared extra node allowance.
Preserve the reference unless a root action has strictly higher average exact
subgame value. These averages are scenario scores, not calibrated probabilities.
"""
from contextlib import contextmanager
from dataclasses import replace,asdict
from gwentsim.opponent_belief import hypotheses,Hypothesis
from terminal_duel import solve_terminal


def refine_terminal(position,context,reference,detail=None):
    if context.round_index!=2 and not (context.own_losses==context.opponent_losses==1):
        return reference
    if reference.action is None and reference.reason not in ('pass_for_match_resources','proven_no_supported_overtake'):
        return reference
    beliefs=(Hypothesis((),(),0,'already-passed'),) if context.opponent_passed else hypotheses(position,context,6)
    if not beliefs:return reference
    results=[solve_terminal(position,context,h,max_nodes=8192//len(beliefs)) for h in beliefs]
    if detail is not None:
        detail.update(scenarios=len(results),complete=sum(r.complete for r in results),
            extraNodes=sum(r.nodes for r in results),reasons=[r.reason for r in results])
    if not all(r.complete for r in results):return reference
    maps=[dict(r.values) for r in results]
    if any(set(m)!=set(maps[0]) for m in maps) or reference.action not in maps[0]:return reference
    scores={a:sum(m[a] for m in maps)/len(maps) for a in maps[0]}
    chosen=max(scores,key=scores.get)
    if detail is not None:
        detail.update(referenceScenarioScore=scores[reference.action],bestScenarioScore=scores[chosen],
            bestAction=asdict(chosen) if chosen else None)
    if scores[chosen]<=scores[reference.action]+1e-12:return reference
    return replace(reference,action=chosen,value=scores[chosen],pass_value=scores[None],
        nodes=reference.nodes+sum(r.nodes for r in results),
        reason='supported_response' if chosen else 'pass_for_match_resources',revision='terminal-duel-v1')


@contextmanager
def terminal_duel_hook(seat,audit):
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    original=ResponseAIPlayerController.search
    def search(controller,position,context):
        reference=original(controller,position,context)
        if controller.playerID!=seat or int(controller.search_profile)!=3:return reference
        detail={}
        candidate=refine_terminal(position,context,reference,detail)
        audit.append(dict(changed=candidate.action!=reference.action,round=context.round_index,
            scores=position.scores(),reference=reference.audit(),candidate=candidate.audit(),duel=detail))
        return candidate
    ResponseAIPlayerController.search=search
    try:yield
    finally:ResponseAIPlayerController.search=original
