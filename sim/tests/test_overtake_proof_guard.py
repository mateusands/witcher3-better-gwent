"""Winning leader/Medic continuations must not be canceled by incomplete bounds."""
from dataclasses import replace
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C
from gwentsim.position import Action,Card
from gwentsim.response_search import choose_response
from gwentsim.options import Difficulty
from overtake_proof_guard import proof_guard,guarded_bounds,original_bounds


def round_two():return replace(ctx(),round_index=1,opponent_losses=1)


def test_ready_leader_horn_can_win_match_even_with_empty_hand(board):
    unit(board,8,5);card(board,14,5,C.CardType_Creature|C.CardType_Melee,player=1)
    king=card(board,0,10,0,(C.CardEffect_Melee_Horn,))
    state=capture(board)
    state.cards[king.instanceId]=Card(king.instanceId,king.templateId,0,0,(C.CardEffect_Melee_Horn,),(),0,0,10)
    state=replace(state,leaders={0:king.instanceId,1:None},leader_ready={0:True,1:False})
    assert original_bounds(state)==(8,14)
    assert choose_response(state,round_two(),Difficulty.EXPERT).reason=='proven_no_supported_overtake'
    with proof_guard():result=choose_response(state,round_two(),Difficulty.EXPERT)
    assert result.action==Action(king.instanceId,8)
    assert state.apply(result.action).scores()==(16,14)
    assert state.scores()==(8,14) and state.leader_ready[0]


def test_medic_recovers_a_winning_unit_instead_of_passing(board):
    card(board,14,5,C.CardType_Creature|C.CardType_Melee,player=1)
    medic=card(board,7,1,C.CardType_Creature|C.CardType_Ranged,(C.CardEffect_Nurse,))
    body=card(board,20,2,C.CardType_Creature|C.CardType_Melee)
    state=capture(board)
    assert original_bounds(state)==(7,14)
    assert choose_response(state,round_two(),Difficulty.EXPERT).reason=='proven_no_supported_overtake'
    with proof_guard():result=choose_response(state,round_two(),Difficulty.EXPERT)
    assert result.action.source==medic.instanceId and result.action.chain==((body.instanceId,5),)
    assert state.apply(result.action).scores()==(27,14)
    assert body.instanceId in state.grave[0]


def test_decoy_can_reuse_board_medic_to_win_match(board):
    medic=card(board,7,4,C.CardType_Creature|C.CardType_Ranged,(C.CardEffect_Nurse,))
    unit(board,1,5);card(board,14,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,20,2,C.CardType_Creature|C.CardType_Melee)
    decoy=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    state=capture(board)
    assert original_bounds(state)==(8,14)
    with proof_guard():result=choose_response(state,round_two(),Difficulty.EXPERT)
    assert result.action==Action(decoy.instanceId,target=medic.instanceId)
    after=state.apply(result.action)
    assert any(after.apply(a).scores()[0]>14 for a in after.actions() if a.source==medic.instanceId)


def test_plain_impossible_chase_keeps_reference_proof(board):
    unit(board,3,5);card(board,14,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board)
    assert guarded_bounds(state)==original_bounds(state)==(3,14)
    with proof_guard():result=choose_response(state,round_two(),Difficulty.EXPERT)
    assert result.reason=='proven_no_supported_overtake'


def test_candidate_hook_restores_search_and_bounds_after_error(board,monkeypatch):
    import pytest
    from types import SimpleNamespace
    from gwentsim import sequence_search
    from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
    from gwentsim.response_search import ResponseResult
    from overtake_proof_guard import proof_guard_hook
    old=sequence_search.overtaking_bounds;seen=[]
    def search(controller,position,context):
        seen.append((controller.playerID,sequence_search.overtaking_bounds is old))
        return ResponseResult(None,.5,.5,0,0,0,False,'pass_for_match_resources')
    monkeypatch.setattr(ResponseAIPlayerController,'search',search)
    audit=[];state=capture(board)
    with pytest.raises(RuntimeError):
        with proof_guard_hook(0,audit):
            ResponseAIPlayerController.search(SimpleNamespace(playerID=0,_decidedCardTransaction=None),state,round_two())
            ResponseAIPlayerController.search(SimpleNamespace(playerID=1,_decidedCardTransaction=None),state,round_two())
            raise RuntimeError('scope test')
    assert seen==[(0,True),(0,False),(1,True)] and len(audit)==1
    assert sequence_search.overtaking_bounds is old and ResponseAIPlayerController.search is search


def test_unchanged_native_nilfgaard_medic_metadata_reproduces_wrong_pass(board):
    from pathlib import Path
    from gwentsim.data import load_match
    fixture=load_match(Path(__file__).resolve().parents[2]/'game/records/g113.json')
    medic_template=fixture.templates[230];body_template=fixture.templates[235]
    assert medic_template.power==1 and C.CardEffect_Nurse in medic_template.effect_flags
    assert body_template.power==10 and not body_template.type_array&C.CardType_Hero
    medic=card(board,medic_template.power,1,medic_template.type_array,medic_template.effect_flags)
    recovered=card(board,body_template.power,2,body_template.type_array,body_template.effect_flags)
    card(board,body_template.power,4,body_template.type_array,body_template.effect_flags,player=1)
    state=capture(board);context=replace(round_two(),own_faction=C.FactionId_Nilfgaard,opponent_faction=C.FactionId_Nilfgaard)
    assert original_bounds(state)==(1,10)
    assert choose_response(state,context,Difficulty.EXPERT).reason=='proven_no_supported_overtake'
    with proof_guard():result=choose_response(state,context,Difficulty.EXPERT)
    assert result.action.source==medic.instanceId and result.action.chain==((recovered.instanceId,4),)
    assert state.apply(result.action).scores()==(11,10)
