"""The NPC must not lower its own score for nothing (in-game match g151).

1. A spell Scorch that leaves every opponent row untouched (it destroys nothing or only
   our own units) is skipped by the search, like a Scorch that destroys nothing.
2. Blunder Fix #6: a wasted move with no alternative becomes a pass even after a lost
   round when the hand would be empty afterwards or the search values passing higher.
Python reference and AS3 port are compared on every scenario.
"""
from dataclasses import asdict, replace
import json
import subprocess
from pathlib import Path

import pytest
from test_horn_evaluation import board, card, unit
from test_position import capture
from test_v8_as_position import payload
from test_v8_as_policy import compare
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.response_search import ResponseResult, self_harm, choose_response
from gwentsim.sequence_search import Context
import gwentsim.response_v8 as reference
from v8_as_test import core_javascript, script_file

ROOT = Path(__file__).resolve().parents[2]
MELEE = C.CardType_Creature | C.CardType_Melee
SCORCH = C.CardType_Spell | C.CardType_Global_Effect


def as3_inert(state, action):
    script = core_javascript() + '\nvar data=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += 'var before=Object.assign(new GwaiV8Position(),data.state);var after=before.apply(data.action);'
    script += 'console.log(JSON.stringify(GwaiV8Response.inert(before,after,data.action)));'
    process = subprocess.run(['node', script_file(script)], capture_output=True, text=True,
                             input=json.dumps(dict(state=payload(state), action=asdict(action))))
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize('scenario', ['own_only', 'both_sides', 'opponent_only', 'pirate'])
def test_scorch_is_inert_when_the_opponent_loses_nothing(board, scenario):
    unit(board, 2 if scenario == 'opponent_only' else 8, 5)
    card(board, 8 if scenario in ('both_sides', 'opponent_only') else 5, 5, MELEE, player=1)
    # A unit with Scorch (Clan Dimun Pirate) keeps the old rule: it adds its own power.
    flags = MELEE if scenario == 'pirate' else SCORCH
    scorch = card(board, 0 if scenario != 'pirate' else 1, 1, flags, (C.CardEffect_Scorch,))
    state = capture(board)
    if scenario == 'pirate':
        from skellige_position import SkelligePosition   # the shipped model plays the pirate
        state = SkelligePosition(**state.__dict__)
    action = Action(scorch.instanceId, 5 if scenario == 'pirate' else -1)
    expected = scenario == 'own_only'
    assert self_harm(state, state.apply(action), action) is expected
    assert as3_inert(state, action) is expected


def test_scorch_that_destroys_nothing_stays_inert(board):
    unit(board, 8, 5, hero=True)
    card(board, 5, 5, MELEE | C.CardType_Hero, player=1)
    scorch = card(board, 0, 1, SCORCH, (C.CardEffect_Scorch,))
    state = capture(board); action = Action(scorch.instanceId)
    assert self_harm(state, state.apply(action), action)
    assert as3_inert(state, action)


@pytest.mark.parametrize('level', range(4))
def test_search_never_burns_only_its_own_unit(board, level):
    unit(board, 8, 5); unit(board, 6, 4)
    card(board, 5, 5, MELEE, player=1); card(board, 4, 5, MELEE, player=1)
    scorch = card(board, 0, 1, SCORCH, (C.CardEffect_Scorch,))
    card(board, 3, 1, MELEE)
    state = capture(board); context = Context(0, 0, 0, False, 5, 3, 1)
    result = choose_response(state, context, level)
    assert result.action is None or result.action.source != scorch.instanceId
    assert all(alt['action']['source'] != scorch.instanceId for alt in result.alternatives)
    compare(state, context, level)


def frost_board(board, extra_card):
    unit(board, 3, 5)                                          # own unit frost would weaken
    card(board, 1, 5, MELEE, player=1)
    frost = card(board, 0, 1, C.CardType_Weather, (C.CardEffect_Melee,))
    if extra_card:
        card(board, 4, 1, MELEE)
    return frost


@pytest.mark.parametrize('extra_card,pass_value,expected', [
    (False, .1, 'pass'),      # hand empty afterwards: pass even after a lost round
    (True, .3, 'pass'),       # search values passing above the wasted move
    (True, .1, 'keep'),       # cards left and pass valued lower: unchanged
])
def test_wasted_move_without_alternative_after_a_lost_round(board, monkeypatch, extra_card, pass_value, expected):
    frost = frost_board(board, extra_card)
    state = capture(board)
    context = Context(1, 1, 0, False, 3, 3, 1)
    move = Action(frost.instanceId, 9)
    assert reference.wasted_move(state, move)
    base = ResponseResult(move, .2, pass_value, 4, 12, 0, False, 'supported_response')
    monkeypatch.setattr(reference, 'choose_response', lambda *args: base)
    result = compare(state, context, base=base)
    if expected == 'pass':
        assert result['action'] is None and result['reason'] == 'pass_for_match_resources'
    else:
        assert result['action']['source'] == move.source and result['action']['slot'] == move.slot


def g151_decisions(indices):
    path = ROOT / 'game/records/g151.json'
    if not path.exists():
        pytest.skip('local in-game record g151 not available')
    import record_review
    found = {}

    def on_decision(index, controller, position, context, recorded):
        if index in indices:
            # The shipped model (and the AS3 port) plays the Skellige cards.
            from skellige_position import SkelligePosition
            position = SkelligePosition(**position.__dict__)
            found[index] = (position, context, controller.search(position, context))
    record_review.rebuild(path, on_decision, stop_at=max(indices) + 1)
    return found


def test_g151_regression_no_self_scorch_and_no_self_frost():
    found = g151_decisions({110, 153})
    position, context, result = found[110]
    scorch = [k for k in position.hand if position.cards[k].has(C.CardEffect_Scorch)]
    assert scorch and result.action is not None and result.action.source not in scorch
    position, context, result = found[153]
    assert result.action is None and result.reason == 'pass_for_match_resources'
    for index in (110, 153):                         # the AS3 port decides the same
        position, context, result = found[index]
        actual = compare(position, context, 2)
        assert (actual['action'] or {}).get('source') == (result.action.source if result.action else None)
