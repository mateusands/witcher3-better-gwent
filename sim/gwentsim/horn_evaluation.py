"""Original, simulator-only Horn evaluator using public board state.

Measure every affected unit's before/after native power, without committing a
transaction, drawing cards or consuming RNG. Heroes and existing Horn effects
are handled by the rule engine, not changed by the evaluator.
"""
from dataclasses import dataclass

from . import constants as C

ROWS = ((5, 8), (4, 7), (3, 6))  # Native board row -> corresponding modifier slot.


@dataclass(frozen=True)
class HornAlternative:
    row: int
    modifier_slot: int
    gain: int


def horn_alternatives(manager, horn, player):
    if not horn.templateRef.isType(C.CardType_Row_Modifier) or not horn.templateRef.hasEffect(C.CardEffect_Horn):
        raise ValueError('expected a Horn row-modifier card')
    if horn not in manager.getCardInstanceList(1, player):
        raise ValueError('Horn must be in the acting player hand')
    alternatives = []
    for row, slot in ROWS:
        # Native UI permits one row modifier in each slot.
        if not horn.canBePlacedInSlot(slot, player):
            continue
        gain = 0
        for unit in manager.getCardInstanceList(row, player):
            if not unit.templateRef.isType(C.CardType_Creature) or unit.templateRef.isType(C.CardType_Hero):
                continue
            before = unit.getTotalPower()
            unit.effectedByCardsRefList.append(horn)
            try:
                gain += unit.getTotalPower() - before
            finally:
                unit.effectedByCardsRefList.pop()
        alternatives.append(HornAlternative(row, slot, gain))
    return tuple(alternatives)


def best_horn_alternative(alternatives):
    # Stable deterministic tie: melee, ranged, siege. No game RNG is consumed.
    return max(alternatives, key=lambda option: option.gain, default=None)
