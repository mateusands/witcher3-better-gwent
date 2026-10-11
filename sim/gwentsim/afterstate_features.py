"""Afterstate feature extraction for experimental learned evaluation.

Extracts a flat, normalized numerical vector representing the game state
immediately following an action (afterstate s').

Strictly respects imperfect information:
- Evaluates own future resources (remaining hand, graveyard, leader).
- Uses ONLY publicly visible opponent information (revealed counts, public graveyard,
  public leader availability, visible board). No peeking into opponent hidden cards.
"""
from typing import List, Tuple
from . import constants as C
from .position import Position, ROWS


FEATURE_NAMES: Tuple[str, ...] = (
    "score_gap",
    "own_score",
    "opp_score",
    "own_board_units",
    "opp_board_units",
    "weather_melee",
    "weather_ranged",
    "weather_siege",
    "own_hand_count",
    "opp_hand_count",
    "hand_count_diff",
    "own_hand_total_power",
    "own_hand_hero_count",
    "own_hand_spies",
    "own_hand_medics",
    "own_hand_scorch",
    "own_hand_decoys",
    "grave_spies_target",
    "grave_high_power_target",
    "own_leader_available",
    "opp_leader_available",
    "round_index",
    "own_rounds_won",
    "opp_rounds_won",
    "opp_passed",
)

NUM_FEATURES: int = len(FEATURE_NAMES)


def extract_features(position: Position, context) -> List[float]:
    """Extract 25 normalized features from (position, context)."""
    own = position.player
    opp = 1 - own
    scores = position.scores()
    own_score = float(scores[own])
    opp_score = float(scores[opp])
    gap = own_score - opp_score

    # Board units
    own_units = sum(
        1 for r in ROWS for k in position.board.get((own, r), ())
        if position.cards[k].is_type(C.CardType_Creature)
    )
    opp_units = sum(
        1 for r in ROWS for k in position.board.get((opp, r), ())
        if position.cards[k].is_type(C.CardType_Creature)
    )

    # Weather: row 5 (melee/frost), 4 (ranged/fog), 3 (siege/rain)
    # Check effects on both sides or global weather row (-1, 9)
    global_weather = position.board.get((-1, 9), ())
    w_melee = 0.0
    w_ranged = 0.0
    w_siege = 0.0
    for k in global_weather:
        c = position.cards[k]
        if c.has(C.CardEffect_Melee):
            w_melee = 1.0
        if c.has(C.CardEffect_Ranged):
            w_ranged = 1.0
        if c.has(C.CardEffect_Siege):
            w_siege = 1.0

    # Own Hand
    own_hand_cards = [position.cards[k] for k in position.hand]
    own_hand_count = float(len(own_hand_cards))
    opp_hand_count = float(context.opponent_hand_count)
    hand_diff = own_hand_count - opp_hand_count

    own_power = sum(c.power for c in own_hand_cards if c.is_type(C.CardType_Creature))
    own_heroes = sum(1 for c in own_hand_cards if c.is_type(C.CardType_Hero))
    own_spies = sum(1 for c in own_hand_cards if c.has(C.CardEffect_Draw2))
    own_medics = sum(1 for c in own_hand_cards if c.has(C.CardEffect_Nurse))
    own_scorch = sum(
        1 for c in own_hand_cards
        if c.has(C.CardEffect_Scorch) or c.has(C.CardEffect_MeleeScorch)
        or c.has(C.CardEffect_RangedScorch) or c.has(C.CardEffect_Siege_Scorch)
    )
    own_decoys = sum(1 for c in own_hand_cards if c.has(C.CardEffect_UnsummonDummy))

    # Public Graveyard: Spy targets and high power targets
    grave_spies = 0
    grave_high_units = 0
    for side in (own, opp):
        for k in position.grave.get(side, ()):
            c = position.cards.get(k)
            if not c:
                continue
            if not c.is_type(C.CardType_Hero):
                if c.has(C.CardEffect_Draw2):
                    grave_spies += 1
                if c.power >= 7:
                    grave_high_units += 1

    # Leaders
    # Own: exact usability
    own_ldr = 1.0 if getattr(context, "own_leader_available", False) else 0.0
    # Opponent: strictly public used/not-used flag
    opp_ldr = 1.0 if getattr(context, "opponent_leader_available", False) else 0.0

    # Match Progression
    rnd_idx = float(getattr(context, "round_index", 0))
    # Rounds won: opponent_losses = own rounds won; own_losses = opponent rounds won
    own_rw = float(getattr(context, "opponent_losses", 0))
    opp_rw = float(getattr(context, "own_losses", 0))
    opp_passed = 1.0 if getattr(context, "opponent_passed", False) else 0.0

    features = [
        max(-2.0, min(2.0, gap / 50.0)),            # score_gap
        min(2.0, own_score / 100.0),                # own_score
        min(2.0, opp_score / 100.0),                # opp_score
        min(2.0, own_units / 20.0),                 # own_board_units
        min(2.0, opp_units / 20.0),                 # opp_board_units
        w_melee,                                    # weather_melee
        w_ranged,                                   # weather_ranged
        w_siege,                                    # weather_siege
        min(2.0, own_hand_count / 10.0),            # own_hand_count
        min(2.0, opp_hand_count / 10.0),            # opp_hand_count
        max(-2.0, min(2.0, hand_diff / 10.0)),      # hand_count_diff
        min(3.0, own_power / 50.0),                 # own_hand_total_power
        min(2.0, own_heroes / 5.0),                 # own_hand_hero_count
        min(2.0, own_spies / 3.0),                  # own_hand_spies
        min(2.0, own_medics / 3.0),                 # own_hand_medics
        min(2.0, own_scorch / 3.0),                 # own_hand_scorch
        min(2.0, own_decoys / 3.0),                 # own_hand_decoys
        min(2.0, grave_spies / 3.0),                # grave_spies_target
        min(2.0, grave_high_units / 5.0),           # grave_high_power_target
        own_ldr,                                    # own_leader_available
        opp_ldr,                                    # opp_leader_available
        rnd_idx / 2.0,                              # round_index
        own_rw / 2.0,                               # own_rounds_won
        opp_rw / 2.0,                               # opp_rounds_won
        opp_passed,                                 # opp_passed
    ]
    assert len(features) == NUM_FEATURES
    return features
