"""Symmetric pass ranking, real safe draws and public-only resource search."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from test_secured_round_refinement import ctx,result
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import choose_response
from gwentsim.options import Difficulty
from secured_resource_search import refine_secured_resources


@pytest.mark.parametrize('faction',[C.FactionId_No_Mans_Land,C.FactionId_Nilfgaard,C.FactionId_Northern_Kingdom,C.FactionId_Scoiatael,C.FactionId_Skellige])
def test_saturated_utility_preserves_heroes_without_a_move_only_bonus(board,faction):
    unit(board,7,5)
    for power in (10,30,70):
        card(board,power,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero,(C.CardEffect_None,))
    state=capture(board);context=ctx(faction)
    reference=choose_response(state,context,Difficulty.EXPERT)
    assert reference.action is not None
    corrected=refine_secured_resources(state,context,reference)
    assert corrected.action is None and corrected.value==corrected.pass_value
    assert corrected.value<=1 and state.scores()==(7,0)


def test_safe_spy_with_real_draws_remains_useful_but_empty_deck_does_not(board):
    unit(board,20,5)
    card(board,12,5,C.CardType_Creature|C.CardType_Melee,player=1)
    spy=card(board,4,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    draw=card(board,40,2,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    state=capture(board);state.counts={draw.templateId:2}
    reference=result(Action(spy.instanceId,5))
    corrected=refine_secured_resources(state,ctx(),reference)
    assert corrected.action==reference.action
    assert state.apply(corrected.action).scores()==(20,16)
    assert refine_secured_resources(replace(state,counts={}),ctx(),reference).action is None
    assert state.unknown_draws==0 and state.counts=={draw.templateId:2}


def test_unsafe_spy_cannot_give_away_an_already_won_round(board):
    unit(board,20,5)
    card(board,12,5,C.CardType_Creature|C.CardType_Melee,player=1)
    spy=card(board,9,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    draw=card(board,40,2,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    state=capture(board);state.counts={draw.templateId:2}
    reference=result(Action(spy.instanceId,5))
    assert refine_secured_resources(state,ctx(),reference).action is None


def test_decoy_recovers_a_unit_while_preserving_the_winning_score(board):
    unit(board,20,5);body=unit(board,8,5)
    d=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    state=capture(board);reference=result(Action(d.instanceId,target=body.instanceId))
    # Force saturation so the comparison must use the shared future-resource key.
    context=replace(ctx(),opponent_hand_count=0)
    state.weights[C.CardEffect_UnsummonDummy]=0
    corrected=refine_secured_resources(state,context,reference)
    assert corrected.action is not None and corrected.action.source==d.instanceId
    after=state.apply(corrected.action)
    assert after.hand and after.scores()[0]>after.scores()[1]


def test_active_opponent_does_not_use_secured_round_solver(board):
    unit(board,7,5);state=capture(board);reference=result(None)
    assert refine_secured_resources(state,replace(ctx(),opponent_passed=False),reference) is reference


@pytest.mark.parametrize('effect',[C.CardEffect_ImproveNeighbours,C.CardEffect_SameTypeMorale,C.CardEffect_Horn,C.CardEffect_Nurse])
def test_current_score_effect_without_future_gain_does_not_require_spending(board,effect):
    unit(board,20,5)
    body=card(board,7,1,C.CardType_Creature|C.CardType_Melee,(effect,))
    state=capture(board);reference=result(Action(body.instanceId,5))
    corrected=refine_secured_resources(state,ctx(),reference)
    assert corrected.action is None
    assert state.scores()==(20,0) and body.instanceId in state.hand


def test_medics_empty_grave_has_no_resource_gain_on_won_round(board):
    unit(board,20,5)
    medic=card(board,0,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_Nurse,))
    state=capture(board);reference=result(Action(medic.instanceId,5))
    assert refine_secured_resources(state,ctx(),reference).action is None



def test_scorch_can_deny_monster_carry_even_when_current_round_is_won(board):
    unit(board,50,5,hero=True)
    card(board,20,5,C.CardType_Creature|C.CardType_Melee,player=1)
    scorch=card(board,0,1,C.CardType_Spell|C.CardType_Global_Effect,(C.CardEffect_Scorch,))
    state=capture(board);context=replace(ctx(),opponent_faction=C.FactionId_No_Mans_Land)
    corrected=refine_secured_resources(state,context,result(Action(scorch.instanceId)))
    assert corrected.action is not None and corrected.action.source==scorch.instanceId
    assert state.apply(corrected.action).scores()==(50,0)
    assert state.scores()==(50,20)



def test_replanning_solver_never_expands_a_prefix_that_gives_away_the_round(board,monkeypatch):
    from gwentsim.position import Position
    from gwentsim.response_search import secured
    unit(board,8,5)
    card(board,7,5,C.CardType_Creature|C.CardType_Melee,player=1)
    d=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    card(board,2,1,C.CardType_Creature|C.CardType_Melee)
    horn(board)
    state=capture(board);context=ctx()
    actions=Position.actions
    def checked_actions(projected):
        assert secured(projected,context), 'unsafe prefix must not rely on a later replan'
        return actions(projected)
    monkeypatch.setattr(Position,'actions',checked_actions)
    corrected=refine_secured_resources(state,context,result(Action(d.instanceId,target=state.board[0,5][0])))
    assert corrected.action is None or secured(state.apply(corrected.action),context)
