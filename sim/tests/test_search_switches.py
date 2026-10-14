"""Lab switches for the NPC's response search (gwentsim/response_search.py, round 12 ideas).

Spec (owner, 13 October 2026): try new ideas that could make the NPC stronger, as Lab switches
on the NPC seat only (the shipped search is unchanged without them).
- beliefsN: the search imagines N opponent hands instead of 4 on Hard (less sampling luck).
- beamN: the second search ply follows the N best first moves instead of 8.
- passN: passing gets a margin of N/1000 when it competes with playing. The second ply can only
  raise a move's value (it starts from the one-ply value), never the pass value, so the search
  leans towards playing; the margin tests whether that lean costs rounds.
- cautionN: hands are combined as mean - N/100 * (mean - worst) instead of the plain mean,
  for passing and for every move alike.
- fusionN: keep only N% of what the second ply adds to a move. In the second ply the search picks
  its next move separately in each imagined hand, as if it knew the player's hand ("strategy
  fusion", the known flaw of sampling-based search: Frank and Basin 1998; Ginsberg's GIB for
  bridge), so that gain is optimistic.

Given the switches, when the search settings are read for a seat, then they change only for the
NPC seat; when the search runs, then it imagines N hands and a large pass margin makes it pass.
"""
from test_horn_evaluation import board, card  # noqa: F401
from test_position import capture
from test_sequence_search import context
from gwentsim import constants as C
from gwentsim import response_v8 as v8
from gwentsim import response_search
from gwentsim.options import Difficulty


def settings(variant, seat=1, npc_seat=1):
    v8.VARIANT, v8.NPC_SEAT = frozenset(variant), npc_seat
    return response_search.search_settings(Difficulty.HARD, seat)


def test_shipped_settings_without_switches():
    s = settings(())
    assert (s.samples, s.budget, s.beam, s.pass_margin, s.caution, s.fusion) == (4, 2048, 8, 0.0, 0.0, 1.0)


def test_each_switch_sets_its_value_for_the_npc_seat_only():
    s = settings({'beliefs6', 'beam12', 'pass20', 'caution25'})
    assert (s.samples, s.beam, s.pass_margin, s.caution) == (6, 12, 0.02, 0.25)
    other = settings({'beliefs6', 'beam12', 'pass20', 'caution25'}, seat=0)
    assert (other.samples, other.beam, other.pass_margin, other.caution) == (4, 8, 0.0, 0.0)


def test_caution_blends_the_mean_with_the_worst_hand():
    assert response_search.combine([0.2, 0.6, 1.0], 0.0) == 0.6
    assert abs(response_search.combine([0.2, 0.6, 1.0], 0.5) - 0.4) < 1e-12
    assert response_search.combine([0.2, 0.6, 1.0], 1.0) == 0.2


def test_the_search_imagines_n_hands(board, monkeypatch):
    card(board, 7, 1, C.CardType_Creature | C.CardType_Melee)
    card(board, 5, 1, C.CardType_Creature | C.CardType_Melee, player=1)
    seen = []
    real = response_search.hypotheses
    monkeypatch.setattr(response_search, 'hypotheses', lambda p, c, n: seen.append(n) or real(p, c, n))
    v8.VARIANT, v8.NPC_SEAT = frozenset({'beliefs6'}), None
    response_search.choose_response(capture(board), context(opponent_passed=False, opponent_hand_count=2))
    assert seen == [6]


def test_a_large_pass_margin_makes_the_search_pass(board):
    # Given the NPC behind on the board with cards to overtake, where the search plays
    card(board, 6, 5, C.CardType_Creature | C.CardType_Melee, player=1)
    card(board, 8, 1, C.CardType_Creature | C.CardType_Melee)
    card(board, 4, 1, C.CardType_Creature | C.CardType_Melee)
    card(board, 5, 1, C.CardType_Creature | C.CardType_Melee, player=1)
    ctx = context(opponent_passed=False, opponent_hand_count=2)
    state = capture(board)
    v8.VARIANT, v8.NPC_SEAT = frozenset(), None
    played = response_search.choose_response(state, ctx)
    v8.VARIANT = frozenset({'pass1000'})
    passed = response_search.choose_response(state, ctx)
    assert played.action is not None and passed.action is None


def test_fusion_keeps_part_of_the_second_ply_gain():
    s = settings({'fusion50'})
    assert s.fusion == 0.5
    assert response_search.second_ply(0.4, 0.6, s.fusion) == 0.5
    assert response_search.second_ply(0.4, 0.6, 1.0) == 0.6
    assert response_search.second_ply(0.4, 0.6, 0.0) == 0.4
