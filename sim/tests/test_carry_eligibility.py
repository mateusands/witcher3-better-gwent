"""Round-clear banishment and faction retention differ in the native rules."""
from dataclasses import replace
from test_horn_evaluation import board, card, unit
from test_position import capture
from gwentsim import constants as C
from gwentsim.sequence_search import faction_carry
from carry_eligibility import eligible_carry


def test_temporary_board_body_is_not_a_skellige_round_three_resource(board):
    body = unit(board, 8, 5)
    body.BanishInsteadOfGraveyard = True
    state = capture(board)
    assert state.cards[body.instanceId].banished_on_clear
    assert faction_carry(state, 0, C.FactionId_Skellige, 2) == 8
    assert eligible_carry(state, 0, C.FactionId_Skellige, 2) == 0


def test_temporary_body_does_not_dilute_real_revival_pool(board):
    body = unit(board, 8, 5)
    body.BanishInsteadOfGraveyard = True
    card(board, 10, 2, C.CardType_Creature | C.CardType_Melee)
    state = capture(board)
    assert eligible_carry(state, 0, C.FactionId_Skellige, 2) == 10


def test_monster_retention_can_keep_the_temporary_body(board):
    body = unit(board, 8, 5)
    body.BanishInsteadOfGraveyard = True
    state = capture(board)
    assert eligible_carry(state, 0, C.FactionId_No_Mans_Land, 1) == 8
    # The native round-clear branch skips the chosen survivor before banishing.
    board.sendListToGraveyard(5, 0, body, False)
    assert body in board.getCardInstanceList(5, 0)


def test_heroes_excluded_and_spies_remain_negative_revival_power(board):
    card(board, 15, 2, C.CardType_Creature | C.CardType_Melee | C.CardType_Hero)
    card(board, 4, 2, C.CardType_Creature | C.CardType_Melee | C.CardType_Spy)
    state = capture(board)
    assert eligible_carry(state, 0, C.FactionId_Skellige, 2) == -4
    assert eligible_carry(state, 0, C.FactionId_Skellige, 1) == 0
