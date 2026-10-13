"""Shipped NPC rules (in-game matches g152-g157): the AS3 port decides as the Python reference.

agile-dry: an agile unit goes to its dry row instead of a weathered one.
weather-guard: no weather that gains nothing now while the opponent still plays, and no unit
into its own weather when a dry unit is valued as high.
medic-hold: a Medic waits while the graveyard holds nothing to revive.
overkill-trim: a won round is kept with the cheapest play the search values above passing.
Each rule is checked on a constructed position (the search stubbed to choose a given move),
Python response_v8.npc_switches against AS3 GwaiV8Policy.rules, then on the complete search.
"""
from dataclasses import asdict

import pytest
from test_horn_evaluation import board, card, horn, unit  # noqa: F401  (board is a fixture)
from test_position import capture
from test_v8_as_policy import compare
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import ResponseResult
from gwentsim.sequence_search import Context
import gwentsim.response_v8 as reference

MELEE = C.CardType_Creature | C.CardType_Melee
RANGED = C.CardType_Creature | C.CardType_Ranged
AGILE = C.CardType_Creature | C.CardType_RangedMelee
NK, NG = C.FactionId_Northern_Kingdom, C.FactionId_No_Mans_Land


def ctx(round_index=0, own_losses=0, opponent_losses=0, opponent_hand=5, passed=False):
    return Context(round_index, own_losses, opponent_losses, passed, opponent_hand, NK, NG)


def forced(monkeypatch, action, alternatives=(), value=.9, pass_value=.5):
    """The search stubbed to choose `action`, with (action, one-turn value) alternatives."""
    alts = tuple(dict(action=asdict(a), oneTurnValue=v) for a, v in alternatives)
    base = ResponseResult(action, value, pass_value, 4, 10, 0, False, 'supported_response', alts)
    monkeypatch.setattr(reference, 'choose_response', lambda *args: base)
    return base


def decide(monkeypatch, position, context, action, alternatives=(), pass_value=.5):
    """Python and AS3 on the same forced decision; returns the (identical) final action."""
    base = forced(monkeypatch, action, alternatives, pass_value=pass_value)
    return compare(position, context, base=base)


def same(result, action):
    return result['action'] == json_action(action)


def json_action(action):
    data = asdict(action)
    data['chain'] = [list(step) for step in data['chain']]
    return data


def frozen(board, horned=False):
    """A Biting Frost already on the board (melee rows weathered), optionally a Horn on our melee row."""
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    row_horn = horn(board) if horned else None
    state = capture(board)
    if row_horn is not None:
        state = state.apply(Action(row_horn.instanceId, 8))
    return state.apply(Action(frost.instanceId, 9))


# ---- agile-dry ---------------------------------------------------------------------------------

def test_agile_unit_goes_to_its_dry_row(board, monkeypatch):
    scout = card(board, 4, 1, AGILE)
    position = frozen(board)
    wet, dry = Action(scout.instanceId, 5), Action(scout.instanceId, 4)
    result = decide(monkeypatch, position, ctx(), wet, [(wet, .8), (dry, .8)])
    # With every shipped rule on, weather-guard can move the unit first: both pick the dry row.
    assert same(result, dry) and result['reason'] in ('agile_dry', 'weather_guard_dry_unit')


def test_agile_unit_keeps_a_horned_weathered_row(board, monkeypatch):
    scout = card(board, 1, 1, AGILE)
    position = frozen(board, horned=True)                  # a Horn on our melee row: 1 x 2 > 1
    wet = Action(scout.instanceId, 5)
    result = decide(monkeypatch, position, ctx(), wet)
    assert same(result, wet) and result['reason'] == 'supported_response'


def test_agile_unit_revived_by_a_medic_goes_to_its_dry_row(board, monkeypatch):
    medic = card(board, 5, 1, RANGED, (C.CardEffect_Nurse,))
    scout = card(board, 4, 2, AGILE)                       # in our graveyard
    position = frozen(board)
    wet = Action(medic.instanceId, 4, chain=((scout.instanceId, 5),))
    result = decide(monkeypatch, position, ctx(), wet)
    assert same(result, Action(medic.instanceId, 4, chain=((scout.instanceId, 4),)))
    assert result['reason'] == 'agile_dry'


# ---- weather-guard -----------------------------------------------------------------------------

@pytest.mark.parametrize('opponent_unit', [False, True])
def test_weather_that_gains_nothing_is_replaced(board, monkeypatch, opponent_unit):
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    soldier = card(board, 5, 1, MELEE)
    if opponent_unit:
        card(board, 8, 5, MELEE, player=1)                 # the frost hits the opponent: kept
    position = capture(board)
    play_frost, play_unit = Action(frost.instanceId, 9), Action(soldier.instanceId, 5)
    result = decide(monkeypatch, position, ctx(), play_frost, [(play_frost, .9), (play_unit, .8)])
    if opponent_unit:
        assert same(result, play_frost)
    else:
        assert same(result, play_unit) and result['reason'] == 'weather_guard'


