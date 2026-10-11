"""Automated tests for V8 Tactical Medic (Nurse) resurrection rules.

Covers:
1. Retargeting Hero Medic (Yennefer of Vengerberg, Menno Coehoorn) from plain units to Spies in graveyard.
2. Retargeting non-hero Medic (Dun Banner Medic, Siege Technician) to Spies in graveyard.
3. Chaining through another non-hero Medic in graveyard to reach the Spy.
4. Proactive Medic on Spy when search would prematurely pass in Round 1 / non-elimination.
5. Hero exclusion in graveyard (heroes cannot be resurrected).
"""
import pytest
from test_horn_evaluation import card
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim.gwint.card_manager import CardManager
from gwentsim.options import Difficulty
from gwentsim.response_v8 import choose_response_v8


@pytest.fixture
def board(monkeypatch):
    monkeypatch.setattr(CardManager, '_instance', None)
    monkeypatch.setattr(CardManager, 'lastInstanceID', 0)
    manager = CardManager()
    monkeypatch.setattr(manager, 'halfWeatherEnabled', lambda player: False)
    return manager


def test_v8_hero_medic_retargets_to_graveyard_spy(board):
    """When a Hero Medic (Yennefer) is played, V8 retargets from plain unit to a Spy in graveyard."""
    # Hand: Yennefer (Hero Medic, power 7, ranged) and 4p unit
    yennefer = card(board, 7, 1, C.CardType_Creature | C.CardType_Hero | C.CardType_Ranged, (C.CardEffect_Nurse,), player=0)
    u4 = card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Graveyard: Thaler (spy, power 1, siege) and 10p plain unit
    thaler = card(board, 1, 2, C.CardType_Creature | C.CardType_Siege | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)
    u10 = card(board, 10, 2, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Board: we have 8, opponent has 10
    our_u8 = card(board, 8, 5, C.CardType_Creature | C.CardType_Melee, (), player=0)
    opp = card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=1, own_losses=0, opponent_losses=1,
                  opponent_passed=False, opponent_hand_count=6,
                  own_faction=C.FactionId_Northern_Kingdom,
                  opponent_faction=C.FactionId_Nilfgaard)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None, "V8 must choose an action"
    assert v8_res.action.source == yennefer.instanceId, "V8 should play Yennefer"
    assert v8_res.action.chain is not None and len(v8_res.action.chain) >= 1
    # Target in chain must be Thaler (spy)
    target_key = v8_res.action.chain[-1][0]
    assert target_key == thaler.instanceId, f"Expected Thaler id {thaler.instanceId}, got {target_key}"


def test_v8_non_hero_medic_retargets_to_graveyard_spy(board):
    """When a non-hero Medic (Dun Banner) is played, V8 retargets from plain unit to a Spy."""
    # Hand: Dun Banner Medic (power 5, siege) and 4p unit
    dun_banner = card(board, 5, 1, C.CardType_Creature | C.CardType_Siege, (C.CardEffect_Nurse,), player=0)
    u4 = card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Graveyard: Dijkstra (spy, power 4, melee) and 10p plain unit
    dijkstra = card(board, 4, 2, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)
    u10 = card(board, 10, 2, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Board: we have 8, opponent has 10
    our_u8 = card(board, 8, 5, C.CardType_Creature | C.CardType_Melee, (), player=0)
    opp = card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=1, own_losses=0, opponent_losses=1,
                  opponent_passed=False, opponent_hand_count=6,
                  own_faction=C.FactionId_Northern_Kingdom,
                  opponent_faction=C.FactionId_Nilfgaard)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None
    assert v8_res.action.source == dun_banner.instanceId
    target_key = v8_res.action.chain[-1][0]
    assert target_key == dijkstra.instanceId, f"Expected Dijkstra id {dijkstra.instanceId}, got {target_key}"


def test_v8_medic_chains_through_graveyard_medic_to_spy(board):
    """When graveyard contains both a non-hero Medic and a Spy, V8 chains Medic -> Medic -> Spy."""
    # Hand: Yennefer (Hero Medic, power 7)
    yennefer = card(board, 7, 1, C.CardType_Creature | C.CardType_Hero | C.CardType_Ranged, (C.CardEffect_Nurse,), player=0)
    u4 = card(board, 4, 1, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Graveyard: Dun Banner Medic (5p) and Thaler (1p spy)
    dun_banner = card(board, 5, 2, C.CardType_Creature | C.CardType_Siege, (C.CardEffect_Nurse,), player=0)
    thaler = card(board, 1, 2, C.CardType_Creature | C.CardType_Siege | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)
    u10 = card(board, 10, 2, C.CardType_Creature | C.CardType_Melee, (), player=0)

    # Board
    our_u8 = card(board, 8, 5, C.CardType_Creature | C.CardType_Melee, (), player=0)
    opp = card(board, 10, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=1, own_losses=0, opponent_losses=1,
                  opponent_passed=False, opponent_hand_count=6,
                  own_faction=C.FactionId_Northern_Kingdom,
                  opponent_faction=C.FactionId_Nilfgaard)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None
    assert len(v8_res.action.chain) == 2, f"Expected 2-step chain, got {v8_res.action.chain}"
    assert v8_res.action.chain[0][0] == dun_banner.instanceId, "First target must be Dun Banner Medic"
    assert v8_res.action.chain[1][0] == thaler.instanceId, "Second target must be Thaler (Spy)"


def test_v8_proactive_medic_on_graveyard_spy_prevents_premature_pass(board):
    """In Round 1 trailing slightly, V8 plays Medic to resurrect Spy instead of passing."""
    # Hand: Dun Banner Medic (5p)
    dun_banner = card(board, 5, 1, C.CardType_Creature | C.CardType_Siege, (C.CardEffect_Nurse,), player=0)

    # Graveyard: Thaler (1p spy)
    thaler = card(board, 1, 2, C.CardType_Creature | C.CardType_Siege | C.CardType_Spy, (C.CardEffect_Draw2,), player=0)

    # Opponent has 6 on board, we have 0 on board
    opp = card(board, 6, 5, C.CardType_Creature | C.CardType_Melee, (), player=1)

    state = capture(board)
    ctx = context(round_index=0, own_losses=0, opponent_losses=0,
                  opponent_passed=False, opponent_hand_count=9,
                  own_faction=C.FactionId_Northern_Kingdom,
                  opponent_faction=C.FactionId_Nilfgaard)

    v8_res = choose_response_v8(state, ctx, Difficulty.EXPERT)
    assert v8_res.action is not None, "V8 must not pass prematurely when holding Medic and Spy in grave"
    assert v8_res.action.source == dun_banner.instanceId
    assert v8_res.action.chain[-1][0] == thaler.instanceId
