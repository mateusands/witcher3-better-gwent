"""NPC spy play experiments (Lab switches, NPC only, off by default).

Spec (owner, 13 October 2026): a spy is worth playing early, because its two cards bring the
synergies, heroes and good cards; the NPC rarely played its spies (g159: Stefan, Shilard and
Vattier never played).
- spy-first: outside the final round and while the opponent still plays, when the search picks a
  non-spy card and a spy is in hand, the NPC plays its cheapest spy (least power given away) first.
- draw15 / draw20: the NPC values cards still to be drawn (spies) 1.5x / 2x (tuning draw_weight).
"""
from gwentsim import constants as C
from gwentsim.position import Action
import gwentsim.response_v8 as v8
from test_horn_evaluation import board, card  # noqa: F401  (board is a fixture)
from test_npc_switches import ctx, decided, switched
from test_position import capture

MELEE = C.CardType_Creature | C.CardType_Melee
SPY = C.CardType_Creature | C.CardType_Melee | C.CardType_Spy


def hand(board):
    """Our hand: a 6-power unit and two spies (5 and 9 power)."""
    knight = card(board, 6, 1, MELEE)
    small = card(board, 5, 1, SPY, (C.CardEffect_Draw2,))
    big = card(board, 9, 1, SPY, (C.CardEffect_Draw2,))
    return capture(board), knight, small, big


def test_spy_first_plays_the_cheapest_spy_early(board, monkeypatch):
    position, knight, small, big = hand(board)
    play = Action(knight.instanceId, 5)
    decided(monkeypatch, play, [(play, .8)])
    # Given the search picks the unit in round 1: off by default, the unit is played
    assert switched(monkeypatch, position, ctx(), ()).action == play
    # When spy-first is on, then the 5-power spy goes first
    result = switched(monkeypatch, position, ctx(), {'spy-first'})
    assert result.action.source == small.instanceId and result.reason == 'spy_first'
    # Also in round 2 when it is not the last round
    assert switched(monkeypatch, position, ctx(round_index=1), {'spy-first'}).action.source == small.instanceId


def test_spy_first_leaves_final_rounds_and_passed_opponents_alone(board, monkeypatch):
    position, knight, small, big = hand(board)
    play = Action(knight.instanceId, 5)
    decided(monkeypatch, play, [(play, .8)])
    assert switched(monkeypatch, position, ctx(round_index=2), {'spy-first'}).action == play
    assert switched(monkeypatch, position, ctx(round_index=1, own_losses=1, opponent_losses=1),
                    {'spy-first'}).action == play
    assert switched(monkeypatch, position, ctx(passed=True), {'spy-first'}).action == play


def test_draw_weight_switches_for_the_npc_seat_only(monkeypatch):
    monkeypatch.setattr(v8, 'NPC_SEAT', 1)
    for switch, weight in (('draw15', 1.5), ('draw20', 2.0)):
        monkeypatch.setattr(v8, 'VARIANT', frozenset({switch}))
        assert v8.weight_switches(1) == {'draw_weight': weight}
        assert v8.weight_switches(0) == {}
    monkeypatch.setattr(v8, 'VARIANT', frozenset({'reserve35'}))
    assert v8.weight_switches(1) == {'reserve_weight': 0.35}
