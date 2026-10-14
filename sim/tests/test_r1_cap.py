"""Lab switch r1capN (gwentsim/response_v8.py): a ceiling on round 1 spending.

Spec (owner, 13 October 2026), from match g167: the player baited round 1 with small units and
two spies; the NPC answered every card, spent 7 cards (Ciri and Geralt while already 44-16
ahead), passed at 74-37, and lost the round to a siege row plus Foltest's siege Horn, then
reached round 3 with no card.
- r1capN: in round 1 (nobody has lost a round), while the opponent still plays, when the NPC
  already leads by N points or more and holds no more cards than the opponent, it passes instead
  of playing another card: the opponent must spend cards to take the round.
- Nothing changes in later rounds, when the opponent has passed, below the lead N, or when the
  NPC holds more cards than the opponent (then spending is affordable).
- NPC seat only, like every Lab switch.

Given a round-1 position, when the NPC leads by at least N with no card advantage, then it
passes; otherwise its move is unchanged.
"""
from dataclasses import replace

from test_horn_evaluation import board, card  # noqa: F401
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim import response_v8 as v8


def lead_position(board, lead_cards=2, hand=2):
    for _ in range(lead_cards):
        card(board, 10, 5, C.CardType_Creature | C.CardType_Melee)      # NPC board: 20 points
    for _ in range(hand):
        card(board, 6, 1, C.CardType_Creature | C.CardType_Melee)       # NPC hand
    card(board, 4, 5, C.CardType_Creature | C.CardType_Melee, player=1)  # opponent board: 4
    return capture(board)


def round_one(**changes):
    return context(round_index=0, own_losses=0, opponent_losses=0, **changes)


def decide(state, ctx, variant):
    v8.VARIANT, v8.NPC_SEAT = frozenset(variant), None
    return v8.choose_response_v8(state, ctx, 3)


def test_a_big_round_one_lead_without_card_advantage_passes(board):
    state = lead_position(board)
    ctx = round_one(opponent_passed=False, opponent_hand_count=5)
    assert decide(state, ctx, ()).action is not None              # the shipped AI keeps playing
    capped = decide(state, ctx, {'r1cap15'})
    assert capped.action is None and capped.reason == 'r1_cap'


def test_no_cap_below_the_lead_or_with_more_cards(board):
    state = lead_position(board)
    assert decide(state, round_one(opponent_passed=False, opponent_hand_count=5), {'r1cap20'}).reason != 'r1_cap'
    assert decide(state, round_one(opponent_passed=False, opponent_hand_count=1), {'r1cap15'}).reason != 'r1_cap'


def test_no_cap_after_round_one_or_against_a_passed_opponent(board):
    state = lead_position(board)
    later = context(opponent_passed=False, opponent_hand_count=5, round_index=1, opponent_losses=1)
    assert decide(state, later, {'r1cap15'}).reason != 'r1_cap'
    passed = round_one(opponent_passed=True, opponent_hand_count=5)
    assert decide(state, passed, {'r1cap15'}).reason != 'r1_cap'


def test_the_cap_reads_its_number():
    assert v8.r1_cap_lead(frozenset({'r1cap15'}), None, 1) == 15
    assert v8.r1_cap_lead(frozenset(), None, 1) is None
    assert v8.r1_cap_lead(frozenset({'r1cap15'}), 0, 1) is None             # NPC seat only
