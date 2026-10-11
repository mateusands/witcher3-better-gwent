"""Original semantic public-evidence seed experiment, outside the frozen engine.

Own private hand/deck changes and arbitrary runtime instance IDs must not resample
the opponent catalog prior. Public revealed cards, locations, attached effects,
leaders and match context still update it. This stabilizes scenarios, not their
uncalibrated probabilities; it is not connected to a gameplay controller yet.
"""
from collections import Counter
from dataclasses import asdict
import hashlib,json
from random import Random
from gwentsim.opponent_belief import hypotheses


def semantic_public_seed(position,context):
    other=1-position.player
    def signature(key):
        c=position.cards[key]
        return (c.template,c.owner,c.player,c.row,
            tuple(sorted(position.cards[e].template for e in c.applied)))
    payload=dict(observer=position.player,context=asdict(context),
        revealedOpponent=sorted(Counter(c.template for c in position.cards.values() if c.owner==other).items()),
        board=[(side,row,sorted(signature(k) for k in keys)) for (side,row),keys in sorted(position.board.items())],
        graves=[(side,sorted(signature(k) for k in keys)) for side,keys in sorted(position.grave.items())],
        effects=[(side,row,sorted(signature(k) for k in keys)) for (side,row),keys in sorted(position.effects.items())],
        leaders=[(side,signature(key),bool((position.leader_ready or {}).get(side)))
            for side,key in sorted((position.leaders or {}).items()) if key in position.cards],
        halfWeather=position.half_weather,doubleSpy=position.double_spy,randomRecovery=position.random_recovery)
    return int.from_bytes(hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).digest()[:8],'big')


def semantic_hypotheses(position,context,samples=4):
    return hypotheses(position,context,samples,rng=Random(semantic_public_seed(position,context)))
