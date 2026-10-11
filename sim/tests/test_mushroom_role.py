"""Observer role survives hypothetical views without changing native cards."""
from types import SimpleNamespace
import pytest
from test_horn_evaluation import board
from test_mushroom_position import berserker, mushroom, projected
from test_secured_round_refinement import ctx, result
from dataclasses import replace
from mushroom_role import role_position, mushroom_role_hook, mushroom_roles_hook
from gwentsim.opponent_belief import Hypothesis, opponent_view
from gwentsim.gwint import sequence_ai_controller as controllers
import mushroom_policy


@pytest.mark.parametrize('role,own,opponent', [('own', True, False), ('opponent', False, True), ('both', True, True)])
def test_projection_capability_is_scoped_to_actor_not_card_owner(board, role, own, opponent):
    source, target = berserker(board); m = mushroom(board)
    cls = role_position(0, role); state = cls(**projected(board).__dict__)
    assert state.supported(state.cards[source.instanceId]) == own
    hypothetical = replace(state.cards[source.instanceId], key=-2000, owner=1, player=1)
    view = opponent_view(state, Hypothesis((hypothetical,), (), 0, 'designer'))
    assert view.supported(view.cards[-2000]) == opponent
    assert state.supported(state.cards[source.instanceId]) == own
    assert view.supported(state.catalog[target.templateId])  # Native transformed public unit remains supported.
    assert state.clone().supported(state.cards[m.instanceId]) == own


def test_role_hook_restores_original_model_and_search_after_error(board, monkeypatch):
    cls = controllers.ResponseAIPlayerController; state = projected(board)
    reference = replace(result(None), reason='pass_for_match_resources')
    model = mushroom_policy.MushroomPosition; original_position = controllers.Position
    calls = []
    def search(controller, position, context):
        calls.append(type(position))
        return reference
    def begin(controller):
        return cls.search(controller, controllers.Position(**state.__dict__), ctx())
    monkeypatch.setattr(cls, 'search', search); monkeypatch.setattr(cls, 'state_begin_ChoseMove', begin)
    with pytest.raises(RuntimeError):
        with mushroom_role_hook(0, 'own', []):
            cls.state_begin_ChoseMove(SimpleNamespace(playerID=0, _decidedCardTransaction=None))
            raise RuntimeError('test')
    assert len(calls) == 2 and calls[0] is original_position and calls[1] is not original_position
    assert mushroom_policy.MushroomPosition is model and controllers.Position is original_position
    assert cls.search is search and cls.state_begin_ChoseMove is begin


def test_invalid_role_is_explicit():
    with pytest.raises(ValueError):
        role_position(0, 'unknown')


def test_two_seat_hook_keeps_peer_model_and_restores_nested_context(board, monkeypatch):
    source, target = berserker(board); state = projected(board)
    cls = controllers.ResponseAIPlayerController; original_position = controllers.Position
    reference = replace(result(None), reason='pass_for_match_resources'); calls = []
    peer = SimpleNamespace(playerID=1, _decidedCardTransaction=None)
    actor = SimpleNamespace(playerID=0, _decidedCardTransaction=None)
    def search(controller, position, context):
        view = position.clone(); view.player = 1-controller.playerID
        calls.append((controller.playerID, position.supported(position.cards[source.instanceId]),
                      view.supported(view.cards[source.instanceId])))
        return reference
    def begin(controller):
        if controller.playerID == 0:
            cls.state_begin_ChoseMove(peer)
        pos = controllers.Position(**state.__dict__); pos.player = controller.playerID
        return cls.search(controller, pos, ctx())
    monkeypatch.setattr(cls, 'search', search); monkeypatch.setattr(cls, 'state_begin_ChoseMove', begin)
    audits = {}
    with mushroom_roles_hook({0: 'own', 1: 'both'}, audits):
        cls.state_begin_ChoseMove(actor)
        assert controllers.Position is original_position
    assert calls == [(1, False, False), (1, True, True), (0, False, False), (0, True, False)]
    assert set(audits) == {0, 1} and all(len(v) == 1 for v in audits.values())
    assert cls.search is search and cls.state_begin_ChoseMove is begin
