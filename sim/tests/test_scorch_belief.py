"""Missing global Scorch becomes possible without altering cards or hidden state."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_horn_evaluation import board, card
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C, rng, response_search
from gwentsim.opponent_belief import hypotheses, opponent_view
from gwentsim.position import Action
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from scorch_belief import scorch_hypotheses, scorch_belief_hook


def test_actual_global_only_flag_is_excluded_by_reference_and_kept_by_candidate(board):
    scorch = card(board, 0, 1, C.CardType_Global_Effect, (C.CardEffect_Scorch,))
    state = capture(board); before = state.clone()
    ctx = context(opponent_passed=False, opponent_hand_count=1)
    assert hypotheses(state, ctx, 6) == ()
    found = scorch_hypotheses(state, ctx, 6)
    assert len(found) == 6
    assert all(h.hand[0].template == scorch.templateId and h.hand[0].types == C.CardType_Global_Effect for h in found)
    assert all(h.unsupported == 0 for h in found)
    assert state == before


def test_recorded_native_scorch_metadata_reproduces_pool_omission(board):
    from pathlib import Path
    from gwentsim.data import load_match
    from gwentsim.position import Card
    match = load_match(Path(__file__).resolve().parents[2]/'game/records/g113.json')
    t = match.templates[2]
    assert t.type_array == C.CardType_Global_Effect
    assert t.effect_flags == (C.CardEffect_Scorch,)
    state = capture(board)
    state.catalog = {2: Card(0, 2, t.power, t.type_array, t.effect_flags,
        tuple(t.summon_flags or ()), 0, 0, 1, faction=t.faction)}
    ctx = context(opponent_passed=False, opponent_hand_count=1)
    assert hypotheses(state, ctx, 6) == ()
    assert all(h.hand[0].template == 2 and h.hand[0].types == t.type_array
               for h in scorch_hypotheses(state, ctx, 6))


def test_scorch_reply_burns_strongest_nonhero_and_protects_hero(board):
    scorch = card(board, 0, 1, C.CardType_Global_Effect, (C.CardEffect_Scorch,))
    weak = card(board, 4, 5, C.CardType_Creature | C.CardType_Melee)
    strong = card(board, 10, 5, C.CardType_Creature | C.CardType_Melee)
    hero = card(board, 15, 5, C.CardType_Creature | C.CardType_Melee | C.CardType_Hero)
    state = capture(board); ctx = context(opponent_passed=False, opponent_hand_count=1)
    state.catalog = {scorch.templateId: state.catalog[scorch.templateId]}
    view = opponent_view(state, scorch_hypotheses(state, ctx, 1)[0])
    after = view.apply(Action(view.hand[0]))
    assert strong.instanceId in after.grave[0]
    assert weak.instanceId in after.board[0, 5] and hero.instanceId in after.board[0, 5]


def test_real_global_scorch_scenario_prefers_immune_unit_to_immediate_burn(board, monkeypatch):
    safe = card(board, 6, 1, C.CardType_Creature | C.CardType_Melee | C.CardType_Hero)
    risky = card(board, 15, 1, C.CardType_Creature | C.CardType_Melee)
    scorch = card(board, 0, 1, C.CardType_Global_Effect, (C.CardEffect_Scorch,))
    state = capture(board); before = state.clone()
    # Deliberately constrained designer scenario, not an assertion about an enemy deck.
    state.catalog = {scorch.templateId: state.catalog[scorch.templateId]}
    monkeypatch.setattr(response_search, 'hypotheses', scorch_hypotheses)
    from gwentsim.options import Difficulty
    result = response_search.choose_response(state,
        context(round_index=2, own_losses=1, opponent_passed=False, opponent_hand_count=1), Difficulty.EASY)
    assert result.action.source == safe.instanceId
    assert risky.instanceId in state.hand and state.cards == before.cards


def test_revealed_copy_caps_and_unrelated_globals_remain_excluded(board):
    scorch = card(board, 0, 1, C.CardType_Global_Effect, (C.CardEffect_Scorch,))
    unrelated = card(board, 0, 1, C.CardType_Global_Effect, (C.CardEffect_None,))
    state = capture(board); ctx = context(opponent_passed=False, opponent_hand_count=1)
    for index in range(3):
        state.cards[900+index] = replace(state.catalog[scorch.templateId], key=900+index, owner=1, player=1, row=2)
    assert scorch_hypotheses(state, ctx, 6) == ()


def test_no_missing_global_scorch_preserves_reference_exactly(board, monkeypatch):
    card(board, 7, 1, C.CardType_Creature | C.CardType_Melee)
    card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    state = capture(board); ctx = context(opponent_passed=False, opponent_hand_count=2)
    def forbidden(*args):
        raise AssertionError('game RNG consumed')
    monkeypatch.setattr(rng, 'math_random', forbidden)
    assert scorch_hypotheses(state, ctx, 6) == hypotheses(state, ctx, 6)
    with pytest.raises(ValueError):
        scorch_hypotheses(state, ctx, 0)


def test_hook_candidate_only_and_restores_after_exception(board, monkeypatch):
    from gwentsim.response_search import ResponseResult
    state = capture(board); ctx = context(opponent_passed=False)
    seen = []
    def search(controller, position, context):
        seen.append((controller.playerID, response_search.hypotheses))
        return ResponseResult(None, .5, .5, 0, 0, 0, False, 'pass_for_match_resources')
    monkeypatch.setattr(ResponseAIPlayerController, 'search', search)
    baseline = response_search.hypotheses
    with pytest.raises(RuntimeError):
        with scorch_belief_hook(0, []):
            a = SimpleNamespace(playerID=0, _decidedCardTransaction=None)
            b = SimpleNamespace(playerID=1, _decidedCardTransaction=None)
            ResponseAIPlayerController.search(a, state, ctx)
            ResponseAIPlayerController.search(b, state, ctx)
            raise RuntimeError('test')
    assert seen == [(0, baseline), (0, scorch_hypotheses), (1, baseline)]
    assert ResponseAIPlayerController.search is search
    assert response_search.hypotheses is baseline
