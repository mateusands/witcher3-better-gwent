"""Unit tests for afterstate feature extraction."""
import pytest
from sim.gwentsim import constants as C
from sim.gwentsim.position import Position, Card
from sim.gwentsim.sequence_search import Context
from sim.gwentsim.afterstate_features import (
    extract_features,
    FEATURE_NAMES,
    NUM_FEATURES,
)


def _make_dummy_position(player=0, hand_keys=(), board_keys=(), grave_keys=(), scores=(10, 5)):
    cards = {
        1: Card(1, 101, 10, C.CardType_Creature, (), (), 0, 0, 5),
        2: Card(2, 102, 5, C.CardType_Creature | C.CardType_Hero, (), (), 0, 0, 4),
        3: Card(3, 103, 1, C.CardType_Creature, (C.CardEffect_Draw2,), (), 1, 0, 5),  # Spy
        4: Card(4, 104, 0, C.CardType_Creature, (C.CardEffect_Nurse,), (), 0, 0, 5),  # Medic
        5: Card(5, 105, 0, 0, (C.CardEffect_Scorch,), (), 0, 0, 1),  # Scorch
        6: Card(6, 106, 0, 0, (C.CardEffect_UnsummonDummy,), (), 0, 0, 1),  # Decoy
        7: Card(7, 107, 8, C.CardType_Creature, (), (), 0, 0, 5),  # High power unit
        8: Card(8, 108, 0, C.CardType_Weather, (C.CardEffect_Melee,), (), 0, 0, 9),  # Biting Frost
    }
    board = {
        (0, 5): tuple(k for k in board_keys if k == 1),
        (0, 4): tuple(k for k in board_keys if k == 2),
        (1, 5): tuple(k for k in board_keys if k == 3),
        (-1, 9): tuple(k for k in board_keys if k == 8),
    }
    grave = {
        0: tuple(k for k in grave_keys if k in (3, 7)),
        1: (),
    }
    pos = Position(
        player=player,
        cards=cards,
        hand=tuple(hand_keys),
        board=board,
        grave=grave,
        effects={},
        counts={},
        catalog={},
        half_weather=(False, False),
        double_spy=False,
        weights={},
        leaders={0: None, 1: None},
        leader_ready={0: True, 1: True},
    )
    # Mock scores method
    pos.scores = lambda: scores
    return pos


def test_feature_vector_size_and_names():
    assert len(FEATURE_NAMES) == NUM_FEATURES
    assert NUM_FEATURES == 25


def test_extract_features_structure_and_bounds():
    pos = _make_dummy_position(
        hand_keys=[1, 2, 3, 4, 5, 6],
        board_keys=[8],
        grave_keys=[3, 7],
        scores=(20, 15),
    )
    ctx = Context(
        round_index=1,
        own_losses=0,
        opponent_losses=1,
        opponent_passed=False,
        opponent_hand_count=5,
        own_faction=C.FactionId_Northern_Kingdom,
        opponent_faction=C.FactionId_Nilfgaard,
        own_leader_available=True,
        opponent_leader_available=False,
    )
    vec = extract_features(pos, ctx)
    assert len(vec) == 25
    assert all(isinstance(v, float) for v in vec)
    # Check score gap: (20 - 15) / 50 = 0.1
    idx_gap = FEATURE_NAMES.index("score_gap")
    assert pytest.approx(vec[idx_gap], 1e-4) == 0.1
    # Weather frost active
    idx_frost = FEATURE_NAMES.index("weather_melee")
    assert vec[idx_frost] == 1.0
    # Spy target in grave: key 3 is a spy
    idx_grave_spy = FEATURE_NAMES.index("grave_spies_target")
    assert vec[idx_grave_spy] > 0.0
    # High power in grave: key 7 is 8 power
    idx_grave_high = FEATURE_NAMES.index("grave_high_power_target")
    assert vec[idx_grave_high] > 0.0
    # Leader available
    idx_own_ldr = FEATURE_NAMES.index("own_leader_available")
    assert vec[idx_own_ldr] == 1.0
    idx_opp_ldr = FEATURE_NAMES.index("opp_leader_available")
    assert vec[idx_opp_ldr] == 0.0
    # Rounds won: own_losses=0 => opp_rw=0.0; opp_losses=1 => own_rw=0.5
    idx_own_rw = FEATURE_NAMES.index("own_rounds_won")
    assert vec[idx_own_rw] == 0.5
    idx_opp_rw = FEATURE_NAMES.index("opp_rounds_won")
    assert vec[idx_opp_rw] == 0.0


def test_extract_features_is_deterministic():
    pos = _make_dummy_position(hand_keys=[1, 2], board_keys=[], grave_keys=[])
    ctx = Context(
        round_index=0,
        own_losses=0,
        opponent_losses=0,
        opponent_passed=True,
        opponent_hand_count=7,
        own_faction=C.FactionId_No_Mans_Land,
        opponent_faction=C.FactionId_Scoiatael,
    )
    vec1 = extract_features(pos, ctx)
    vec2 = extract_features(pos, ctx)
    assert vec1 == vec2
