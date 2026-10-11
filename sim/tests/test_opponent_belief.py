"""Information-boundary and response-risk tests for the public-catalog prototype."""
from collections import Counter
from dataclasses import replace
from copy import deepcopy
from test_horn_evaluation import board,card,unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.opponent_belief import hypotheses,opponent_view
from gwentsim.response_search import choose_response
from gwentsim.position import Action
from gwentsim import rng


def test_hypotheses_obey_faction_revealed_capacity_and_do_not_touch_game_rng(board,monkeypatch):
    revealed=card(board,15,5,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero,player=1)
    revealed.templateRef.factionIdx=C.FactionId_No_Mans_Land
    available=card(board,6,1,C.CardType_Creature|C.CardType_Melee)
    available.templateRef.factionIdx=C.FactionId_No_Mans_Land
    foreign=card(board,10,1,C.CardType_Creature|C.CardType_Melee)
    foreign.templateRef.factionIdx=C.FactionId_Nilfgaard
    special=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,))
    def forbidden(*args):raise AssertionError('game random consumed')
    monkeypatch.setattr(rng,'math_random',forbidden)
    state=capture(board);before=deepcopy(state)
    ctx=context(opponent_passed=False,opponent_hand_count=3)
    first=hypotheses(state,ctx,6)
    assert len(first)==6 and hypotheses(state,ctx,6)==first and state==before
    for h in first:
        assert len(h.hand)==3
        counts=Counter(c.template for c in h.hand)+Counter(dict(h.counts))
        assert revealed.templateId not in counts and foreign.templateId not in counts
        assert all(n<=3 for n in counts.values())
        view=opponent_view(state,h)
        assert view.player==1 and view.hand!=state.hand and state==before


def test_changing_actual_hidden_hand_cannot_change_hypotheses_or_decision(board):
    own=card(board,7,1,C.CardType_Creature|C.CardType_Melee)
    other=card(board,10,1,C.CardType_Creature|C.CardType_Melee,player=1)
    ctx=context(opponent_passed=False,opponent_hand_count=1)
    before=capture(board);expected=hypotheses(before,ctx)
    board.cardListHand[1].clear()  # Same public count is supplied to the planner.
    after=capture(board)
    assert before==after and hypotheses(after,ctx)==expected
    assert choose_response(before,ctx)==choose_response(after,ctx)


def test_explicit_scorch_response_changes_preferred_unit_without_live_mutation(board,monkeypatch):
    safe=card(board,6,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    risky=card(board,15,1,C.CardType_Creature|C.CardType_Melee)
    scorch=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,),player=1)
    state=capture(board);before=deepcopy(state)
    from gwentsim.opponent_belief import Hypothesis
    h=Hypothesis((replace(state.catalog[scorch.templateId],key=-2000,owner=1,player=1),),(),0,'designer')
    monkeypatch.setattr('gwentsim.response_search.hypotheses',lambda *args:(h,))
    from gwentsim.options import Difficulty
    result=choose_response(state,context(round_index=2,own_losses=1,
        opponent_passed=False,opponent_hand_count=1),Difficulty.EASY)
    assert result.action.source==safe.instanceId and result.samples==1 and result.nodes>0
    assert state==before and risky.inList==1 and not board.getCardInstanceList(5,0)


def test_available_opponent_leader_and_unsupported_cards_are_reported(board):
    card(board,6,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_Morph,))
    ctx=context(opponent_passed=False,opponent_hand_count=1,opponent_leader_available=True)
    result=choose_response(capture(board),ctx)
    assert result.unresolved_leader and result.unsupported>=1 and result.reason=='no_supported_plan'


def test_insufficient_catalog_does_not_invent_an_opponent_hand(board):
    card(board,6,1,C.CardType_Creature|C.CardType_Melee)
    result=choose_response(capture(board),context(opponent_passed=False,opponent_hand_count=100))
    assert result.samples==0 and result.reason=='insufficient_public_catalog'


def test_response_search_stops_at_transition_budget_without_live_mutation(board):
    for i in range(20):card(board,3+i%8,1,C.CardType_Creature|C.CardType_RangedMelee)
    state=capture(board);before=deepcopy(state)
    from gwentsim.options import Difficulty
    result=choose_response(state,context(opponent_passed=False,opponent_hand_count=10),Difficulty.EASY)
    assert result.nodes<=512 and result.budget_exhausted
    assert state==before and choose_response(state,context(opponent_passed=False,
        opponent_hand_count=10),Difficulty.EASY)==result


def test_hypothetical_muster_copies_belong_to_the_simulated_opponent(board):
    source=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SummonClones,))
    source.templateRef.summonFlags=[source.templateId]
    state=capture(board)
    from gwentsim.opponent_belief import Hypothesis
    h=Hypothesis((replace(state.catalog[source.templateId],key=-2000,owner=1,player=1),),
        ((source.templateId,2),),0,'designer')
    after=opponent_view(state,h).apply(Action(-2000,5))
    assert after.scores()==(0,12)
    assert all(after.cards[k].owner==1 for k in after.board[1,5])
    assert not state.board[1,5]


def test_search_does_not_burn_scorch_on_an_empty_board(board,monkeypatch):
    useless=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,))
    productive=card(board,7,1,C.CardType_Creature|C.CardType_Melee|C.CardType_Hero)
    enemy=card(board,6,1,C.CardType_Creature|C.CardType_Melee,player=1)
    from gwentsim.opponent_belief import Hypothesis
    state=capture(board)
    h=Hypothesis((replace(state.catalog[enemy.templateId],key=-2000,owner=1,player=1),),(),0,'designer')
    monkeypatch.setattr('gwentsim.response_search.hypotheses',lambda *args:(h,))
    result=choose_response(state,context(own_losses=1,opponent_losses=1,round_index=2,
        opponent_passed=False,opponent_hand_count=1))
    assert result.action.source==productive.instanceId
    assert all(a['action']['source']!=useless.instanceId for a in result.alternatives)
