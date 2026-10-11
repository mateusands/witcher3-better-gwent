"""Original own-hand reserve estimate after a normal board clear.

Bounded maximization within the supported unit/Horn subset; unsupported effects use
explicit provisional reserve weights. This is potential, not expected round score.
No opponent hand, shuffled draw order, runtime mutation or RNG is consulted.
"""
from dataclasses import dataclass
from itertools import product, islice
from . import constants as C

ROW_TYPES=(C.CardType_Melee,C.CardType_Ranged,C.CardType_Siege)


@dataclass(frozen=True)
class ReserveCard:
    key: int
    template: int
    power: int
    rows: tuple[int,...]
    hero: bool=False
    morale: bool=False
    bond: bool=False
    bond_targets: tuple[int,...]=()
    horn: bool=False
    unsupported_value: float=0
    summons: tuple=()


def supported_reserve_power(cards):
    # Copies are conditional on a retained hand trigger; multiple triggers must not
    # count the same own-deck copy twice. No future draw order is represented.
    expanded={c.key:c for c in cards}
    for card in cards:
        for summoned in card.summons:
            expanded.setdefault(summoned.key,summoned)
    cards=tuple(expanded.values())
    units=[c for c in cards if not c.horn and c.rows]
    horns=[c for c in cards if c.horn]
    if not horns and not any(c.morale or c.bond for c in units):
        return sum(c.power for c in units)+sum(c.unsupported_value for c in cards)
    maximum=0
    for assignment in islice(product(*(u.rows for u in units)), 4096):
        totals=[0,0,0];horn_gains=[0,0,0]
        for unit,row in zip(units,assignment):
            if unit.hero:
                power=unit.power
            else:
                morale=sum(other.morale and other.key!=unit.key for other,r in zip(units,assignment) if r==row)
                bonds=sum(other.key!=unit.key and other.bond and unit.template in other.bond_targets
                          for other,r in zip(units,assignment) if r==row)
                power=unit.power*(1+bonds)+morale
                horn_gains[row]+=power
            totals[row]+=power
        # One modifier per row; Horn does not affect heroes or stack.
        reachable={0}
        for horn in horns:
            reachable |= {mask | (1 << row) for mask in tuple(reachable)
                          for row in horn.rows if not mask & (1 << row)}
        horn_best=max(sum(horn_gains[r] for r in range(3) if mask & (1 << r))
                      for mask in reachable)
        maximum=max(maximum,sum(totals)+horn_best)
    return maximum+sum(c.unsupported_value for c in cards)


def reserve_marginals(cards):
    full=supported_reserve_power(cards)
    return {c.key:max(0,full-supported_reserve_power(tuple(x for x in cards if x.key!=c.key))) for c in cards}


def describe_hand(hand, card_values=None, own_deck=None, templates=None):
    cards=[]
    for unit in hand:
        t=unit.templateRef
        rows=tuple(i for i,flag in enumerate(ROW_TYPES) if t.isType(flag))
        supported=(t.isType(C.CardType_Creature) and not t.isType(C.CardType_Spy)
                   and set(t.effectFlags)<={C.CardEffect_None,C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale}
                   | ({C.CardEffect_SummonClones} if own_deck is not None else set()))
        horn=t.isType(C.CardType_Row_Modifier) and t.hasEffect(C.CardEffect_Horn)
        # Unsupported specials retain a reserve weight rather than becoming worthless.
        weights=[]
        if card_values is not None:
            weights=[card_values.getEffectValueDictionary().get(effect,0) for effect in t.effectFlags]
            if t.isType(C.CardType_Weather):weights.append(card_values.weatherCardValue)
        value=0 if supported or horn else max(t.power,unit.getOptimalTransaction().strategicValue,0,*weights)
        summons=[]
        if own_deck is not None and supported and t.hasEffect(C.CardEffect_SummonClones):
            for template_id in sorted(set(t.summonFlags or ())):
                target=templates[template_id]
                target_rows=tuple(i for i,flag in enumerate(ROW_TYPES) if target.isType(flag))
                simple=(target.isType(C.CardType_Creature) and not target.isType(C.CardType_Spy)
                        and set(target.effectFlags)<={C.CardEffect_None,C.CardEffect_SummonClones})
                for index in range(own_deck.numCopiesLeft(template_id)):
                    summons.append(ReserveCard(-(template_id*10000+index+1),template_id,target.power,
                        target_rows if simple else (),hero=target.isType(C.CardType_Hero),
                        unsupported_value=0 if simple else target.power))
        cards.append(ReserveCard(unit.instanceId,unit.templateId,t.power,rows if supported or horn else (),
            hero=t.isType(C.CardType_Hero),morale=supported and t.hasEffect(C.CardEffect_ImproveNeighbours),
            bond=supported and t.hasEffect(C.CardEffect_SameTypeMorale),bond_targets=tuple(t.summonFlags or ()),
            horn=horn,unsupported_value=value,summons=tuple(summons)))
    return tuple(cards)
