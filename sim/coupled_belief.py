"""Original catalog-coupling diagnostic for the rejected Scorch pool experiment.

Per-copy deterministic exponential priorities preserve the relative order of
existing entries when a missing entry is added. -log(U)/weight is equivalent to
ranking U**(1/weight) in reverse order (A-ES weighted sampling, Efraimidis 2015,
https://arxiv.org/html/1012.0256, section 3.2). No published code is used.

This changes the sampler, not its provisional weights. It is NOT calibrated
opponent inference or a promoted policy. The existing snapshot seed still changes
between turns; this module does not implement persistent match-level beliefs.
"""
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from math import log
from gwentsim import constants as C
from gwentsim.opponent_belief import Hypothesis, public_seed


def exponential_priority(seed, scenario, template, copy, weight):
    if weight <= 0:
        raise ValueError('positive sampling weight required')
    payload=f'gwai-coupled-v1:{seed}:{scenario}:{template}:{copy}'.encode()
    bits=int.from_bytes(sha256(payload).digest()[:8],'big') >> 11
    # Exclude both endpoints before taking the logarithm.
    uniform=(bits+1)/(2**53+1)
    return -log(uniform)/weight


def ranked_copies(position, context, scenario, *, include_scorch):
    if scenario < 0:
        raise ValueError('nonnegative scenario required')
    seen=Counter(c.template for c in position.cards.values() if c.owner==1-position.player)
    prior=('balanced','unit-heavy','special-heavy')[scenario%3]
    seed=public_seed(position,context);entries=[]
    for template in sorted(position.catalog):
        card=position.catalog[template]
        if card.faction not in (C.FactionId_Neutral,context.opponent_faction):continue
        ordinary=any(card.is_type(flag) for flag in (
            C.CardType_Creature,C.CardType_Weather,C.CardType_Spell,C.CardType_Row_Modifier))
        extra=include_scorch and card.is_type(C.CardType_Global_Effect) and set(card.effects)=={C.CardEffect_Scorch}
        if not (ordinary or extra):continue
        creature=card.is_type(C.CardType_Creature)
        weight=1 if prior=='balanced' else (3 if creature else 1) if prior=='unit-heavy' else (1 if creature else 3)
        cap=1 if card.is_type(C.CardType_Hero) else 3
        for copy in range(seen[template],cap):
            entries.append((exponential_priority(seed,scenario,template,copy,weight),template,copy))
    return tuple((template,copy) for _,template,copy in sorted(entries))


def coupled_hypotheses(position, context, samples=4, *, include_scorch=True):
    if samples<1 or context.opponent_hand_count<0:
        raise ValueError('positive sample count and nonnegative hand count required')
    other=1-position.player;results=[]
    for index in range(samples):
        order=ranked_copies(position,context,index,include_scorch=include_scorch)
        count=context.opponent_hand_count
        if len(order)<count:return ()
        hand=tuple(replace(position.catalog[template],key=-200000000-index*1000-slot,
            owner=other,player=other,row=1,applied=()) for slot,(template,copy) in enumerate(order[:count]))
        remainder=Counter(t for t,copy in order[count:count+16])
        results.append(Hypothesis(hand,tuple(sorted(remainder.items())),
            sum(not position.supported(c) for c in hand),('balanced','unit-heavy','special-heavy')[index%3]))
    return tuple(results)
