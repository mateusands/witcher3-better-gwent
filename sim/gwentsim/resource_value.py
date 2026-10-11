"""Original experimental spy reserve accounting from own remaining composition.

A spy gives its strength to the opposing board and draws at most two cards. Native
V7 reserve instead credits its printed strength as a positive future asset. We use
the same base-power draw estimate as Position.place_unit, minus the opposing points.
This is an explicit heuristic, not exact synergy, draw-order or win prediction.
"""
from dataclasses import dataclass
from . import constants as C
from .position import Position


def spy_reserve_adjustment(position):
    total=sum(position.counts.values())
    available=max(0,total-position.unknown_draws)
    mean=sum(position.catalog[t].power*n for t,n in position.counts.items())/total if total else 0
    old_total=0;costs=[]
    for key in position.hand:
        card=position.cards[key]
        if not (card.is_type(C.CardType_Spy) and card.has(C.CardEffect_Draw2)):continue
        old_total+=max(card.power,*(position.weights.get(e,0) for e in card.effects),0)
        costs.append(card.power*(2 if position.double_spy and not card.is_type(C.CardType_Hero) else 1))
    # Joint draw capacity: two retained spies cannot each buy the same final card.
    # Identical draw ability / common mean makes the cheapest useful spies optimal
    # within this heuristic. Unprofitable spies receive no speculative draw credit.
    value=0
    for cost in sorted(costs):
        drawn=min(2,available)
        gain=drawn*mean-cost
        if gain>0:value+=gain;available-=drawn
    return value-old_total



@dataclass
class ResourcePosition(Position):
    """Correct owned resources without revaluing provisional enemy hypotheses.

    Opponent composition is an uncalibrated catalog prior. Applying the owned-deck
    correction there changed decisions even with no owned spies. Keep reference
    opponent reserve until that separate belief model has independent evidence.
    The observer identity survives clones and hypothetical perspective changes.
    """
    valuation_owner:int|None=None

    def __post_init__(self):
        if self.valuation_owner is None:self.valuation_owner=self.player

    def reserve(self):
        adjustment=spy_reserve_adjustment(self) if self.player==self.valuation_owner else 0
        return super().reserve()+adjustment
