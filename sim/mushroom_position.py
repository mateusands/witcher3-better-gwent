"""Original isolated public-state projection for vanilla Mushroom transformations.

Same instance changes template, then reapplies row and transformed unit effects.
Only pure Mushroom/Morph sources and bounded deterministic target effects are
supported. Core Position, native execution and future-resource estimates remain
unchanged. Projection fidelity is separate from measured AI strength.
"""
from dataclasses import replace
from gwentsim import constants as C
from gwentsim.position import Position,UnsupportedPosition,ROWS,ROW_FLAGS,MODS

TARGET_EFFECTS={C.CardEffect_None,C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale}


class MushroomPosition(Position):
    def supported(self,card):
        if set(card.effects)=={C.CardEffect_Mushroom}:
            return card.is_type(C.CardType_Creature) or card.is_type(C.CardType_Row_Modifier)
        if set(card.effects)=={C.CardEffect_Morph}:
            if not card.is_type(C.CardType_Creature) or len(card.targets)!=1:return False
            target=self.catalog.get(card.targets[0])
            return bool(target and target.is_type(C.CardType_Creature)
                and not card.is_type(C.CardType_Hero) and not target.is_type(C.CardType_Hero)
                and set(target.effects)<=TARGET_EFFECTS
                and card.types&C.CardType_SeigeRangedMelee==target.types&C.CardType_SeigeRangedMelee)
        return super().supported(card)

    def transform(self,key):
        card=self.cards[key]
        if not card.has(C.CardEffect_Morph):return
        if not self.supported(card):raise UnsupportedPosition('unmodeled Mushroom transformation target')
        target=self.catalog[card.targets[0]]
        current=replace(target,key=key,owner=card.owner,player=card.player,
            row=card.row,applied=card.applied,banished_on_clear=card.banished_on_clear)
        self.cards[key]=current
        side,row=current.player,current.row
        for source in self.effects[side,row]:
            if source!=key and source not in self.cards[key].applied:self.add_effect(key,source)
        if current.has(C.CardEffect_ImproveNeighbours):
            for other in self.board[side,row]:
                unit=self.cards[other]
                if other!=key and not unit.is_type(C.CardType_Hero) and not unit.has(C.CardEffect_UnsummonDummy) and key not in unit.applied:
                    self.add_effect(other,key)
            if key not in self.effects[side,row]:self.effects[side,row]+=(key,)
        if current.has(C.CardEffect_SameTypeMorale):
            for other in self.board[side,row]:
                unit=self.cards[other]
                if other!=key and not unit.is_type(C.CardType_Hero) and unit.template in current.targets:
                    if key not in unit.applied:self.add_effect(other,key)
                    if other not in self.cards[key].applied:self.add_effect(key,other)

    def transform_row(self,side,row):
        for key in tuple(self.board[side,row]):
            if self.cards[key].has(C.CardEffect_Morph):self.transform(key)

    def place_modifier(self,card,slot,side):
        if not card.has(C.CardEffect_Mushroom):return super().place_modifier(card,slot,side)
        row=next(r for r,s in MODS.items() if s==slot)
        self.cards[card.key]=replace(card,row=slot,player=side,applied=())
        self.board[side,slot]+=(card.key,)
        # Mushroom triggers a template change; it is not a persistent power
        # modifier attached to every unit like Horn or Morale.
        self.transform_row(side,row)

    def place_unit(self,key,row,side,chain=()):
        super().place_unit(key,row,side,chain)
        card=self.cards[key]
        if card.has(C.CardEffect_Mushroom):self.transform_row(side,row)
        elif card.has(C.CardEffect_Morph) and any(self.cards[k].has(C.CardEffect_Mushroom)
                for k in (*self.board[side,row],*self.board[side,MODS[row]]) if k!=key):
            self.transform(key)
