"""NPC experiment switches from in-game matches g152-g157 (Lab only, all off by default).

agile-dry, weather-guard, medic-hold, r1-chase and overkill-trim post-process a V8 decision;
each is checked on a constructed position, with the switch off (unchanged) and on.
"""
from dataclasses import asdict

import pytest
from test_horn_evaluation import board, card, horn, unit  # noqa: F401  (board is a fixture)
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import ResponseResult
from gwentsim.sequence_search import Context
import gwentsim.response_v8 as v8

MELEE = C.CardType_Creature | C.CardType_Melee
RANGED = C.CardType_Creature | C.CardType_Ranged
AGILE = C.CardType_Creature | C.CardType_RangedMelee
NK, NG = C.FactionId_Northern_Kingdom, C.FactionId_No_Mans_Land


def ctx(round_index=0, own_losses=0, opponent_losses=0, passed=False, opponent_hand=5):
    return Context(round_index, own_losses, opponent_losses, passed, opponent_hand, NK, NG)


def decided(monkeypatch, action, alternatives=(), value=.9, pass_value=.5):
    """V7 search stubbed to choose `action`, with (action, one-turn value) alternatives."""
    alts = tuple(dict(action=asdict(a), oneTurnValue=v) for a, v in alternatives)
    base = ResponseResult(action, value, pass_value, 4, 10, 0, False, 'supported_response', alts)
    monkeypatch.setattr(v8, 'choose_response', lambda *args: base)


def switched(monkeypatch, position, context, switches):
    monkeypatch.setattr(v8, 'VARIANT', frozenset(switches))
    monkeypatch.setattr(v8, 'NPC_SEAT', position.player)
    return v8.choose_response_v8(position, context, 2)


def frozen(board, horned=False):
    """Our hand with a Biting Frost already on the board (melee rows weathered), and optionally
    a Commander's Horn on our melee row."""
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    row_horn = horn(board) if horned else None
    state = capture(board)
    if row_horn is not None:
        state = state.apply(Action(row_horn.instanceId, 8))
    return state.apply(Action(frost.instanceId, 9))


def test_switches_are_off_by_default_and_named():
    assert not v8.VARIANT & v8.NPC_SWITCHES
    policy = 'player-mulligan+base-mulligan+agile-dry+weather-guard+medic-hold'   # "rules3" in round 8
    flags = frozenset(f for f in policy.split('+') if f)                          # as lab/core.py reads it
    assert flags & v8.NPC_SWITCHES == {'agile-dry', 'weather-guard', 'medic-hold'}


# ---- agile-dry ---------------------------------------------------------------------------------

def test_agile_dry_moves_an_agile_unit_out_of_the_frost(board, monkeypatch):
    scout = card(board, 4, 1, AGILE)
    position = frozen(board)
    wet = Action(scout.instanceId, 5)
    decided(monkeypatch, wet, [(wet, .8), (Action(scout.instanceId, 4), .8)])
    assert switched(monkeypatch, position, ctx(), ()).action == wet                  # switch off
    result = switched(monkeypatch, position, ctx(), {'agile-dry'})
    assert result.action == Action(scout.instanceId, 4) and result.reason == 'agile_dry'


def test_agile_dry_keeps_a_horned_frozen_row_that_is_strictly_better(board, monkeypatch):
    scout = card(board, 1, 1, AGILE)
    position = frozen(board, horned=True)                  # a Horn on our melee row: 1 x 2 > 1
    wet = Action(scout.instanceId, 5)
    assert v8.score_gain(position, wet) > v8.score_gain(position, Action(scout.instanceId, 4))
    decided(monkeypatch, wet)
    assert switched(monkeypatch, position, ctx(), {'agile-dry'}).action == wet


# ---- weather-guard -----------------------------------------------------------------------------

def test_weather_guard_skips_a_frost_on_an_empty_board(board, monkeypatch):
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    soldier = card(board, 5, 1, MELEE)
    position = capture(board)
    play_frost, play_unit = Action(frost.instanceId, 9), Action(soldier.instanceId, 5)
    decided(monkeypatch, play_frost, [(play_frost, .9), (play_unit, .8)])
    assert switched(monkeypatch, position, ctx(), ()).action == play_frost
    result = switched(monkeypatch, position, ctx(), {'weather-guard'})
    assert result.action == play_unit and result.reason == 'weather_guard'
    # Against a passed opponent the weather card is left to the passed-round search.
    assert switched(monkeypatch, position, ctx(passed=True), {'weather-guard'}).action == play_frost


def test_weather_guard_keeps_a_frost_that_hits_the_opponent(board, monkeypatch):
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    soldier = card(board, 5, 1, MELEE)
    card(board, 8, 5, MELEE, player=1)
    position = capture(board)
    play_frost = Action(frost.instanceId, 9)
    decided(monkeypatch, play_frost, [(play_frost, .9), (Action(soldier.instanceId, 5), .8)])
    assert switched(monkeypatch, position, ctx(), {'weather-guard'}).action == play_frost


@pytest.mark.parametrize('dry_value,expected', [(.8, 'dry'), (.7, 'wet')])
def test_weather_guard_plays_a_dry_unit_instead_of_a_frozen_one(board, monkeypatch, dry_value, expected):
    knight = card(board, 6, 1, MELEE)
    archer = card(board, 3, 1, RANGED)
    position = frozen(board)
    wet, dry = Action(knight.instanceId, 5), Action(archer.instanceId, 4)
    decided(monkeypatch, wet, [(wet, .8), (dry, dry_value)])
    result = switched(monkeypatch, position, ctx(), {'weather-guard'})
    assert result.action == (dry if expected == 'dry' else wet)


