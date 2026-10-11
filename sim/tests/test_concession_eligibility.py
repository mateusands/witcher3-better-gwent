"""An inert unsupported modifier cannot force spending a winning match lead."""
from dataclasses import replace
import pytest
from test_horn_evaluation import board,card,unit,horn
from test_position import capture
from test_secured_round_refinement import ctx,result
from gwentsim import constants as C
from gwentsim.position import Action
from concession_eligibility import inert_mushroom_veto,refine_concession_eligibility


def scenario(board):
    unit(board,6,5)
    card(board,21,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,0,1,C.CardType_Row_Modifier,(C.CardEffect_Mushroom,))
    h=horn(board)
    card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SameTypeMorale,))
    state=capture(board)
    context=replace(ctx(),round_index=1,own_losses=0,opponent_losses=1,
        own_faction=C.FactionId_Skellige,opponent_passed=False)
    reference=replace(result(Action(h.instanceId,8)),value=.43,pass_value=.66,
        samples=6,reason='supported_response')
    return state,context,reference


def test_inert_mushroom_does_not_block_the_better_existing_concession(board):
    state,context,reference=scenario(board)
    corrected=refine_concession_eligibility(state,context,reference)
    assert corrected.action is None and corrected.value==reference.pass_value
    assert state.scores()==(6,21) and len(state.hand)==3


@pytest.mark.parametrize('effect',[C.CardEffect_Draw2,C.CardEffect_Nurse,
    C.CardEffect_SummonClones,C.CardEffect_UnsummonDummy,C.CardEffect_Morph])
def test_possible_target_acquisition_or_transform_retains_the_veto(board,effect):
    state,context,reference=scenario(board)
    card(board,4,1,C.CardType_Creature|C.CardType_Melee,(effect,))
    assert refine_concession_eligibility(capture(board),context,reference) is reference


def test_berserker_on_board_retains_the_transformation_choice(board):
    state,context,reference=scenario(board)
    card(board,4,5,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_Morph,))
    assert refine_concession_eligibility(capture(board),context,reference) is reference


def test_unknown_draws_available_leader_and_other_unsupported_effects_retain_veto(board):
    state,context,reference=scenario(board)
    assert not inert_mushroom_veto(replace(state,unknown_draws=1))
    assert not inert_mushroom_veto(replace(state,leader_ready={0:True}))
    card(board,0,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SuicideSummon,))
    assert refine_concession_eligibility(capture(board),context,reference) is reference


def test_critical_rounds_and_incomplete_search_do_not_use_concession_override(board):
    state,context,reference=scenario(board)
    for c in (replace(context,own_losses=1),replace(context,round_index=2),
              replace(context,round_index=0),replace(context,opponent_passed=True)):
        assert refine_concession_eligibility(state,c,reference) is reference
    for r in (replace(reference,budget_exhausted=True),replace(reference,pass_value=.2),
              replace(reference,pass_value=float('nan'))):
        assert refine_concession_eligibility(state,context,r) is r
