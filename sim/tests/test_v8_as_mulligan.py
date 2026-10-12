"""The in-game NPC opening exchange (GwaiV8Mulligan.as) makes the Lab's evaluated choices.

Opening hands come from the Lab's NPC-vs-player matchups in every NPC deck mode; each hand
and the hand after the first exchange are compared with sim/mulligan_policy.py: the chosen
card, and the hand potential before and after every possible exchange.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
sys.path.insert(0, str(ROOT / 'tools'))

from gwentsim.gwint.gwint_game_flow_controller import GwintGameFlowController
from gwentsim.gwint.match import run_match
from gwentsim.position import Position
from gwentsim.rng import SeededRandom
from mulligan_policy import choose_mulligan, exchanged, initial_hand_potential
from test_v8_as_position import payload
from v8_as_test import core_javascript, script_file


class Dealt(Exception):
    pass


def opening_positions(cases):
    from evaluate_pool import player_seats, setup
    match = setup()['match']
    out = []
    original = GwintGameFlowController.state_begin_Mulligan

    def begin(flow):
        original(flow)
        cm = flow.cardManager
        for _ in range(2):
            state = Position.from_manager(cm, seat)
            out.append(state)
            decision = choose_mulligan(state)
            if decision.source is None:
                break
            cm.mulliganCard(cm.getCardInstance(decision.source))
        raise Dealt()
    GwintGameFlowController.state_begin_Mulligan = begin
    try:
        for pair, seed, swap, mode in cases:
            seats, seat = player_seats(pair, swap, mode, 3)
            try:
                run_match(match.templates.values(), [seats[0].for_player(0), seats[1].for_player(1)],
                          match.card_values, SeededRandom(seed), coin_toss_choice=lambda: True,
                          seat_policies=('response-v8', 'response-v8'), candidate_profile=3)
            except Dealt:
                pass
    finally:
        GwintGameFlowController.state_begin_Mulligan = original
    return out


def run_js(states):
    script = core_javascript() + '\nvar inputs=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += '''
console.log(JSON.stringify(inputs.map(data => {
  var state = Object.assign(new GwaiV8Position(), data);
  var before = JSON.stringify(state);
  var templates = Object.keys(state.counts).filter(t => state.counts[t] > 0).map(Number).sort((a,b) => a-b);
  var swaps = state.hand.map(k => templates.map(t => GwaiV8Mulligan.potential(GwaiV8Mulligan.exchanged(state,k,t))));
  var out = {choice: GwaiV8Mulligan.choose(state), potential: GwaiV8Mulligan.potential(state), swaps: swaps};
  if(JSON.stringify(state) !== before) throw new Error("source mutated");
  return out;
})));'''
    process = subprocess.run(['node', script_file(script)], input=json.dumps([payload(s) for s in states]),
                             capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def test_opening_exchange_matches_simulator():
    cases = [(pair, seed, swap, mode) for mode in ('original', 'balanced', 'strong')
             for pair in range(0, 60, 4) for seed, swap in ((11, False), (12, True))]
    states = opening_positions(cases)
    assert len(states) >= len(cases)
    actual = run_js(states)
    chosen = 0
    for state, result in zip(states, actual):
        expected = choose_mulligan(state)
        assert result['choice'] == (-1 if expected.source is None else expected.source)
        assert result['potential'] == initial_hand_potential(state)
        templates = sorted(t for t, n in state.counts.items() if n > 0)
        assert result['swaps'] == [[initial_hand_potential(exchanged(state, key, t)) for t in templates]
                                   for key in state.hand]
        chosen += expected.source is not None
    # The corpus must exercise both outcomes.
    assert 0 < chosen < len(states)


def test_leader_weather_first_matches_simulator():
    """GwaiV8Mulligan.chooseWithLeader = evaluate_mulligan's "combined" exchange."""
    from gwentsim.npc_balance import LEADER_PICK
    from evaluate_pool import player_setup, setup
    templates = setup()['match'].templates
    # NPCs whose leader pulls a weather card from the deck; several deals each.
    pullers = [i for i, (npc, _) in enumerate(player_setup())
               if templates[npc.deck.selected_king_index].get_first_effect() in LEADER_PICK][:16]
    cases = [(pair, seed, False, mode) for mode in ('balanced', 'strong') for pair in pullers
             for seed in (21, 22, 23)]
    states = opening_positions(cases)
    leaders = [s.leader_effect(s.player) for s in states]
    script = core_javascript() + '\nvar inputs=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += ('\nconsole.log(JSON.stringify(inputs.map(d => GwaiV8Mulligan.chooseWithLeader('
               'Object.assign(new GwaiV8Position(), d.state), d.leader))));')
    process = subprocess.run(['node', script_file(script)], input=json.dumps(
        [dict(state=payload(s), leader=-1 if e is None else e) for s, e in zip(states, leaders)]),
        capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    actual = json.loads(process.stdout)
    pulled = 0
    for state, effect, choice in zip(states, leaders, actual):
        weather = LEADER_PICK.get(effect)
        key = next((k for k in state.hand if weather is not None and state.cards[k].effects[:1] == (weather,)), None)
        if key is None:
            decision = choose_mulligan(state)
            key = -1 if decision.source is None else decision.source
        else:
            pulled += 1
        assert choice == key
    assert pulled > 0
