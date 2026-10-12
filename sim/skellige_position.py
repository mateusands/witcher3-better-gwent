"""Skellige cards in the search model (experiment "skellige", simulator first).

Builds on the Mushroom/Morph projection (mushroom_position.py, checked against the native
engine) and its held-combination reserve (mushroom_reserve.py), and adds:
- a unit with Scorch (Clan Dimun Pirate): placed, then the normal global Scorch;
- a unit with a death summon (Kambi, the Cow): a plain unit inside the round. The native
  engine spawns its summon only when the board is cleared, so nothing changes this round.
Without these, the search never plays them itself and, with one in hand, never passes.
"""
from gwentsim import constants as C
from gwentsim.position import ROWS
from mushroom_reserve import MushroomReservePosition


class SkelligePosition(MushroomReservePosition):
    def supported(self, card):
        if card.is_type(C.CardType_Creature) and not card.is_type(C.CardType_Spy):
            effects = set(card.effects) - {C.CardEffect_None}
            if effects == {C.CardEffect_Scorch}:
                return True
            if effects == {C.CardEffect_SuicideSummon}:
                return len(card.targets) == 1 and card.targets[0] in self.catalog
        return super().supported(card)

    def place_unit(self, key, row, side, chain=()):
        super().place_unit(key, row, side, chain)
        card = self.cards[key]
        if card.is_type(C.CardType_Creature) and card.has(C.CardEffect_Scorch):
            self.scorch()

    def scorch(self, sides=(0, 1), rows=ROWS):
        eligible = [k for side in sides for row in rows for k in self.board[side, row]
                    if not self.cards[k].is_type(C.CardType_Hero) and self.cards[k].is_type(C.CardType_Creature)]
        maximum = max((self.power(k) for k in eligible), default=-1)
        targets = [k for k in eligible if self.power(k) == maximum]
        # A death summon only fires at the board clear; Morph/Mushroom sources just die.
        for key in targets:
            self.remove_from_board(key)
