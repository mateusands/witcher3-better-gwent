"""Isolated held-hand transformation ceiling after a normal round clear.

Own held sources only, no death summons, draw-order or opponent-card access.
This remains V7's uncontested power heuristic, not a promised future score.
"""
from contextlib import contextmanager
from dataclasses import replace
from gwentsim import constants as C
from gwentsim.position import Position, ROWS, ROW_FLAGS
from mushroom_position import MushroomPosition
import mushroom_policy


class _ReserveView(Position):
    def leader_reserve(self):
        cards, recoveries = super().leader_reserve()
        blocked = self._blocked_indices
        return tuple(replace(c, rows=tuple(r for r in c.rows if r not in blocked))
                     if c.horn else c for c in cards), recoveries


class MushroomReservePosition(MushroomPosition):
    def reserve(self):
        reference = Position(**self.__dict__).reserve()
        cards = [self.cards[k] for k in self.hand]
        morphs = [c for c in cards if c.has(C.CardEffect_Morph) and self.supported(c)]
        mushrooms = [c for c in cards if set(c.effects) == {C.CardEffect_Mushroom}
                     and self.supported(c)]
        if not morphs or not mushrooms:
            return reference
        relevant = {r for r in ROWS for c in morphs if c.is_type(ROW_FLAGS[r])}
        # Compress interchangeable modifiers into at most 27 active/occupied masks.
        # Unit sources keep their identity and row choice for Morale/Horn counting.
        states = {(frozenset(), frozenset(), ())}
        for card in mushrooms:
            choices = tuple(r for r in ROWS if r in relevant and card.is_type(ROW_FLAGS[r]))
            following = set()
            for active, occupied, units in states:
                following.add((active, occupied, units))
                for row in choices:
                    if card.is_type(C.CardType_Row_Modifier):
                        if row not in occupied:
                            following.add((active | {row}, occupied | {row}, units))
                    else:
                        following.add((active | {row}, occupied, units + ((card.key, row),)))
            if len(following) > 4096:
                return reference  # Explicit conservative bound for non-native huge hands.
            states = following
        best = reference
        for active, occupied, units in sorted(states, key=repr):
            if not active:
                continue
            view = _ReserveView(**self.__dict__).clone()
            view._blocked_indices = {i for i, r in enumerate((5, 4, 3)) if r in occupied}
            # Deployed row Mushroom has zero power and takes a shared modifier slot.
            # Unused copies carry no additional transformation benefit.
            view.hand = tuple(k for k in view.hand if not (
                view.cards[k] in mushrooms and view.cards[k].is_type(C.CardType_Row_Modifier)))
            for key, row in units:
                card = view.cards[key]
                view.cards[key] = replace(card,
                    types=(card.types & ~C.CardType_SeigeRangedMelee) | ROW_FLAGS[row],
                    effects=(C.CardEffect_None,))
            for card in morphs:
                rows = tuple(r for r in active if card.is_type(ROW_FLAGS[r]))
                if rows:
                    target = self.catalog[card.targets[0]]
                    view.cards[card.key] = replace(target, key=card.key, owner=card.owner,
                        player=card.player, row=1, applied=(),
                        types=(target.types & ~C.CardType_SeigeRangedMelee)
                              | sum(ROW_FLAGS[r] for r in rows))
            for card in cards:
                if card.is_type(C.CardType_Row_Modifier) and card.has(C.CardEffect_Horn):
                    flags = card.types
                    for row in occupied:
                        flags &= ~ROW_FLAGS[row]
                    view.cards[card.key] = replace(card, types=flags)
            best = max(best, view.reserve())
        return best


@contextmanager
def mushroom_reserve_hook(seat, audit):
    original = mushroom_policy.MushroomPosition
    mushroom_policy.MushroomPosition = MushroomReservePosition
    try:
        with mushroom_policy.mushroom_hook(seat, audit):
            yield
    finally:
        mushroom_policy.MushroomPosition = original
