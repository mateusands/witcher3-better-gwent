"""Resource preservation and effect-aware safe spy draws on secured rounds."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import ResponseResult
from secured_round_refinement import refine_secured_round,safe_spy_draw


def ctx(faction=C.FactionId_Northern_Kingdom):
    return context(round_index=0,own_losses=0,opponent_losses=0,
        opponent_passed=True,opponent_hand_count=0,own_faction=faction)


def result(action):return ResponseResult(action,.9,.2,0,1,0,False,'supported_sequence')


@pytest.mark.parametrize('faction',[C.FactionId_Northern_Kingdom,C.FactionId_Nilfgaard,C.FactionId_Scoiatael])
def test_plain_nonhero_preserved_after_winning_round(board,faction):
    unit(board,7,5);body=card(board,10,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);reference=result(Action(body.instanceId,5))
    assert refine_secured_round(state,ctx(faction),reference).action is None
    assert state.scores()==(7,0) and body.instanceId in state.hand
    assert refine_secured_round(state,replace(ctx(faction),opponent_passed=False),reference) is reference


@pytest.mark.parametrize('faction',[C.FactionId_No_Mans_Land,C.FactionId_Skellige])
def test_nonhero_faction_carry_preserved(board,faction):
    unit(board,7,5);body=card(board,10,1,C.CardType_Creature|C.CardType_Melee);reference=result(Action(body.instanceId,5))
    assert refine_secured_round(capture(board),ctx(faction),reference) is reference


def test_horn_and_weather_kept_for_later_round(board):
    unit(board,7,5);h=horn(board)
    w=card(board,0,1,C.CardType_Weather,(C.CardEffect_Ranged,))
    state=capture(board)
    for action in (Action(h.instanceId,8),Action(w.instanceId,9)):
        corrected=refine_secured_round(state,ctx(),result(action))
        assert corrected.action is None and corrected.revision=='secured-round-v1'


def test_spy_cost_is_lead_and_real_effects_not_enemy_total(board):
    unit(board,20,5)
    card(board,12,5,C.CardType_Creature|C.CardType_Melee,player=1)
    spy=card(board,4,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    state=capture(board);state.counts={spy.templateId:2};action=Action(spy.instanceId,5)
    assert safe_spy_draw(state,ctx(),action)
    # A 4-point spy costs eight points with DoubleSpy; 20-20 is not a secured
    # first-round win for Northern Realms even though four is below enemy twelve.
    assert not safe_spy_draw(replace(state,double_spy=True),ctx(),action)
    assert not safe_spy_draw(replace(state,counts={}),ctx(),action)
    reference=result(action)
    assert refine_secured_round(state,ctx(),reference) is reference
    assert state.scores()==(20,12) and state.unknown_draws==0


def test_medic_and_decoy_resource_plans_remain_available(board):
    unit(board,20,5)
    nurse=card(board,7,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_Nurse,))
    decoy=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    state=capture(board)
    for action in (Action(nurse.instanceId,5),Action(decoy.instanceId,target=state.board[0,5][0])):
        reference=result(action)
        assert refine_secured_round(state,ctx(),reference) is reference


def test_spy_cost_uses_opponent_horn_and_weather(board):
    unit(board,20,5)
    card(board,12,5,C.CardType_Creature|C.CardType_Melee,player=1)
    spy=card(board,4,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    h=card(board,0,8,C.CardType_Row_Modifier|C.CardType_SeigeRangedMelee,(C.CardEffect_Horn,),player=1)
    state=capture(board);state.counts={spy.templateId:2}
    state.effects[1,5]=(h.instanceId,)
    action=Action(spy.instanceId,5)
    assert state.apply(action).scores()==(20,20)
    assert not safe_spy_draw(state,ctx(),action)
    frost=card(board,0,9,C.CardType_Weather,(C.CardEffect_Melee,),player=-1)
    state.cards[frost.instanceId]=capture(board).cards[frost.instanceId]
    state.effects[1,5]=(h.instanceId,frost.instanceId)
    assert state.apply(action).scores()==(20,14)
    assert safe_spy_draw(state,ctx(),action)
