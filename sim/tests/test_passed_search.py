"""Exhaustive passed-opponent coverage and honest incompleteness boundaries."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.passed_search import choose_passed
from gwentsim.sequence_search import choose_sequence


def test_three_moves_finish_beyond_v7_hard_depth(board):
    a=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    b=card(board,5,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    horn(board)
    card(board,17,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    result=choose_passed(state,ctx)
    assert result.complete and result.value==1 and len(result.sequence)==3
    after=state
    for action in result.sequence:after=after.apply(action)
    assert after.scores()==(18,17)
    assert choose_sequence(state,ctx).utility==0
    assert state.scores()==(0,17) and len(state.hand)==3


def test_cheap_finish_preserves_hero_and_secured_match_passes(board):
    cheap=card(board,5,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    hero=card(board,10,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero,(C.CardEffect_None,))
    card(board,4,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board);result=choose_passed(state,context())
    assert result.complete and result.action.source==cheap.instanceId
    after=state.apply(result.action)
    secured=choose_passed(after,context())
    assert secured.complete and secured.action is None and hero.instanceId in after.hand


def test_budget_never_claims_exactness_and_rejects_open_round(board):
    card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    card(board,9,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board)
    limited=choose_passed(state,context(),max_nodes=0)
    assert not limited.complete and limited.limitations==('budget',)
    assert not choose_passed(state,context(),time_limit=0).complete
    with pytest.raises(ValueError,match='passed'):
        choose_passed(state,context(opponent_passed=False))


def test_unknown_spy_draw_and_unsupported_hand_are_not_exact(board):
    spy=card(board,4,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    spare=card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    board.playerDeckDefinitions[0].cardIndicesInDeck=[spare.templateId]
    card(board,9,5,C.CardType_Creature|C.CardType_Melee,player=1)
    result=choose_passed(capture(board),context())
    assert not result.complete and 'unknown_draws' in result.limitations
    unsupported=card(board,2,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_Morph,))
    result=choose_passed(capture(board),context())
    assert not result.complete and 'unsupported_hand' in result.limitations


def test_ordinary_final_draw_and_nilfgaard_ties(board):
    unit(board,10,5);card(board,10,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    assert choose_passed(state,ctx).value==0.5
    assert choose_passed(state,replace(ctx,own_faction=C.FactionId_Nilfgaard)).value==1
    assert choose_passed(state,replace(ctx,opponent_faction=C.FactionId_Nilfgaard)).value==0


def test_ambiguous_weather_leader_is_not_silently_exact(board):
    king=card(board,0,10,0,(C.CardEffect_Pick_Rain,))
    rain=card(board,0,1,C.CardType_Weather,(C.CardEffect_Siege,))
    storm=card(board,0,1,C.CardType_Weather,(C.CardEffect_Siege,C.CardEffect_Ranged))
    card(board,9,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board)
    state.cards[king.instanceId]=replace(state.catalog[king.templateId],key=king.instanceId,row=10)
    state.leaders[0]=king.instanceId;state.leader_ready[0]=True
    state.counts={rain.templateId:1,storm.templateId:1}
    result=choose_passed(state,context(round_index=2,own_losses=1))
    assert not result.complete and 'ambiguous_weather_leader' in result.limitations
