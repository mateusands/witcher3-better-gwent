"""Equivalent public knowledge must yield identical provisional enemy scenarios."""
from dataclasses import replace
from copy import deepcopy
from test_horn_evaluation import board,card
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C,rng
from gwentsim.opponent_belief import public_seed
from public_belief_prior import semantic_public_seed,semantic_hypotheses


def snapshot(board):
    own=card(board,7,1,C.CardType_Creature|C.CardType_Melee)
    other=card(board,5,5,C.CardType_Creature|C.CardType_Melee,player=1)
    spare=card(board,9,1,C.CardType_Creature|C.CardType_Ranged)
    special=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,))
    return capture(board),own,other,spare


def test_private_owned_card_and_deck_changes_do_not_resample_enemy(board):
    state,own,other,spare=snapshot(board);ctx=context(opponent_passed=False,opponent_hand_count=2)
    changed=state.clone();changed.hand=tuple(k for k in changed.hand if k!=own.instanceId)
    changed.cards.pop(own.instanceId);changed.counts={spare.templateId:9}
    assert public_seed(state,ctx)!=public_seed(changed,ctx)
    assert semantic_public_seed(state,ctx)==semantic_public_seed(changed,ctx)
    assert semantic_hypotheses(state,ctx,6)==semantic_hypotheses(changed,ctx,6)


def test_runtime_instance_renaming_preserves_public_scenarios(board):
    state,own,other,spare=snapshot(board);ctx=context(opponent_passed=False,opponent_hand_count=2)
    shifted=state.clone();offset=10000
    shifted.cards={k+offset:replace(c,key=c.key+offset,applied=tuple(x+offset for x in c.applied)) for k,c in state.cards.items()}
    shifted.hand=tuple(k+offset for k in state.hand)
    shifted.board={place:tuple(k+offset for k in keys) for place,keys in state.board.items()}
    shifted.grave={side:tuple(k+offset for k in keys) for side,keys in state.grave.items()}
    shifted.effects={place:tuple(k+offset for k in keys) for place,keys in state.effects.items()}
    shifted.leaders={side:key+offset if key is not None else None for side,key in (state.leaders or {}).items()}
    assert public_seed(state,ctx)!=public_seed(shifted,ctx)
    assert semantic_public_seed(state,ctx)==semantic_public_seed(shifted,ctx)
    assert semantic_hypotheses(state,ctx,6)==semantic_hypotheses(shifted,ctx,6)


def test_public_evidence_updates_seed_and_game_randomness_remains_untouched(board,monkeypatch):
    state,own,other,spare=snapshot(board);ctx=context(opponent_passed=False,opponent_hand_count=2)
    before=deepcopy(state)
    def forbidden(*args):raise AssertionError('game RNG consumed')
    monkeypatch.setattr(rng,'math_random',forbidden)
    assert semantic_hypotheses(state,ctx,6)==semantic_hypotheses(state,ctx,6)
    assert state==before
    assert semantic_public_seed(state,ctx)!=semantic_public_seed(state,replace(ctx,opponent_hand_count=1))
    changed=state.clone();changed.cards[other.instanceId]=replace(changed.cards[other.instanceId],template=spare.templateId)
    assert semantic_public_seed(state,ctx)!=semantic_public_seed(changed,ctx)


def test_response_planning_is_invariant_under_owned_hand_instance_renaming(board,monkeypatch):
    from gwentsim.response_search import choose_response
    state,own,other,spare=snapshot(board)
    ctx=context(opponent_passed=False,opponent_hand_count=2)
    shifted=state.clone();offset=10000
    for key in state.hand:
        shifted.cards[key+offset]=replace(shifted.cards.pop(key),key=key+offset)
    shifted.hand=tuple(key+offset for key in state.hand)
    monkeypatch.setattr('gwentsim.response_search.hypotheses',semantic_hypotheses)
    first=choose_response(state,ctx);second=choose_response(shifted,ctx)
    assert first.value==second.value and first.pass_value==second.pass_value
    assert first.action is not None and second.action is not None
    assert second.action.source==first.action.source+offset
    assert (first.action.slot,first.action.target)==(second.action.slot,second.action.target)
