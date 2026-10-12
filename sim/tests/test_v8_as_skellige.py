"""The game's AS3 model plays the Skellige cards exactly like sim/skellige_position.py.

Positions come from simulated matches with Skellige NPC decks played with the "skellige"
switch (Mardroeme, Ermion, Berserkers, Clan Dimun Pirate, Kambi). For each NPC decision the
AS3 model must give the same legal moves, the same state after every move, the same reserve
(including held Mushroom + Berserker combinations) and, on a sample, the same final decision.
"""
from dataclasses import asdict
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
sys.path.insert(0, str(ROOT / 'tools'))

from gwentsim import constants as C  # noqa: E402
from gwentsim import response_v8  # noqa: E402
from test_v8_as_position import payload  # noqa: E402
from v8_as_test import core_javascript, script_file  # noqa: E402

SKELLIGE_EFFECTS = (C.CardEffect_Mushroom, C.CardEffect_Morph, C.CardEffect_SuicideSummon)


def skellige_decisions(limit_matches=10):
    import blunder_hunter as bh
    from evaluate_pool import player_setup
    pairs = [i for i, (npc, _) in enumerate(player_setup()) if npc.faction == C.FactionId_Skellige][:limit_matches]
    saved = response_v8.VARIANT
    response_v8.VARIANT = frozenset({'skellige'})
    out = []
    try:
        for pair in pairs:
            spec = dict(source='player', pair=pair, seed=31, swap=False, seat=1, profile='hard',
                        npc_decks='balanced:v090')   # the sample predates the lean decks; it only feeds parity
            _, log = bh.play(spec)
            out.extend((e['position'], e['context']) for e in log)
    finally:
        response_v8.VARIANT = saved
    return out


def touches_skellige(position):
    return any(any(position.cards[k].has(e) for e in SKELLIGE_EFFECTS) or (
        position.cards[k].is_type(C.CardType_Creature) and position.cards[k].has(C.CardEffect_Scorch))
        for k in position.hand)


@pytest.fixture(scope='module')
def decisions():
    found = [d for d in skellige_decisions() if touches_skellige(d[0])]
    assert len(found) >= 20
    return found


def run(samples, expression):
    script = core_javascript() + '\nvar inputs=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += '\nconsole.log(JSON.stringify(inputs.map(data => { var state=Object.assign(new GwaiV8Position(),data.state); return ' + expression + '; })));'
    process = subprocess.run(['node', script_file(script)], input=json.dumps(samples), capture_output=True, text=True)
    assert process.returncode == 0, process.stderr[-3000:]
    return json.loads(process.stdout)


def test_moves_transitions_and_reserve_match(decisions):
    samples = [dict(state=payload(p)) for p, _ in decisions]
    actual = run(samples, '{actions: state.actions(), reserve: state.reserve(), after: state.actions().map(a => { try { var s=state.apply(a); return {state: s, reserve: s.reserve()}; } catch(e) { return {error: e.message}; } })}')
    morphs = mushrooms = 0
    for (position, _), result in zip(decisions, actual):
        expected_actions = position.actions()
        assert result['actions'] == json.loads(json.dumps([asdict(a) for a in expected_actions]))
        assert result['reserve'] == pytest.approx(position.reserve(), abs=1e-9)
        for action, after in zip(expected_actions, result['after']):
            try:
                state = position.apply(action)
            except Exception as exc:  # noqa: BLE001 - both sides must refuse the same move
                assert 'error' in after, exc
                continue
            assert after['state'] == json.loads(json.dumps(payload(state)))
            assert after['reserve'] == pytest.approx(state.reserve(), abs=1e-9)
            card = position.cards[action.source]
            morphs += card.has(C.CardEffect_Morph)
            mushrooms += card.has(C.CardEffect_Mushroom)
    assert morphs and mushrooms


def test_final_decisions_match(decisions):
    sample = decisions[::max(1, len(decisions) // 12)][:12]
    payloads = [dict(state=payload(p), context=asdict(c)) for p, c in sample]
    actual = run(payloads, 'GwaiV8Policy.choose(state, data.context, 2)')
    for (position, context), result in zip(sample, actual):
        expected = json.loads(json.dumps(asdict(response_v8.choose_response_v8(position, context, 2))))
        assert result['action'] == expected['action'] and result['reason'] == expected['reason']
