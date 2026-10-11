"""Known-card restoration and absence of imaginary drawn identities."""
from dataclasses import replace
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_secured_round_refinement import ctx,result
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import secured
from secured_resource_continuation import refine_secured_continuation


def spy_case(board,restoration):
    unit(board,20,5)
    card(board,12,5,C.CardType_Creature|C.CardType_Melee,player=1)
    spy=card(board,9,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    known=card(board,2,1,C.CardType_Creature|C.CardType_Melee) if restoration else None
    draw=card(board,40,2,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    state=capture(board);state.counts={draw.templateId:2}
    return state,Action(spy.instanceId,5),known


def test_unknown_draws_cannot_certify_a_losing_spy_without_known_restoration(board):
    state,spy,_=spy_case(board,False)
    assert not secured(state.apply(spy),ctx())
    assert refine_secured_continuation(state,ctx(),result(spy)).action is None
    assert state.unknown_draws==0


def test_known_card_can_restore_score_without_inventing_drawn_card_identities(board):
    state,spy,known=spy_case(board,True)
    temporary=state.apply(spy)
    assert temporary.unknown_draws==2 and not secured(temporary,ctx())
    restored=temporary.apply(Action(known.instanceId,5))
    assert secured(restored,ctx()) and restored.scores()==(22,21)
    assert set(restored.cards)==set(state.cards)
    corrected=refine_secured_continuation(state,ctx(),result(spy))
    assert corrected.action is not None
    # This planning result must start from a real held card, never a sampled draw.
    assert corrected.action.source in state.hand
    assert state.scores()==(20,12) and state.unknown_draws==0


def test_active_opponent_and_match_finishes_preserve_reference(board):
    state,spy,_=spy_case(board,True);reference=result(spy)
    for context in (replace(ctx(),opponent_passed=False),replace(ctx(),opponent_losses=1)):
        assert refine_secured_continuation(state,context,reference) is reference
