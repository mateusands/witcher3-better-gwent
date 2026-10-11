"""Automated tests for V8 tactical threshold rules (Decoy spy priority & Weather/Scorch retention).

Inspired by Forge threshold triggers and card-game domain rules:
1. Decoy priority on enemy spies: retargets and prioritizes recovering enemy spies on own board.
2. Weather retention threshold: holds row weather when enemy row has <= 1 unit and <= 6 power.
3. Scorch retention threshold: holds Scorch when enemy value killed is <= 6 power against active opponent.
"""
import pytest
from test_horn_evaluation import card, unit
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.gwint.card_manager import CardManager
from gwentsim.options import Difficulty
from gwentsim.response_search import choose_response
from gwentsim.response_v8 import choose_response_v8


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(CardManager, '_instance', None)
    monkeypatch.setattr(CardManager, 'lastInstanceID', 0)
    manager = CardManager()
    monkeypatch.setattr(manager, 'halfWeatherEnabled', lambda player: False)
    return manager


def test_v8_decoy_retargets_to_spy_on_board(board):
    """When Decoy is played and both a 10-power unit and a Spy are on board, Decoy must target the Spy."""
    decoy = card(board, 0, 1, C.CardType_SeigeRangedMelee, (C.CardEffect_UnsummonDummy,), player=0)
    u6 = card(board, 6, 1, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Dijkstra (power 4, spy) and a 10-power unit on board
    dijkstra = card(board, 4, 5, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)
    u10 = card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, (), player=0)
    opp = card(board, 18, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=False, opponent_hand_count=8,
                  own_faction=C.FactionId_Northern_Kingdom,
                  opponent_faction=C.FactionId_Nilfgaard)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None, "V8 must choose an action"
    assert v8_res.action.target == dijkstra.instanceId, f"Decoy must target the Spy (id {dijkstra.instanceId}), got {v8_res.action.target}"


def test_v8_proactive_decoy_on_enemy_spy(board):
    """When an enemy spy is on our board, V8 prioritizes Decoy over developing a plain unit."""
    decoy = card(board, 0, 1, C.CardType_SeigeRangedMelee, (C.CardEffect_UnsummonDummy,), player=0)
    u5 = card(board, 5, 1, C.CardType_Creature | C.CardType_Melee, (), player=0)
    thaler = card(board, 1, 5, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)
    opp = card(board, 8, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=False, opponent_hand_count=9)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None
    assert v8_res.action.source == decoy.instanceId, "V8 must play Decoy"
    assert v8_res.action.target == thaler.instanceId, "V8 must target Thaler"


def test_v8_holds_weather_threshold_against_active_opponent(board):
    """When enemy has only 1 weak unit (4 power) in melee row, V8 holds Biting Frost and plays a unit."""
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,), player=0)
    u6 = card(board, 6, 1, C.CardType_Creature | C.CardType_Melee, (), player=0)
    opp_weak = card(board, 4, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=False, opponent_hand_count=1)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None
    assert v8_res.action.source == u6.instanceId, "V8 must play the 6-power unit and hold Frost"
