"""Hybrid policy integration; designer scenarios are not match-strength evidence."""
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.ismcts_search import choose_ismcts


def test_hybrid_uses_exhaustive_three_move_finish_after_pass(board):
    card(board,4,1,C.CardType_Creature|C.CardType_Melee)
    card(board,5,1,C.CardType_Creature|C.CardType_Melee)
    horn(board);card(board,17,5,C.CardType_Creature|C.CardType_Melee,player=1)
    result=choose_ismcts(capture(board),context(round_index=2,own_losses=1))
    assert result.exact_complete and result.iterations==0 and result.action is not None
    assert result.value==1 and result.fallback is None


def test_hybrid_open_round_is_repeatable_and_does_not_mutate_live_board(board):
    a=card(board,8,1,C.CardType_Creature|C.CardType_Melee)
    card(board,4,5,C.CardType_Creature|C.CardType_Melee,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1,opponent_passed=False,opponent_hand_count=1)
    one=choose_ismcts(state,ctx,iterations=8);two=choose_ismcts(state,ctx,iterations=8)
    assert one.action==two.action and one.alternatives==two.alternatives
    assert one.iterations==8 and one.action.source==a.instanceId
    assert one.terminal_rollouts+one.cutoff_rollouts<=one.iterations
    assert a.inList==1 and state.hand==(a.instanceId,) and not board.getCardInstanceList(5,0)


def test_missing_own_actions_stop_root_and_preserve_explicit_v7_fallback(board):
    card(board,8,1,C.CardType_Creature|C.CardType_Melee)
    card(board,0,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SuicideSummon,))
    state=capture(board)
    result=choose_ismcts(state,context(round_index=1,own_losses=0,
        opponent_passed=False,opponent_hand_count=0),iterations=8)
    assert result.iterations==8 and result.coverage_cutoffs==result.cutoff_rollouts==8
    assert not result.alternatives and result.fallback['policy']=='response-v7'
    assert 'incomplete_action_set_cutoff' in result.limitations
    assert len(state.hand)==2
