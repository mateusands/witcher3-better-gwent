"""Blunder Fix #6: no card/leader spent without improving the score gap (in-game match g123)."""
from dataclasses import replace
from test_horn_evaluation import board,card,unit
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action,Card
from gwentsim.response_v8 import wasted_move

MELEE=C.CardType_Creature|C.CardType_Melee


def test_frost_that_only_weakens_own_row_is_wasted(board):
    unit(board,3,5)                                   # own 3-power melee unit
    card(board,1,5,MELEE,player=1);card(board,1,5,MELEE,player=1)   # opponent 1-power units
    frost=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,))
    state=capture(board)
    assert wasted_move(state,Action(frost.instanceId,9))


def test_frost_that_hurts_the_opponent_more_is_kept(board):
    unit(board,1,5);card(board,8,5,MELEE,player=1)
    frost=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,))
    assert not wasted_move(capture(board),Action(frost.instanceId,9))


def test_leader_horn_on_empty_row_is_wasted_but_useful_horn_is_kept(board):
    king=card(board,0,10,0,(C.CardEffect_Range_Horn,))
    state=capture(board)
    cards=dict(state.cards)
    cards[king.instanceId]=Card(king.instanceId,king.templateId,0,0,(C.CardEffect_Range_Horn,),(),0,0,10)
    empty=replace(state,cards=cards,leaders={0:king.instanceId,1:None},leader_ready={0:True,1:False})
    assert wasted_move(empty,Action(king.instanceId,7))
    unit(board,6,4)
    state=capture(board);cards=dict(state.cards);cards[king.instanceId]=empty.cards[king.instanceId]
    useful=replace(state,cards=cards,leaders={0:king.instanceId,1:None},leader_ready={0:True,1:False})
    assert not wasted_move(useful,Action(king.instanceId,7))


def test_spy_is_never_wasted_even_when_it_raises_the_opponent_score(board):
    spy=card(board,4,1,MELEE|C.CardType_Spy,(C.CardEffect_Draw2,))
    board.playerDeckDefinitions[0].cardIndicesInDeck=[spy.templateId]*3
    assert not wasted_move(capture(board),Action(spy.instanceId,5))