@pytest.mark.parametrize('dry_value,expected', [(.8, 'dry'), (.7, 'wet')])
def test_dry_unit_instead_of_a_weathered_one(board, monkeypatch, dry_value, expected):
    knight = card(board, 6, 1, MELEE)
    archer = card(board, 3, 1, RANGED)
    position = frozen(board)
    wet, dry = Action(knight.instanceId, 5), Action(archer.instanceId, 4)
    result = decide(monkeypatch, position, ctx(), wet, [(wet, .8), (dry, dry_value)])
    assert same(result, dry if expected == 'dry' else wet)
    if expected == 'dry':
        assert result['reason'] == 'weather_guard_dry_unit'


# ---- medic-hold --------------------------------------------------------------------------------

@pytest.mark.parametrize('grave_unit,context,held', [
    (False, ctx(), True),
    (True, ctx(), False),                                    # something to revive: play it
    (False, ctx(round_index=2, own_losses=1, opponent_losses=1), False),   # final round
])
def test_medic_waits_for_something_to_revive(board, monkeypatch, grave_unit, context, held):
    medic = card(board, 5, 1, RANGED | C.CardType_Hero, (C.CardEffect_Nurse,))
    soldier = card(board, 4, 1, MELEE)
    if grave_unit:
        card(board, 3, 2, MELEE)
    position = capture(board)
    play_medic = next(a for a in position.actions() if a.source == medic.instanceId)
    play_unit = Action(soldier.instanceId, 5)
    result = decide(monkeypatch, position, context, play_medic, [(play_medic, .9), (play_unit, .8)])
    assert same(result, play_unit if held else play_medic)
    if held:
        assert result['reason'] == 'medic_hold'


# ---- overkill-trim -----------------------------------------------------------------------------

def leading(board):
    """We lead 20 to 5 with a 10 hero and a 2 unit in hand."""
    unit(board, 20, 5)
    card(board, 5, 5, MELEE, player=1)
    hero = card(board, 10, 1, MELEE | C.CardType_Hero)
    small = card(board, 2, 1, MELEE)
    return capture(board), Action(hero.instanceId, 5), Action(small.instanceId, 5)


@pytest.mark.parametrize('context,trimmed', [
    (ctx(opponent_hand=6), True),
    (ctx(round_index=2, own_losses=1, opponent_losses=1, opponent_hand=6), False),   # final round
])
def test_won_round_takes_the_cheapest_sufficient_play(board, monkeypatch, context, trimmed):
    position, big, cheap = leading(board)
    result = decide(monkeypatch, position, context, big, [(big, .9), (cheap, .85)], pass_value=.8)
    if trimmed:
        assert same(result, cheap) and result['reason'] == 'overkill_trim'
    else:
        assert same(result, big)


def test_search_best_stays_when_nothing_cheaper_beats_passing(board, monkeypatch):
    position, big, cheap = leading(board)
    result = decide(monkeypatch, position, ctx(opponent_hand=6), big, [(big, .9), (cheap, .75)], pass_value=.8)
    assert same(result, big) and result['reason'] == 'supported_response'


def test_passed_opponent_cheapest_securing_play(board, monkeypatch):
    unit(board, 10, 5)
    card(board, 12, 5, MELEE, player=1)
    hero = card(board, 15, 1, MELEE | C.CardType_Hero)
    small = card(board, 3, 1, MELEE)
    position = capture(board)
    result = decide(monkeypatch, position, ctx(opponent_hand=4, passed=True), Action(hero.instanceId, 5))
    assert same(result, Action(small.instanceId, 5)) and result['reason'] == 'overkill_trim'


# ---- complete search ---------------------------------------------------------------------------

@pytest.mark.parametrize('level', range(4))
@pytest.mark.parametrize('scenario', ['agile', 'weather', 'medic', 'overkill'])
def test_complete_search_with_the_rules(board, scenario, level):
    card(board, 6, 5, MELEE, player=1)
    if scenario == 'agile':
        card(board, 4, 1, AGILE); card(board, 5, 1, MELEE)
        position = frozen(board)
    elif scenario == 'weather':
        card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Ranged,)); card(board, 5, 1, MELEE)
        position = capture(board)
    elif scenario == 'medic':
        card(board, 5, 1, RANGED, (C.CardEffect_Nurse,)); card(board, 3, 1, MELEE)
        position = capture(board)
    else:
        unit(board, 15, 5); card(board, 10, 1, MELEE | C.CardType_Hero); card(board, 2, 1, MELEE)
        card(board, 4, 1, MELEE)
        position = capture(board)
    compare(position, ctx(opponent_hand=3), level)
