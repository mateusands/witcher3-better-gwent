"""Original conservative exchange policy for redundant, supported Muster cards.

Keep an owned hand card which summons the returned copy from the owned deck.
This preserves that supported group when deployed and frees a starting-hand slot.
No numeric spell ranking, hidden order, enemy cards or general optimality claim.
"""
from dataclasses import dataclass,asdict
from gwentsim import constants as C
from mulligan_policy import initial_hand_potential


@dataclass(frozen=True)
class StructuralDecision:
    source:int|None
    before:float
    expected_after:None=None
    alternatives:tuple=()
    revision:str='structural-mulligan-v1'

    def audit(self):return asdict(self)


def choose_structural_mulligan(position):
    before=initial_hand_potential(position)
    if not sum(position.counts.values()):return StructuralDecision(None,before)
    def safe(card):
        return (card.is_type(C.CardType_Creature) and not card.is_type(C.CardType_Spy)
            and card.has(C.CardEffect_SummonClones)
            and set(card.effects)<={C.CardEffect_None,C.CardEffect_SummonClones}
            and all(t in position.catalog and position.supported(position.catalog[t])
                for t in card.targets))
    choices=[]
    for source in position.hand:
        card=position.cards[source]
        if not safe(card):continue
        for retained in position.hand:
            keeper=position.cards[retained]
            if retained!=source and safe(keeper) and card.template in keeper.targets:
                choices.append(dict(source=source,retained=retained,criterion='retained_Muster_summons_returned_copy'))
                break
    if not choices:return StructuralDecision(None,before)
    selected=min(choices,key=lambda c:(position.cards[c['source']].power,c['source']))
    return StructuralDecision(selected['source'],before,alternatives=tuple(choices))
