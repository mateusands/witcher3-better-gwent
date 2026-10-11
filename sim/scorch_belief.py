"""Original isolated V7 pool correction for ordinary global-effect Scorch.

Keep existing copy caps, sensitivity priors, public seed and sample count. These
are uncalibrated scenarios, never the actual opponent hand or selected deck.
"""
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from random import Random
from time import perf_counter
from gwentsim import constants as C, response_search
from gwentsim.opponent_belief import Hypothesis, public_seed
from gwentsim.position import Action
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController


def scorch_hypotheses(position, context, samples=4, *, rng=None):
    if samples < 1:
        raise ValueError('at least one hypothesis is required')
    other = 1-position.player
    seen = Counter(c.template for c in position.cards.values() if c.owner == other)
    pool = []
    for template in sorted(position.catalog):
        card = position.catalog[template]
        if card.faction not in (C.FactionId_Neutral, context.opponent_faction):
            continue
        ordinary = any(card.is_type(flag) for flag in (
            C.CardType_Creature, C.CardType_Weather, C.CardType_Spell, C.CardType_Row_Modifier))
        global_scorch = card.is_type(C.CardType_Global_Effect) and set(card.effects) == {C.CardEffect_Scorch}
        if not (ordinary or global_scorch):
            continue
        cap = 1 if card.is_type(C.CardType_Hero) else 3
        pool.extend([template]*max(0, cap-seen[template]))
    if len(pool) < context.opponent_hand_count:
        return ()
    seed = public_seed(position, context)
    results = []
    for index in range(samples):
        random = Random(seed+index) if rng is None else rng
        remaining = list(pool)
        prior = ('balanced', 'unit-heavy', 'special-heavy')[index % 3]
        def draw():
            weights = []
            for template in remaining:
                creature = position.catalog[template].is_type(C.CardType_Creature)
                weights.append(1 if prior == 'balanced' else
                    (3 if creature else 1) if prior == 'unit-heavy' else (1 if creature else 3))
            slot = random.choices(range(len(remaining)), weights=weights, k=1)[0]
            return remaining.pop(slot)
        selected = tuple(replace(position.catalog[draw()],
            key=-200000000-index*1000-slot, owner=other, player=other, row=1, applied=())
            for slot in range(context.opponent_hand_count))
        counts = Counter(draw() for _ in range(min(16, len(remaining))))
        results.append(Hypothesis(selected, tuple(sorted(counts.items())),
            sum(not position.supported(c) for c in selected), prior))
    return tuple(results)


@contextmanager
def scorch_belief_hook(seat, audit):
    original_search = ResponseAIPlayerController.search
    original_hypotheses = response_search.hypotheses
    def search(controller, position, context):
        reference = original_search(controller, position, context)
        if controller.playerID != seat or context.opponent_passed:
            return reference
        started = perf_counter()
        response_search.hypotheses = scorch_hypotheses
        try:
            candidate = replace(original_search(controller, position, context), revision='scorch-belief-v1')
        finally:
            response_search.hypotheses = original_hypotheses
        native = getattr(controller, '_decidedCardTransaction', None)
        source = native.sourceCardInstanceRef if native else None
        intent = Action(source.instanceId, native.targetSlotID,
            native.targetCardInstanceRef.instanceId if native.targetCardInstanceRef else -1) if source else None
        pass_reasons = ('pass_for_match_resources', 'proven_no_supported_overtake')
        def effective(result):
            return intent if result.action is None and result.reason not in pass_reasons else result.action
        audit.append(dict(changed=effective(candidate) != effective(reference), round=context.round_index,
            scores=position.scores(), reference=reference.audit(), candidate=candidate.audit(),
            referenceFallback=reference.action is None and reference.reason not in pass_reasons,
            candidateFallback=candidate.action is None and candidate.reason not in pass_reasons,
            refinementSeconds=perf_counter()-started))
        return candidate
    ResponseAIPlayerController.search = search
    try:
        yield
    finally:
        ResponseAIPlayerController.search = original_search
        response_search.hypotheses = original_hypotheses
