"""Detached leader parity; JS subset execution is not Flash game acceptance."""
from dataclasses import replace, asdict
import json
import subprocess

import pytest
from test_horn_evaluation import board, card, unit
from test_position import capture
from test_v8_as_position import payload, ROOT
from gwentsim.position import Card, Action
from gwentsim import constants as C
from v8_as_test import core_javascript, script_file


def with_leader(state, effect):
    state.cards[-100] = Card(-100, 999, 0, C.CardType_King, (effect,), (), state.player, state.player, 10)
    state.leaders[state.player] = -100
    state.leader_ready[state.player] = True
    return state


def parity(state, moves=None):
    if moves is None:
        moves = state.leader_actions()
    script = core_javascript() + '\nvar state=Object.assign(new GwaiV8Position(),' + json.dumps(payload(state)) + ');'
    script += '\nvar before=JSON.stringify(state); var out={actions:state.actions(),leaders:state.leaderActions(),states:[]};'
    for move in moves:
        script += '\nout.states.push(state.apply(' + json.dumps(asdict(move)) + '));'
    script += '\nif(before!==JSON.stringify(state)) throw new Error("source mutated"); console.log(JSON.stringify(out));'
    completed = subprocess.run(['node', script_file(script)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result['leaders'] == json.loads(json.dumps([asdict(a) for a in state.leader_actions()]))
    assert result['actions'] == json.loads(json.dumps([asdict(a) for a in state.actions()]))
    for move, actual in zip(moves, result['states']):
        expected = json.loads(json.dumps(payload(state.apply(move))))
        assert actual == expected
    return result


@pytest.mark.parametrize('effect', [7,9,10,11,12,13,14,15,16,18,19,20,21,36,39,44])
def test_all_supported_leader_transitions(board, effect):
    unit(board, 6, 5)
    card(board, 4, 5, C.CardType_Creature | C.CardType_RangedMelee)
    for row, flag in [(5,1),(4,2),(3,4)]:
        card(board, 11, row, C.CardType_Creature | flag, player=1)
    card(board, 7, 2, C.CardType_Creature | 1)
    card(board, 8, 2, C.CardType_Creature | 1, player=1)
    weather = [card(board, 0, 1, C.CardType_Weather, (e,), player=1) for e in (23,24,25)]
    state = with_leader(capture(board), effect)
    state.counts = {w.templateId:1 for w in weather}
    if effect in (9,36):
        state.play_weather(state.catalog[weather[0].templateId])
    assert state.leader_actions(), effect
    parity(state)


@pytest.mark.parametrize('effect', [8,22,37,38,43,17])
def test_passive_or_unsupported_leader_is_not_searched(board, effect):
    state = with_leader(capture(board), effect)
    assert not state.leader_actions()
    parity(state)


def test_ambiguous_weather_order_is_never_guessed(board):
    a = card(board,0,1,16,(23,),player=1)
    b = card(board,0,1,16,(23,24),player=1)
    state = with_leader(capture(board),13)
    state.counts = {a.templateId:1,b.templateId:1}
    assert not state.leader_actions()
    parity(state)


def test_resurrection_accepts_noncanonical_same_template_copy(board):
    a = card(board,7,2,9)
    state = with_leader(capture(board),15)
    duplicate = replace(state.cards[a.instanceId],key=-200)
    state.cards[-200] = duplicate
    state.grave[0] += (-200,)
    assert state.leader_actions()[0].target == -200
    parity(state,[Action(-100,target=a.instanceId)])


def test_random_recovery_leader_is_explicitly_unmodeled(board):
    card(board,7,2,9)
    state = with_leader(capture(board),15)
    state.random_recovery = True
    assert not state.leader_actions()
    parity(state)
