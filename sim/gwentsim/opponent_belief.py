"""Original public-catalog opponent hypotheses, never actual hidden cards.

This deliberately provisional prior has no knowledge of the opponent's selected
collection/deck. Revealed instances reduce assumed template capacity (one hero,
three ordinary copies). Local random sampling cannot consume game randomness.
Unsupported effects stay in the hypothesis and in its coverage report.
"""
from collections import Counter
from dataclasses import dataclass,replace
import hashlib
import json
from random import Random
from . import constants as C


@dataclass(frozen=True)
class Hypothesis:
    hand:tuple
    counts:tuple
    unsupported:int
    prior:str


def public_seed(position,context):
    # The snapshot already enforces the information boundary. Hand identities
    # here are our own; all other card identities are publicly revealed.
    fields=dict(context.__dict__)
    if not fields.get('opponent_known'):fields.pop('opponent_known',None)  # unchanged seed without it
    payload=(position.player,fields,position.hand,
        sorted((k,c.template,c.owner,c.player,c.row,c.applied) for k,c in position.cards.items()),
        sorted(position.counts.items()),sorted(position.board.items()))
    return int.from_bytes(hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).digest()[:8],'big')


def hypotheses(position,context,samples=4,*,rng=None):
    if samples<1:raise ValueError('at least one hypothesis is required')
    other=1-position.player
    seen=Counter(c.template for c in position.cards.values() if c.owner==other)
    pool=[]
    for template in sorted(position.catalog):
        card=position.catalog[template]
        if card.faction not in (C.FactionId_Neutral,context.opponent_faction):continue
        if not (card.is_type(C.CardType_Creature) or card.is_type(C.CardType_Weather) or
                card.is_type(C.CardType_Spell) or card.is_type(C.CardType_Row_Modifier)):continue
        cap=1 if card.is_type(C.CardType_Hero) else 3
        pool.extend([template]*max(0,cap-seen[template]))
    # Publicly known hand cards are in every hypothesis; only the other slots are sampled.
    known=[t for t in getattr(context,'opponent_known',()) if t in position.catalog][:context.opponent_hand_count]
    for template in known:
        if template in pool:pool.remove(template)
    if len(pool)<context.opponent_hand_count-len(known):
        return ()  # Insufficient catalog coverage must not invent card copies.
    seed=public_seed(position,context);results=[]
    for index in range(samples):
        # Default preserves the V7 reference exactly. ISMCTS can supply its own
        # isolated RNG to draw fresh hypotheses on each tree iteration.
        random=Random(seed+index) if rng is None else rng
        remaining=list(pool);selected=[]
        # Three explicit sensitivity priors, not estimated probabilities of the
        # player's actual collection. Specials cannot silently disappear.
        prior=('balanced','unit-heavy','special-heavy')[index%3]
        def draw():
            weights=[]
            for template in remaining:
                card=position.catalog[template]
                creature=card.is_type(C.CardType_Creature)
                weights.append(1 if prior=='balanced' else
                    (3 if creature else 1) if prior=='unit-heavy' else (1 if creature else 3))
            slot=random.choices(range(len(remaining)),weights=weights,k=1)[0]
            return remaining.pop(slot)
        # Experiment "scorch-prior": players almost always carry Scorch, so every other sampled
        # hand holds one (when the public catalog still allows a copy).
        forced=[]
        if index%2==1 and context.opponent_hand_count>len(known):
            from . import response_v8
            if response_v8.flag('scorch-prior',position.player):
                scorch=min((t for t in remaining if position.catalog[t].has(C.CardEffect_Scorch)
                            and not position.catalog[t].is_type(C.CardType_Creature)),default=None)
                if scorch is not None:
                    remaining.remove(scorch);forced=[scorch]
        for slot in range(context.opponent_hand_count):
            template=known[slot] if slot<len(known) else forced.pop() if forced else draw()
            selected.append(replace(position.catalog[template],
                key=-200000000-index*1000-slot,owner=other,player=other,row=1,applied=()))
        # A generic sixteen-card remainder is another explicit prior, not the
        # actual NPC deck or an alleged future draw sequence. Only counts survive.
        counts=Counter(draw() for _ in range(min(16,len(remaining))))
        results.append(Hypothesis(tuple(selected),tuple(sorted(counts.items())),
            sum(not position.supported(c) for c in selected),prior))
    return tuple(results)


def opponent_view(position,hypothesis):
    other=1-position.player
    view=position.clone()
    view.player=other;view.hand=tuple(c.key for c in hypothesis.hand)
    view.cards.update((c.key,c) for c in hypothesis.hand)
    view.counts=dict(hypothesis.counts);view.unknown_draws=0;view.draw_value=0
    return view
