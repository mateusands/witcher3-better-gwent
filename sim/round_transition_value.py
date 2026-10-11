"""Original V7 experiment for the conditional final-round resource estimate.

After round two, only one decisive round remains. Credit the Northern Realms draw
to the winner, and do not apply the earlier concession allowance to that final.
Resource strength/draw means remain heuristics; no hidden deck/order is consulted.
"""
from math import sqrt
from gwentsim import constants as C
from gwentsim.sequence_search import utility as original_utility,sigmoid,faction_carry


def round_transition_utility(position,context,depth,reserve,opponent_mean,passing=False,opponent_reserve=None):
    if context.round_index!=1 or context.own_losses>=1 and context.opponent_losses>=1:
        return original_utility(position,context,depth,reserve,opponent_mean,passing,opponent_reserve)
    if (context.own_losses,context.opponent_losses) not in ((0,1),(1,0)):
        return original_utility(position,context,depth,reserve,opponent_mean,passing,opponent_reserve)
    own=position.player;other=1-own;scores=position.scores()
    replies=0 if context.opponent_passed else max(0,depth-1)
    count=max(0,context.opponent_hand_count-replies)
    gap=scores[own]-scores[other]-replies*opponent_mean
    # A tie can already finish the match after winning round one. Preserve the
    # reference's exact endpoint and Nilfgaard rule before estimating any future.
    if context.opponent_passed and gap==0 and context.opponent_losses==1 and context.own_losses==0 and not (
            context.opponent_faction==C.FactionId_Nilfgaard and context.own_faction!=context.opponent_faction):
        return 1
    wins=gap>=0 if context.wins_ties else gap>0
    opposing=(count*opponent_mean if opponent_reserve is None else opponent_reserve)+(3 if context.opponent_leader_available else 0)
    scale=4+sqrt(max(1,count))*2
    if not position.hand and not position.unknown_draws and not context.own_leader_available and not position.leader_modeled(own):passing=True
    if context.opponent_passed:p=float(wins)
    elif passing:p=sigmoid((gap-opposing)/scale) if wins else 0
    else:p=sigmoid((gap+(reserve-opposing)*.25)/scale)
    own_future=reserve+faction_carry(position,own,context.own_faction,2)
    other_future=opposing+faction_carry(position,other,context.opponent_faction,2)
    total=sum(position.counts.values())
    own_draw=0
    if context.own_faction==C.FactionId_Northern_Kingdom and total>position.unknown_draws:
        own_draw=sum(position.catalog[t].power*n for t,n in position.counts.items())/total
    # Opponent deck availability is unknown; the same provisional mean-card prior
    # as V7 is retained. This corrects the winner, not that uncertainty.
    enemy_draw=opponent_mean if context.opponent_faction==C.FactionId_Northern_Kingdom else 0
    if context.opponent_losses==1:
        after_loss=sigmoid((own_future-other_future-enemy_draw)/scale)
        return p+(1-p)*after_loss
    after_win=sigmoid((own_future+own_draw-other_future)/scale)
    return p*after_win
