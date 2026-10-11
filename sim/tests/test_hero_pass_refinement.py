"""Reproduce the scalar tie-bonus overinvestment and guard plain heroes only."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import choose_response,ResponseResult
from gwentsim.options import Difficulty
from hero_pass_refinement import refine_hero_pass


@pytest.mark.parametrize('faction',[C.FactionId_No_Mans_Land,C.FactionId_Nilfgaard,C.FactionId_Northern_Kingdom,C.FactionId_Scoiatael,C.FactionId_Skellige])
def test_passed_won_round_keeps_plain_hero_despite_scalar_rank_bonus(board,faction):
    unit(board,7,5)
    for power in (10,30,70):card(board,power,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero,(C.CardEffect_None,))
    state=capture(board);ctx=context(round_index=0,own_losses=0,opponent_losses=0,opponent_passed=True,opponent_hand_count=0,own_faction=faction)
    reference=choose_response(state,ctx,Difficulty.EXPERT)
    assert reference.action is not None and reference.value>reference.pass_value
    corrected=refine_hero_pass(state,ctx,reference)
    assert corrected.action is None and corrected.reason=='pass_for_match_resources'
    assert corrected.value==reference.pass_value and len(state.hand)==3 and state.scores()==(7,0)


def test_opponent_active_or_round_unsecured_retains_reference(board):
    hero=card(board,10,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    state=capture(board);result=ResponseResult(Action(hero.instanceId,5),.9,.2,0,1,0,False,'supported_sequence')
    ctx=context(round_index=0,own_losses=0,opponent_losses=0,opponent_passed=True,opponent_hand_count=0)
    assert refine_hero_pass(state,ctx,result) is result
    unit(board,7,5);state=capture(board)
    assert refine_hero_pass(state,replace(ctx,opponent_passed=False),result) is result


def test_hero_secondary_effect_and_nonhero_faction_carry_are_not_discarded(board):
    unit(board,7,5)
    nurse=card(board,7,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero,(C.CardEffect_Nurse,))
    spy=card(board,0,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero|C.CardType_Spy,(C.CardEffect_Draw2,))
    normal=card(board,10,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);ctx=context(round_index=0,own_losses=0,opponent_losses=0,opponent_passed=True,opponent_hand_count=0)
    for source in (nurse,normal,spy):
        result=ResponseResult(Action(source.instanceId,5),.9,.2,0,1,0,False,'supported_sequence')
        assert refine_hero_pass(state,ctx,result) is result