# ---- medic-hold --------------------------------------------------------------------------------

def medic_board(board, grave_unit):
    medic = card(board, 5, 1, RANGED | C.CardType_Hero, (C.CardEffect_Nurse,))
    soldier = card(board, 4, 1, MELEE)
    if grave_unit:
        card(board, 3, 2, MELEE)                             # a unit in our graveyard
    return medic, soldier


@pytest.mark.parametrize('grave_unit,context,held', [
    (False, ctx(), True),
    (True, ctx(), False),                                    # something to revive: play it
    (False, ctx(round_index=2, own_losses=1, opponent_losses=1), False),   # final round
])
def test_medic_hold(board, monkeypatch, grave_unit, context, held):
    medic, soldier = medic_board(board, grave_unit)
    position = capture(board)
    play_medic = next(a for a in position.actions() if a.source == medic.instanceId)
    play_unit = Action(soldier.instanceId, 5)
    decided(monkeypatch, play_medic, [(play_medic, .9), (play_unit, .8)])
    assert switched(monkeypatch, position, context, ()).action == play_medic
    result = switched(monkeypatch, position, context, {'medic-hold'})
    assert result.action == (play_unit if held else play_medic)


# ---- r1-chase ----------------------------------------------------------------------------------

def chase_board(board, own_cards):
    for _ in range(own_cards):
        card(board, 1, 1, MELEE)
    for power in (10, 10, 10):
        card(board, power, 5, MELEE, player=1)
    for power in range(2, 9):                                # a public catalog for the opponent's hand
        card(board, power, 2, MELEE, player=1)
    return capture(board)


def test_r1_chase_passes_a_first_round_it_cannot_win(board, monkeypatch):
    position = chase_board(board, 2)
    move = next(iter(position.actions()))
    decided(monkeypatch, move)
    assert switched(monkeypatch, position, ctx(opponent_hand=5), ()).action == move
    result = switched(monkeypatch, position, ctx(opponent_hand=5), {'r1-chase'})
    assert result.action is None and result.reason == 'pass_for_match_resources'
    assert result.revision == 'response-v8+r1-chase'


@pytest.mark.parametrize('context', [
    ctx(opponent_hand=2),                                    # not down cards: left to the search
    ctx(round_index=1, own_losses=0, opponent_losses=1, opponent_hand=5),   # not round 1
    ctx(opponent_hand=5, passed=True),
])
def test_r1_chase_only_in_round_one_with_fewer_cards(board, monkeypatch, context):
    position = chase_board(board, 2)
    assert not v8.hopeless_chase(position, context)


def test_r1_chase_keeps_a_winnable_round(board, monkeypatch):
    for power in (9, 9):
        # Our faction's cards: not in the public catalog of the opponent's possible hand.
        card(board, power, 1, MELEE).templateRef.factionIdx = NK
    card(board, 3, 5, MELEE, player=1)
    for power in (1, 1, 1):
        card(board, power, 2, MELEE, player=1)
    position = capture(board)
    assert not v8.hopeless_chase(position, ctx(opponent_hand=3))


# ---- overkill-trim -----------------------------------------------------------------------------

def test_overkill_trim_against_a_passed_opponent(board, monkeypatch):
    unit(board, 10, 5)
    card(board, 12, 5, MELEE, player=1)
    hero = card(board, 15, 1, MELEE | C.CardType_Hero)
    small = card(board, 3, 1, MELEE)
    position = capture(board)
    big = Action(hero.instanceId, 5)
    decided(monkeypatch, big)
    context = ctx(passed=True, opponent_hand=4)
    assert switched(monkeypatch, position, context, ()).action == big
    result = switched(monkeypatch, position, context, {'overkill-trim'})
    assert result.action == Action(small.instanceId, 5) and result.reason == 'overkill_trim'


@pytest.mark.parametrize('context,trimmed', [
    (ctx(opponent_hand=6), True),
    (ctx(round_index=2, own_losses=1, opponent_losses=1, opponent_hand=6), False),   # final round
])
def test_overkill_trim_while_leading(board, monkeypatch, context, trimmed):
    unit(board, 20, 5)
    card(board, 5, 5, MELEE, player=1)
    hero = card(board, 10, 1, MELEE | C.CardType_Hero)
    small = card(board, 2, 1, MELEE)
    position = capture(board)
    big, cheap = Action(hero.instanceId, 5), Action(small.instanceId, 5)
    decided(monkeypatch, big, [(big, .9), (cheap, .85)], pass_value=.8)
    result = switched(monkeypatch, position, context, {'overkill-trim'})
    assert result.action == (cheap if trimmed else big)


def test_overkill_trim_needs_a_play_valued_above_passing(board, monkeypatch):
    unit(board, 20, 5)
    card(board, 5, 5, MELEE, player=1)
    hero = card(board, 10, 1, MELEE | C.CardType_Hero)
    small = card(board, 2, 1, MELEE)
    position = capture(board)
    big, cheap = Action(hero.instanceId, 5), Action(small.instanceId, 5)
    decided(monkeypatch, big, [(big, .9), (cheap, .75)], pass_value=.8)
    assert switched(monkeypatch, position, ctx(opponent_hand=6), {'overkill-trim'}).action == big
