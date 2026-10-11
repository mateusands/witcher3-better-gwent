"""Original public-state row projection for ordinary units, morale and Tight Bond.

Only cloned instances are changed. Unsupported effects deliberately return no
estimate. This is immediate evaluation, not prediction of an opponent response.
"""
from copy import copy
from dataclasses import dataclass

from . import constants as C
from .horn_evaluation import ROWS

SUPPORTED_EFFECTS = {C.CardEffect_None, C.CardEffect_ImproveNeighbours, C.CardEffect_SameTypeMorale}


@dataclass(frozen=True)
class UnitAlternative:
    row: int
    gain: int
    horn_sequence_gain: int | None = None


def supported_unit(card):
    t = card.templateRef
    return (t.isType(C.CardType_Creature) and not t.isType(C.CardType_Spy)
            and set(t.effectFlags) <= SUPPORTED_EFFECTS)


def project_row(manager, card, row, player):
    originals = manager.getCardInstanceList(row, player)
    baseline = sum(unit.getTotalPower() for unit in originals)
    clones = []
    for original in originals:
        clone = copy(original)
        clone.effectedByCardsRefList = list(original.effectedByCardsRefList)
        clones.append(clone)
    played = copy(card)
    played.inList, played.listsPlayer = row, player
    played.effectedByCardsRefList = manager.cardEffectManager.getEffectsForList(row, player)
    for unit in clones:
        if unit.templateRef.isType(C.CardType_Hero):
            continue
        if card.templateRef.hasEffect(C.CardEffect_ImproveNeighbours) and not unit.templateRef.hasEffect(C.CardEffect_UnsummonDummy):
            unit.effectedByCardsRefList.append(played)
        if card.templateRef.hasEffect(C.CardEffect_SameTypeMorale) and unit.templateId in card.templateRef.summonFlags:
            unit.effectedByCardsRefList.append(played)
            played.effectedByCardsRefList.append(unit)
    return baseline, clones + [played]


def unit_alternatives(manager, card, player, horn=None):
    if card not in manager.getCardInstanceList(1, player):
        raise ValueError('unit must be in the acting player hand')
    if not supported_unit(card):
        return ()
    if horn is not None and (horn not in manager.getCardInstanceList(1, player) or not horn.templateRef.hasEffect(C.CardEffect_Horn) or not horn.templateRef.isType(C.CardType_Row_Modifier)):
        raise ValueError('expected an own-hand Horn modifier')
    results = []
    for row, slot in ROWS:
        if not card.canBePlacedInSlot(row, player):
            continue
        baseline, projected = project_row(manager, card, row, player)
        after = sum(unit.getTotalPower() for unit in projected)
        sequence = None
        if horn is not None and horn.canBePlacedInSlot(slot, player):
            for unit in projected:
                if unit.templateRef.isType(C.CardType_Creature) and not unit.templateRef.isType(C.CardType_Hero):
                    unit.effectedByCardsRefList.append(horn)
            sequence = sum(unit.getTotalPower() for unit in projected) - baseline
        results.append(UnitAlternative(row, after - baseline, sequence))
    return tuple(results)
