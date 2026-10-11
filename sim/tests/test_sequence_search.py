"""Designer match-context scenarios for bounded public-action sequence search."""
from dataclasses import replace
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.sequence_search import Context,choose_sequence
from gwentsim.options import Difficulty,PROFILES


def context(**changes):
    state=Context(1,0,1,True,0,C.FactionId_Northern_Kingdom,C.FactionId_No_Mans_Land)
    return replace(state,**changes)


def test_two_card_horn_finish_and_profile_search_budget(board):
    h=horn(board);u=card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    card(board,13,5,C.CardType_Creature|C.CardType_Melee,player=1)
    position=capture(board)
    plan=choose_sequence(position,context(),Difficulty.HARD)
    assert plan.action.source==u.instanceId and len(plan.sequence)==2
    state=position
    for action in plan.sequence:state=state.apply(action)
    assert state.scores()==(16,13)
    assert plan.nodes<=PROFILES[Difficulty.HARD].search_depth*PROFILES[Difficulty.HARD].beam_width*12
    assert choose_sequence(position,context(),Difficulty.HARD)==plan


def test_cheap_attainable_two_zero_is_kept_with_other_reserve(board):
    cheap=card(board,5,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    card(board,10,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero,(C.CardEffect_None,))
    card(board,4,5,C.CardType_Creature|C.CardType_Melee,player=1)
    assert choose_sequence(capture(board),context()).action.source==cheap.instanceId


def test_secured_match_does_not_spend_spy_or_weather(board):
    unit(board,10,5)
    spy=card(board,4,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    plan=choose_sequence(capture(board),context())
    assert plan.action is None and not plan.sequence and plan.nodes==0


def test_unreachable_second_round_preserves_last_unit(board):
    unit(board,24,5,hero=True);card(board,35,5,C.CardType_Creature|C.CardType_Melee,player=1)
    horn(board)
    card(board,0,1,C.CardType_Weather,(C.CardEffect_Ranged,))
    card(board,5,1,C.CardType_Creature|C.CardType_Siege,(C.CardEffect_None,))
    plan=choose_sequence(capture(board),context(opponent_passed=False,opponent_hand_count=8))
    assert plan.action is None


def test_elimination_round_is_not_conceded_for_reserve(board):
    card(board,30,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    plan=choose_sequence(capture(board),context(own_losses=1,opponent_losses=0,opponent_passed=False,opponent_hand_count=4))
    assert plan.action is not None


def test_nilfgaard_tie_secures_match_without_spending(board):
    unit(board,10,5);card(board,10,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    plan=choose_sequence(capture(board),context(own_faction=C.FactionId_Nilfgaard))
    assert plan.action is None


def test_round_two_draw_also_finishes_match_when_leading_one_zero(board):
    unit(board,10,5);card(board,10,5,C.CardType_Creature|C.CardType_Melee,player=1)
    card(board,8,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    assert choose_sequence(capture(board),context()).action is None
    against_nilf=context(opponent_faction=C.FactionId_Nilfgaard)
    assert choose_sequence(capture(board),against_nilf).action is not None


def test_using_last_card_does_not_assume_future_turns_or_reserve(board):
    from gwentsim.sequence_search import utility,public_opponent_average
    u=card(board,5,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_None,))
    state=capture(board).apply(Action(u.instanceId,5))
    ctx=context(opponent_passed=False,opponent_hand_count=8)
    mean=public_opponent_average(state)
    assert utility(state,ctx,1,0,mean)==utility(state,ctx,1,0,mean,passing=True)


def test_final_round_ordinary_draw_has_half_match_value(board):
    from gwentsim.sequence_search import utility
    unit(board,10,5);card(board,10,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board)
    ctx=context(round_index=2,own_losses=1)
    assert utility(state,ctx,1,0,6,passing=True)==0.5
    assert utility(state,replace(ctx,opponent_faction=C.FactionId_Nilfgaard),1,0,6,passing=True)==0
    assert utility(state,replace(ctx,own_faction=C.FactionId_Nilfgaard),1,0,6,passing=True)==1


def test_first_round_draw_requires_one_future_win_not_two(board):
    from gwentsim.sequence_search import utility
    unit(board,10,5);card(board,10,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board)
    ctx=context(round_index=0,own_losses=0,opponent_losses=0,
        opponent_faction=C.FactionId_Northern_Kingdom)
    assert utility(state,ctx,1,12,6,passing=True,opponent_reserve=12)==0.5
