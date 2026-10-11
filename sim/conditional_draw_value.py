"""Original controlled V7 experiment: correct winner draws without retuning phases.

Keeps V7's concession allowance and other resource assumptions. Isolates the
Northern Realms draw credit from the rejected round-transition-v1 phase change.
Enemy draw availability/mean and match prospects remain provisional heuristics.
"""
from math import sqrt
from gwentsim import constants as C
from gwentsim.sequence_search import utility as original_utility,sigmoid,faction_carry


def conditional_draw_utility(position,context,depth,reserve,opponent_mean,passing=False,opponent_reserve=None):
    reference=original_utility(position,context,depth,reserve,opponent_mean,passing,opponent_reserve)
    if context.round_index!=1 or (context.own_losses,context.opponent_losses) not in ((0,1),(1,0)):return reference
    own_north=context.own_faction==C.FactionId_Northern_Kingdom
    enemy_north=context.opponent_faction==C.FactionId_Northern_Kingdom
    total=sum(position.counts.values())
    if context.opponent_losses==1:
        if not (own_north or enemy_north):return reference
    elif not (own_north and total and total<=position.unknown_draws):return reference
    own=position.player;other=1-own;scores=position.scores()
    replies=0 if context.opponent_passed else max(0,depth-1)
    count=max(0,context.opponent_hand_count-replies)
    gap=scores[own]-scores[other]-replies*opponent_mean
    if context.opponent_passed and gap==0 and context.opponent_losses==1 and context.own_losses==0 and not (
            context.opponent_faction==C.FactionId_Nilfgaard and context.own_faction!=context.opponent_faction):return reference
    wins=gap>=0 if context.wins_ties else gap>0
    opposing=(count*opponent_mean if opponent_reserve is None else opponent_reserve)+(3 if context.opponent_leader_available else 0)
    scale=4+sqrt(max(1,count))*2
    if not position.hand and not position.unknown_draws and not context.own_leader_available and not position.leader_modeled(own):passing=True
    if context.opponent_passed:p=float(wins)
    elif passing:p=sigmoid((gap-opposing)/scale) if wins else 0
    else:p=sigmoid((gap+(reserve-opposing)*.25)/scale)
    own_future=reserve+faction_carry(position,own,context.own_faction,2)
    other_future=opposing+faction_carry(position,other,context.opponent_faction,2)
    previous_draw=sum(position.catalog[t].power*n for t,n in position.counts.items())/total if own_north and total else 0
    previous_future=sigmoid((own_future+previous_draw-other_future+opponent_mean)/scale)
    if context.opponent_losses==1:
        corrected_future=sigmoid((own_future-other_future-(opponent_mean if enemy_north else 0)+opponent_mean)/scale)
        adjustment=(1-p)*(corrected_future-previous_future)
    else:
        corrected_future=sigmoid((own_future-other_future+opponent_mean)/scale)
        adjustment=p*(corrected_future-previous_future)
    return min(1,max(0,reference+adjustment))
