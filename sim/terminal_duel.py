"""Bounded exhaustive final-round play against one explicit public hypothesis.

This solves a deterministic hypothetical subgame, not the hidden-information game.
No live enemy hand, draw order or game RNG is accessed. Any unsupported transition,
unresolved draw or exhausted budget invalidates the entire result; no partial
value is presented as a proof. Both players may pass permanently.
"""
from dataclasses import dataclass
from gwentsim import constants as C
from gwentsim.position import UnsupportedPosition
from gwentsim.opponent_belief import opponent_view


@dataclass(frozen=True)
class DuelResult:
    complete: bool
    values: tuple = ()
    nodes: int = 0
    reason: str = ''


class IncompleteDuel(Exception):
    pass


def solve_terminal(position, context, hypothesis, max_nodes=4096, max_cards=6):
    if context.round_index != 2 and not (context.own_losses == context.opponent_losses == 1):
        return DuelResult(False, reason='not_final_round')
    enemy = opponent_view(position, hypothesis)
    if position.unknown_draws or hypothesis.unsupported or position.random_recovery:
        return DuelResult(False, reason='unresolved_state')
    if len(position.hand)+len(enemy.hand) > max_cards:
        return DuelResult(False, reason='hand_limit')
    if position.leader_unmodeled(position.player) or enemy.leader_unmodeled(enemy.player):
        return DuelResult(False, reason='unmodeled_leader')
    # The current public model does not retain both players' shuffled deck pools.
    if any(s.leader_modeled(s.player) and s.leader_effect(s.player)==C.CardEffect_GraveyardShuffle
           for s in (position, enemy)):
        return DuelResult(False, reason='two_deck_shuffle_unmodeled')
    own = position.player; other = 1-own
    initial = position.clone(); initial.cards.update(enemy.cards)
    hands = {own: position.hand, other: enemy.hand}
    counts = {own: dict(position.counts), other: dict(enemy.counts)}
    nodes = 0

    def view(state, side, held, pools):
        active = state.clone(); active.player = side; active.hand = held[side]
        active.counts = dict(pools[side]); active.unknown_draws = 0; active.draw_value = 0
        if any(not active.supported(active.cards[k]) for k in active.hand):
            raise IncompleteDuel('unsupported_hand')
        return active

    def outcome(state):
        scores = state.scores(); gap = scores[own]-scores[other]
        if gap: return float(gap > 0)
        if context.own_faction != context.opponent_faction:
            if context.own_faction == C.FactionId_Nilfgaard: return 1.0
            if context.opponent_faction == C.FactionId_Nilfgaard: return 0.0
        return .5

    def next_state(state, side, held, pools, action):
        active = view(state, side, held, pools)
        after = active.apply(action)
        if after.unknown_draws: raise IncompleteDuel('unresolved_draw')
        following_hands = dict(held); following_hands[side] = after.hand
        following_pools = dict(pools); following_pools[side] = dict(after.counts)
        return after, following_hands, following_pools

    def visit(state, side, held, pools, passed, depth):
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes: raise IncompleteDuel('node_limit')
        if depth > 18: raise IncompleteDuel('depth_limit')
        if all(passed): return outcome(state)
        if passed[side]: return visit(state,1-side,held,pools,passed,depth)
        active = view(state, side, held, pools)
        flags = list(passed); flags[side] = True
        best = visit(state,1-side,held,pools,tuple(flags),depth+1)
        # 0 and 1 are exact game-value bounds, so these early exits are proofs.
        bound = 1.0 if side == own else 0.0
        if best == bound: return best
        for action in active.actions():
            after, new_hands, new_pools = next_state(state,side,held,pools,action)
            score = visit(after,side if passed[1-side] else 1-side,
                new_hands,new_pools,passed,depth+1)
            best = max(best,score) if side == own else min(best,score)
            if best == bound: break
        return best

    try:
        active = view(initial,own,hands,counts)
        view(initial,other,hands,counts)
        passed = [False,False]; passed[other] = context.opponent_passed
        values = []
        for action in (None, *active.actions()):
            if action is None:
                flags = list(passed); flags[own] = True
                score = visit(initial,other,hands,counts,tuple(flags),1)
            else:
                after,new_hands,new_pools = next_state(initial,own,hands,counts,action)
                score = visit(after,own if passed[other] else other,
                    new_hands,new_pools,tuple(passed),1)
            values.append((action,score))
        return DuelResult(True,tuple(values),nodes,'complete_hypothetical_subgame')
    except (IncompleteDuel, UnsupportedPosition) as exc:
        return DuelResult(False,nodes=nodes,reason=str(exc))
