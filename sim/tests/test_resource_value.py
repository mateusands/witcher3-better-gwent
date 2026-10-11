"""Spy cost direction, limited draws and unchanged projected rule behavior."""
from dataclasses import replace
from test_horn_evaluation import board,card
from test_position import capture
from gwentsim import constants as C
from gwentsim.resource_value import ResourcePosition
from gwentsim.position import Action
from mulligan_policy import choose_mulligan

SPY=C.CardType_Creature|C.CardType_Melee|C.CardType_Spy


def states(board):
    low=card(board,0,1,SPY,(C.CardEffect_Draw2,))
    high=card(board,7,1,SPY,(C.CardEffect_Draw2,))
    unit=card(board,5,1,C.CardType_Creature|C.CardType_Melee)
    base=capture(board)
    return low,high,unit,replace(base,hand=(low.instanceId,),counts={unit.templateId:6})


def test_lower_cost_equivalent_spy_has_more_future_value(board):
    low,high,unit,state=states(board)
    cheaper=ResourcePosition(**state.__dict__)
    costly=replace(cheaper,hand=(high.instanceId,))
    assert cheaper.reserve()==10 and costly.reserve()==3
    assert state.reserve()<replace(state,hand=(high.instanceId,)).reserve()


def test_empty_deck_and_one_draw_do_not_credit_two_new_cards(board):
    low,high,unit,state=states(board)
    corrected=ResourcePosition(**state.__dict__)
    assert replace(corrected,counts={}).reserve()==0
    assert replace(corrected,counts={unit.templateId:1}).reserve()==5
    assert replace(corrected,unknown_draws=5,draw_value=25).reserve()==30


def test_double_spy_points_increase_cost_but_heroes_remain_immune(board):
    low,high,unit,state=states(board)
    corrected=ResourcePosition(**replace(state,hand=(high.instanceId,),double_spy=True).__dict__)
    assert corrected.reserve()==0
    cards=dict(corrected.cards);cards[high.instanceId]=replace(cards[high.instanceId],types=SPY|C.CardType_Hero)
    assert replace(corrected,cards=cards).reserve()==3


def test_rule_transitions_are_identical_and_clones_retain_separate_evaluator(board):
    low,high,unit,state=states(board)
    corrected=ResourcePosition(**state.__dict__)
    normal=state.apply(Action(low.instanceId,5));after=corrected.apply(Action(low.instanceId,5))
    assert isinstance(after,ResourcePosition)
    assert {k:v for k,v in after.__dict__.items() if k!='valuation_owner'}==normal.__dict__ and after.scores()==(0,0)
    assert state.hand==(low.instanceId,) and after.unknown_draws==2


def test_mulligan_keeps_cheap_spy_instead_of_calling_printed_power_beneficial(board):
    low,high,unit,state=states(board)
    state=replace(state,counts={unit.templateId:5,high.templateId:1})
    decision=choose_mulligan(state)
    assert decision.source is None and decision.before>10


def test_two_spies_cannot_draw_the_same_single_remaining_card_twice(board):
    low,high,unit,state=states(board)
    second=card(board,0,1,SPY,(C.CardEffect_Draw2,))
    base=capture(board)
    corrected=ResourcePosition(**replace(base,hand=(low.instanceId,second.instanceId),counts={unit.templateId:1}).__dict__)
    assert corrected.reserve()==5
    assert replace(corrected,counts={unit.templateId:3}).reserve()==15


def test_opponent_hypothesis_retains_reference_reserve_and_observer_identity(board):
    low,high,unit,state=states(board)
    corrected=ResourcePosition(**state.__dict__)
    other=replace(corrected,player=1-corrected.player)
    reference=replace(state,player=other.player)
    assert other.valuation_owner==corrected.player
    assert other.reserve()==reference.reserve()
    assert replace(other.clone(),player=corrected.player).reserve()==corrected.reserve()
