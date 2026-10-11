"""Exhaustive hypothetical endgames must distinguish proof from incomplete search."""
from dataclasses import replace
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_secured_round_refinement import ctx
from gwentsim import constants as C
from gwentsim.position import Action,Card
from gwentsim.opponent_belief import Hypothesis
from terminal_duel import solve_terminal


def final_context(**changes):
    values=dict(round_index=2,own_losses=1,opponent_losses=1,opponent_passed=False,
        own_faction=C.FactionId_Northern_Kingdom,opponent_faction=C.FactionId_Scoiatael)
    values.update(changes)
    return replace(ctx(),**values)


def hypothesis(power=None):
    hand=() if power is None else (Card(-100,900,power,C.CardType_Creature|C.CardType_Melee,
        (C.CardEffect_None,),(),1,1,1),)
    return Hypothesis(hand,(),0,'explicit-test-hypothesis')


def test_preserves_board_and_finishes_against_passed_enemy(board):
    unit(board,4,5);card(board,5,5,C.CardType_Creature|C.CardType_Melee,player=1)
    held=card(board,6,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);before=state.clone()
    result=solve_terminal(state,final_context(opponent_passed=True),hypothesis())
    assert result.complete
    assert dict(result.values)[None]==0
    assert dict(result.values)[Action(held.instanceId,5)]==1
    assert state==before


def test_does_not_choose_self_scorch_when_unit_wins_against_enemy_reply(board):
    unit(board,10,5);card(board,8,5,C.CardType_Creature|C.CardType_Melee,player=1)
    scorch=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,))
    held=card(board,5,1,C.CardType_Creature|C.CardType_Melee)
    result=solve_terminal(capture(board),final_context(),hypothesis(3))
    assert result.complete
    values=dict(result.values)
    assert values[Action(held.instanceId,5)]==1
    assert all(v==0 for a,v in result.values if a is not None and a.source==scorch.instanceId)


def test_only_hypothetical_hand_is_used(board):
    card(board,50,1,C.CardType_Creature|C.CardType_Melee,player=1)
    own=card(board,10,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board)
    assert dict(solve_terminal(state,final_context(),hypothesis()).values)[Action(own.instanceId,5)]==1
    assert dict(solve_terminal(state,final_context(),hypothesis(12)).values)[Action(own.instanceId,5)]==0


def test_tie_rules_are_exact(board):
    state=capture(board);context=final_context()
    assert dict(solve_terminal(state,context,hypothesis()).values)[None]==.5
    assert dict(solve_terminal(state,replace(context,own_faction=C.FactionId_Nilfgaard),hypothesis()).values)[None]==1
    assert dict(solve_terminal(state,replace(context,opponent_faction=C.FactionId_Nilfgaard),hypothesis()).values)[None]==0


def test_budget_exhaustion_returns_no_partial_proof(board):
    card(board,4,1,C.CardType_Creature|C.CardType_Melee)
    result=solve_terminal(capture(board),final_context(),hypothesis(3),max_nodes=1)
    assert not result.complete and result.reason=='node_limit' and result.values==()


def test_unresolved_draw_invalidates_result(board):
    spy=card(board,7,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    state=capture(board);state.counts={spy.templateId:2}
    result=solve_terminal(state,final_context(),hypothesis())
    assert not result.complete and result.reason=='unresolved_draw' and result.values==()


def test_nonfinal_round_is_not_given_a_terminal_value(board):
    result=solve_terminal(capture(board),replace(final_context(),round_index=1,own_losses=0),hypothesis())
    assert not result.complete and result.reason=='not_final_round'


def test_refinement_replaces_proven_losing_scorch_and_keeps_equal_winning_move(board,monkeypatch):
    import terminal_duel_policy as policy
    from gwentsim.response_search import ResponseResult
    unit(board,10,5);card(board,8,5,C.CardType_Creature|C.CardType_Melee,player=1)
    scorch=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,))
    held=card(board,5,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board)
    monkeypatch.setattr(policy,'hypotheses',lambda *args:(hypothesis(3),))
    scorch_action=next(a for a in state.actions() if a.source==scorch.instanceId)
    reference=ResponseResult(scorch_action,.7,0,1,10,0,False,'supported_response')
    detail={};corrected=policy.refine_terminal(state,final_context(),reference,detail)
    assert corrected.action==Action(held.instanceId,5)
    assert detail['referenceScenarioScore']==0 and detail['bestScenarioScore']==1
    assert policy.refine_terminal(state,final_context(),corrected) is corrected


def test_one_unresolved_hypothesis_preserves_reference(board,monkeypatch):
    import terminal_duel_policy as policy
    from gwentsim.response_search import ResponseResult
    own=card(board,5,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board)
    monkeypatch.setattr(policy,'hypotheses',lambda *args:(hypothesis(),replace(hypothesis(3),unsupported=1)))
    reference=ResponseResult(Action(own.instanceId,5),.2,0,2,10,0,False,'supported_response')
    detail={}
    assert policy.refine_terminal(state,final_context(),reference,detail) is reference
    assert detail['complete']==1 and detail['scenarios']==2
