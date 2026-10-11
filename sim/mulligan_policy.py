"""Original own-deck expected-hand-value mulligan experiment.

Uniform remaining-template probabilities are a provisional exchangeability prior,
not an assertion that the native comparator shuffle is uniform. The native exchange
returns the selected card to the bottom before drawing; it cannot be drawn back
immediately while other cards remain. No shuffled order or opponent cards are read.
The score is V7's hand potential, not a calibrated match-winning probability.
"""
from dataclasses import dataclass,replace,asdict
from itertools import product
from gwentsim import constants as C
from gwentsim.position import ROWS,ROW_FLAGS
from gwentsim.resource_value import spy_reserve_adjustment


@dataclass(frozen=True)
class MulliganDecision:
    source:int|None
    before:float
    expected_after:float
    alternatives:tuple
    revision:str='own-deck-mulligan-v3.1'

    def audit(self):return asdict(self)


def exchanged(position,source,template):
    """Project a native exchange without observing which card is actually next."""
    if source not in position.hand:raise ValueError('source outside own hand')
    if position.counts.get(template,0)<=0:raise ValueError('template outside remaining own deck')
    state=position.clone();old=state.cards[source]
    state.counts[template]-=1
    state.counts[old.template]=state.counts.get(old.template,0)+1
    state.cards[source]=replace(state.catalog[template],key=source,owner=state.player,
        player=state.player,row=1,applied=())
    return state


def initial_hand_potential(position):
    """Hand potential including native transformation and later death summons.

    This is a match-hand heuristic, not a current-round score or win probability.
    Death summons are credited as a later-round unit; no future callback is run.
    Joint Mushroom row choices respect the single modifier slot shared with Horn.
    Native gameplay transitions and V7's reserve evaluator remain unchanged.
    """
    cards=[position.cards[k] for k in position.hand]
    mushrooms=[c for c in cards if c.has(C.CardEffect_Mushroom)]
    choices=[]
    for card in mushrooms:
        rows=tuple(row for row in ROWS if card.is_type(ROW_FLAGS[row]))
        choices.append((None,)+rows)
    best=float('-inf')
    for assignment in product(*choices):
        transformed=position.clone();active={r for r in assignment if r is not None}
        occupied={r for c,r in zip(mushrooms,assignment)
            if r is not None and c.is_type(C.CardType_Row_Modifier)}
        # Two row modifiers cannot be deployed in the same slot.
        slots=[r for c,r in zip(mushrooms,assignment)
            if r is not None and c.is_type(C.CardType_Row_Modifier)]
        if len(slots)!=len(occupied):continue
        for card,row in zip(mushrooms,assignment):
            if card.is_type(C.CardType_Row_Modifier):
                transformed.hand=tuple(k for k in transformed.hand if k!=card.key)
            elif row is not None:
                flags=(card.types & ~C.CardType_SeigeRangedMelee)|ROW_FLAGS[row]
                transformed.cards[card.key]=replace(card,types=flags,
                    effects=tuple(e for e in card.effects if e!=C.CardEffect_Mushroom))
        for card in cards:
            target=None
            if len(card.targets)==1 and card.targets[0] in position.catalog:
                if card.has(C.CardEffect_SuicideSummon):
                    target=position.catalog[card.targets[0]]
                elif card.has(C.CardEffect_Morph):
                    rows=tuple(r for r in active if card.is_type(ROW_FLAGS[r]))
                    if rows:
                        target=position.catalog[card.targets[0]]
                        flags=(target.types & ~C.CardType_SeigeRangedMelee)|sum(ROW_FLAGS[r] for r in rows)
                        target=replace(target,types=flags)
            if target is not None:
                transformed.cards[card.key]=replace(target,key=card.key,owner=position.player,
                    player=position.player,row=1,applied=())
            if card.is_type(C.CardType_Row_Modifier) and card.has(C.CardEffect_Horn):
                flags=card.types
                for row in occupied:flags&=~ROW_FLAGS[row]
                transformed.cards[card.key]=replace(card,types=flags)
        best=max(best,transformed.reserve()+spy_reserve_adjustment(transformed))
    return best


def choose_mulligan(position,*,score=None):
    """Choose one positive expected-value exchange, or keep the hand.

    Recompute after the real draw, up to two exchanges. This is greedy adaptive
    selection; it does not claim an optimal two-exchange contingent strategy.
    """
    score=initial_hand_potential if score is None else score
    before=score(position);total=sum(position.counts.values())
    if not total:return MulliganDecision(None,before,before,())
    best=before;source=None;alternatives=[]
    for key in position.hand:
        expected=sum(count*score(exchanged(position,key,template))
            for template,count in sorted(position.counts.items()) if count>0)/total
        alternatives.append(dict(source=key,expectedAfter=expected))
        if expected>best+1e-9:best,source=expected,key
    return MulliganDecision(source,before,best,tuple(alternatives))
