"""A separate refinement must retain V7 and disclose incomplete passed searches."""
from test_horn_evaluation import board,card,horn,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.passed_refinement import choose_refinement
from gwentsim.response_search import choose_response

MELEE=C.CardType_Creature|C.CardType_Melee


def test_open_round_preserves_reference_decision_and_audit(board):
    card(board,8,1,MELEE);card(board,4,5,MELEE,player=1)
    state=capture(board);ctx=context(opponent_passed=False,opponent_hand_count=1)
    original=choose_response(state,ctx);candidate=choose_refinement(state,ctx)
    assert candidate.action==original.action and candidate.reason==original.reason
    assert candidate.reference==original.audit() and candidate.value==original.value
    assert candidate.mode=='v7_open_round' and candidate.exact_complete is None


def test_completed_search_finds_three_move_finish_missing_from_v7(board):
    card(board,4,1,MELEE);card(board,5,1,MELEE);horn(board)
    card(board,17,5,MELEE,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    original=choose_response(state,ctx);candidate=choose_refinement(state,ctx)
    assert original.value==0 and candidate.value==1
    assert candidate.winning_witness and candidate.action is not None and candidate.fallback is None
    assert candidate.mode=='verified_terminal_witness' and state.scores()==(0,17)


def test_budget_and_unknown_draws_fall_back_without_claiming_exactness(board):
    card(board,8,1,MELEE);card(board,9,5,MELEE,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    original=choose_response(state,ctx);candidate=choose_refinement(state,ctx,max_nodes=0)
    assert candidate.action==original.action and candidate.reference==original.audit()
    assert candidate.exact_complete is False and candidate.limitations==('budget',)
    assert candidate.fallback['policy']=='response-v7'
    spy=card(board,4,1,MELEE|C.CardType_Spy,(C.CardEffect_Draw2,))
    board.playerDeckDefinitions[0].cardIndicesInDeck=[spy.templateId]
    state=capture(board);candidate=choose_refinement(state,ctx)
    assert candidate.exact_complete is False and 'unknown_draws' in candidate.limitations
    assert candidate.reference==choose_response(state,ctx).audit()


def test_nonterminal_future_round_preserves_v7_without_exhaustive_proxy_optimization(board):
    card(board,8,1,MELEE);card(board,4,5,MELEE,player=1)
    state=capture(board);ctx=context(round_index=0,own_losses=0,opponent_losses=0)
    original=choose_response(state,ctx);candidate=choose_refinement(state,ctx)
    assert candidate.mode=='v7_future_round' and candidate.exact_complete is None
    assert candidate.action==original.action and candidate.reference==original.audit()


def test_equal_terminal_outcome_keeps_the_reference_and_never_spends_more(board):
    cheap=card(board,5,1,MELEE);card(board,10,1,MELEE)
    card(board,4,5,MELEE,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    original=choose_response(state,ctx);candidate=choose_refinement(state,ctx)
    assert original.value==candidate.value and original.value>1
    assert candidate.exact_complete is None
    assert candidate.mode=='v7_terminal_upper_bound'
    assert candidate.action==original.action and candidate.fallback is None


def test_expert_four_move_win_across_all_factions(board):
    from gwentsim.options import Difficulty
    from gwentsim.passed_refinement import verify_terminal_witness
    from dataclasses import replace
    for power in (3,4,5):card(board,power,1,MELEE)
    horn(board);card(board,23,5,MELEE,player=1)
    state=capture(board)
    factions=(C.FactionId_Northern_Kingdom,C.FactionId_Nilfgaard,
        C.FactionId_No_Mans_Land,C.FactionId_Scoiatael,C.FactionId_Skellige)
    for faction in factions:
        ctx=context(round_index=2,own_losses=1,own_faction=faction)
        original=choose_response(state,ctx,Difficulty.EXPERT)
        candidate=choose_refinement(state,ctx,Difficulty.EXPERT)
        assert original.value==0
        assert candidate.value==1 and candidate.mode=='verified_terminal_witness'
        sequence=candidate.winning_witness['sequence']
        assert len(sequence)==4 and candidate.winning_witness['scores']==(24,23)
        assert candidate.exact_complete is False
        assert 'winning_witness_early_stop' in candidate.limitations
        assert state.scores()==(0,23) and len(state.hand)==4


def test_unused_unsupported_card_does_not_invalidate_deterministic_win(board):
    for power in (3,4,5):card(board,power,1,MELEE)
    horn(board);card(board,2,1,MELEE,(C.CardEffect_Morph,))
    card(board,23,5,MELEE,player=1)
    from gwentsim.options import Difficulty
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    candidate=choose_refinement(state,ctx,Difficulty.EXPERT)
    assert candidate.mode=='verified_terminal_witness' and candidate.value==1
    assert 'unsupported_hand' in candidate.limitations and candidate.exact_complete is False


def test_witness_rejects_open_round_unknown_draw_and_nonwinning_line(board):
    from gwentsim.passed_refinement import verify_terminal_witness
    from gwentsim.position import Action
    from dataclasses import replace
    u=card(board,8,1,MELEE);card(board,9,5,MELEE,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    line=(Action(u.instanceId,5),)
    assert verify_terminal_witness(state,ctx,line) is None
    assert verify_terminal_witness(state,replace(ctx,opponent_passed=False),line) is None
    state.unknown_draws=1
    assert verify_terminal_witness(state,ctx,line) is None


def test_bounded_witness_and_replanning_finish_instead_of_abandoning_combo(board):
    from gwentsim.options import Difficulty
    for power in (3,4,5):card(board,power,1,MELEE)
    horn(board);card(board,23,5,MELEE,player=1)
    state=capture(board);ctx=context(round_index=2,own_losses=1)
    # Five visited states suffice for this witness, while full enumeration has
    # many remaining permutations and Horn row alternatives.
    candidate=choose_refinement(state,ctx,Difficulty.EXPERT,max_nodes=5)
    assert candidate.winning_witness and candidate.exact_complete is False
    short=choose_refinement(state,ctx,Difficulty.EXPERT,max_nodes=4)
    assert short.winning_witness is None and short.fallback
    for _ in range(4):
        candidate=choose_refinement(state,ctx,Difficulty.EXPERT,max_nodes=5)
        assert candidate.action is not None
        state=state.apply(candidate.action)
    assert state.scores()==(24,23)
    final=choose_refinement(state,ctx,Difficulty.EXPERT)
    assert final.action is None and final.reason=='pass_for_match_resources'
