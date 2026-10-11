"""Fair without-replacement draw identities, counts and isolated randomness."""
from dataclasses import replace
from random import Random
import random
import pytest
from test_horn_evaluation import board,card
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.sampled_draws import resolve_draws


def test_sample_own_spy_draws_then_muster_consumes_only_remaining_copies(board):
    spy=card(board,4,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    muster=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SummonClones,))
    muster.templateRef.summonFlags=[muster.templateId]
    board.playerDeckDefinitions[0].cardIndicesInDeck=[muster.templateId]*3
    original=capture(board);pending=original.apply(Action(spy.instanceId,5))
    sampled=resolve_draws(pending,Random(161))
    assert sampled.unknown_draws==0 and sampled.draw_value==0
    assert len(sampled.hand)==3 and sampled.counts[muster.templateId]==1
    after=sampled.apply(Action(muster.instanceId,5))
    assert after.scores()==(16,4) and not after.hand
    assert pending.unknown_draws==2 and pending.counts[muster.templateId]==3
    assert len(original.hand)==2 and len(board.playerDeckDefinitions[0].cardIndicesInDeck)==3


def test_reproducible_copy_weighted_samples_do_not_use_game_global_rng(board):
    a=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    b=card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    state=replace(capture(board),hand=(),counts={a.templateId:1,b.templateId:3},unknown_draws=1)
    before=random.getstate()
    first=resolve_draws(state,Random(161));again=resolve_draws(state,Random(161))
    assert first==again and random.getstate()==before
    swapped=replace(state,counts=dict(reversed(tuple(state.counts.items()))))
    assert resolve_draws(swapped,Random(161))==first
    # Deterministic broad sampler check: a three-copy template must be sampled
    # much more often than a one-copy template; no match-strength claim.
    picked=[resolve_draws(state,Random(seed)) for seed in range(400)]
    high=sum(s.cards[s.hand[0]].template==b.templateId for s in picked)
    assert 260<high<340


def test_empty_deck_zero_draws_and_invalid_counts(board):
    state=replace(capture(board),counts={})
    assert resolve_draws(state,Random(0))==state
    with pytest.raises(ValueError,match='exceed'):
        resolve_draws(replace(state,unknown_draws=1),Random(0))
    with pytest.raises(ValueError,match='negative'):
        resolve_draws(replace(state,counts={1:-1}),Random(0))
    with pytest.raises(ValueError,match='catalog'):
        resolve_draws(replace(state,counts={999:1}),Random(0))
