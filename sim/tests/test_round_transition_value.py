"""Conditional winner draws and decisive-round resource arithmetic."""
from dataclasses import replace
from math import sqrt
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.sequence_search import utility,sigmoid
from round_transition_value import round_transition_utility as corrected


def position(board,winning=False):
    if winning:unit(board,10,5)
    card(board,5,5,C.CardType_Creature|C.CardType_Melee,player=1)
    draw=card(board,10,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);state.counts={draw.templateId:2}
    return state


def ctx(**changes):
    return context(round_index=1,own_losses=0,opponent_losses=1,opponent_passed=True,
        opponent_hand_count=2,own_faction=C.FactionId_Neutral,opponent_faction=C.FactionId_Neutral,**changes)


def test_losing_round_two_does_not_credit_own_northern_draw(board):
    state=position(board);base=ctx();north=replace(base,own_faction=C.FactionId_Northern_Kingdom)
    assert utility(state,north,0,20,6,passing=True)>utility(state,base,0,20,6,passing=True)
    assert corrected(state,north,0,20,6,passing=True)==corrected(state,base,0,20,6,passing=True)


def test_enemy_northern_winner_receives_conditional_draw(board):
    state=position(board);base=ctx();north=replace(base,opponent_faction=C.FactionId_Northern_Kingdom)
    assert corrected(state,north,0,20,6,passing=True)<corrected(state,base,0,20,6,passing=True)
    assert corrected(state,north,0,20,6,passing=True)==sigmoid((20-12-6)/(4+sqrt(2)*2))


def test_required_round_two_win_credits_only_own_winner_draw(board):
    state=position(board,True);base=replace(ctx(),own_losses=1,opponent_losses=0)
    own_north=replace(base,own_faction=C.FactionId_Northern_Kingdom)
    enemy_north=replace(base,opponent_faction=C.FactionId_Northern_Kingdom)
    assert corrected(state,own_north,0,20,6)==sigmoid((20+10-12)/(4+sqrt(2)*2))
    assert corrected(state,own_north,0,20,6)>corrected(state,base,0,20,6)
    assert corrected(state,enemy_north,0,20,6)==corrected(state,base,0,20,6)


def test_pending_spy_draws_exhausting_own_deck_prevent_extra_draw_credit(board):
    state=position(board,True);state.unknown_draws=2
    base=replace(ctx(),own_losses=1,opponent_losses=0)
    own_north=replace(base,own_faction=C.FactionId_Northern_Kingdom)
    assert corrected(state,own_north,0,20,6)==corrected(state,base,0,20,6)


def test_final_round_estimate_has_no_fictitious_concession_card(board):
    state=position(board);base=ctx()
    assert corrected(state,base,0,20,6)==sigmoid((20-12)/(4+sqrt(2)*2))
    assert corrected(state,base,0,20,6)<utility(state,base,0,20,6)


def test_other_rounds_and_exact_match_endpoint_remain_reference(board):
    state=position(board,True)
    for c in (replace(ctx(),round_index=0,opponent_losses=0),replace(ctx(),round_index=2,own_losses=1),replace(ctx(),own_losses=1)):
        assert corrected(state,c,0,20,6)==utility(state,c,0,20,6)
    card(board,5,5,C.CardType_Creature|C.CardType_Melee,player=1)
    tied=capture(board)
    assert corrected(tied,ctx(),0,20,6)==1



def test_nilfgaard_tie_outcomes_before_decisive_round(board):
    state=position(board,True)
    card(board,5,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board)
    trailing=replace(ctx(),own_losses=1,opponent_losses=0,own_faction=C.FactionId_Nilfgaard)
    assert corrected(state,trailing,0,20,6)==sigmoid((20-12)/(4+sqrt(2)*2))
    enemy_nilf=replace(trailing,own_faction=C.FactionId_Neutral,opponent_faction=C.FactionId_Nilfgaard)
    assert corrected(state,enemy_nilf,0,20,6)==0
    assert corrected(state,replace(ctx(),own_faction=C.FactionId_Nilfgaard),0,20,6)==1


def test_skellige_final_carry_excludes_heroes_and_accounts_for_spy_cost(board):
    unit(board,10,5)
    card(board,20,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,4,2,C.CardType_Creature|C.CardType_Melee)
    card(board,100,2,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    card(board,2,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board);skellige=replace(ctx(),own_faction=C.FactionId_Skellige)
    # Two eligible nonheroes, current body10 and gravebody4: expected carry14.
    assert corrected(state,skellige,0,20,6)==sigmoid((20+14-12)/(4+sqrt(2)*2))
    card(board,4,2,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy)
    state=capture(board)
    # Two random eligible cards out of three, spy reduces the own-side expectation.
    assert corrected(state,skellige,0,20,6)==sigmoid((20+2*(10+4-4)/3-12)/(4+sqrt(2)*2))
