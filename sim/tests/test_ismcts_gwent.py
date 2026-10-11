"""Fair determinization without live hidden-hand/deck access."""
from dataclasses import replace
from random import Random
from test_horn_evaluation import board,card
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.ismcts_gwent import determinize
from gwentsim.opponent_belief import hypotheses


def test_fresh_samples_preserve_private_seats_and_shared_public_position(board):
    a=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    b=card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    state=capture(board);ctx=context(opponent_hand_count=2,opponent_passed=False)
    rng=Random(161)
    samples=[determinize(state,ctx,rng) for _ in range(20)]
    assert len({tuple(d.positions[1].cards[k].template for k in d.positions[1].hand) for d in samples})>1
    for sample in samples:
        own,other=sample.positions
        assert own.hand==state.hand and own.counts==state.counts
        assert len(other.hand)==2 and set(other.hand).isdisjoint(own.hand)
        assert all(other.cards[k].owner==1 for k in other.hand)
        assert own.cards==other.cards and own.board==other.board
        assert own.cards is not other.cards and own.counts is not other.counts
    assert len(state.cards)==2 and set(state.hand)=={a.instanceId,b.instanceId}
    assert determinize(state,ctx,Random(161))==determinize(state,ctx,Random(161))


def test_capture_and_determinization_ignore_real_hidden_cards_and_deck(board,monkeypatch):
    card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    getter=board.getCardInstanceList
    def guarded(row,side):
        if row==1 and side==1:raise AssertionError('real opponent hand accessed')
        return getter(row,side)
    monkeypatch.setattr(board,'getCardInstanceList',guarded)
    class Hidden:
        def __getattr__(self,name):raise AssertionError('real opponent deck accessed')
    board.playerDeckDefinitions[1]=Hidden()
    state=capture(board)
    result=determinize(state,context(opponent_hand_count=1),Random(161))
    assert len(result.positions[1].hand)==1


def test_v7_default_hypotheses_still_reproducible_and_external_rng_is_independent(board):
    card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    state=capture(board);ctx=context(opponent_hand_count=1)
    reference=hypotheses(state,ctx)
    determinize(state,ctx,Random(161))
    assert hypotheses(state,ctx)==reference


def test_search_keeps_global_random_and_all_observer_collections_isolated(board):
    import random
    import copy
    from gwentsim.ismcts_search import choose_ismcts
    card(board,8,1,C.CardType_Creature|C.CardType_Melee)
    card(board,4,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board);saved=copy.deepcopy(state);global_state=random.getstate()
    choose_ismcts(state,context(round_index=2,own_losses=1,opponent_passed=False,opponent_hand_count=1),iterations=8)
    assert state==saved and random.getstate()==global_state
