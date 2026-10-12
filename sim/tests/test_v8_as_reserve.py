"""Own/public reserve parity, including capped maximization and recovery chains."""
from dataclasses import asdict, replace
import json
import random
import subprocess

import pytest
from test_horn_evaluation import board, card, horn
from test_position import capture
from test_v8_as_position import payload
from test_v8_as_leaders import with_leader
from gwentsim.future_value import ReserveCard, supported_reserve_power
from v8_as_test import core_javascript, script_file


def run(inputs, expression):
    script = core_javascript() + '\nvar inputs=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += '\nconsole.log(JSON.stringify(inputs.map(data => ' + expression + ')));'
    process = subprocess.run(['node',script_file(script)],input=json.dumps(inputs),capture_output=True,text=True)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def test_seed234_bounded_reserve_corpus():
    rng = random.Random(234)
    fixtures = []
    for n in range(200):
        cards = []
        for key in range(rng.randrange(10)):
            template = rng.randrange(1,5)
            rows = tuple(r for r in range(3) if rng.randrange(2))
            cards.append(ReserveCard(key,template,rng.randrange(16),rows,hero=rng.random()<.15,
                morale=rng.random()<.15,bond=rng.random()<.2,bond_targets=(template,),
                horn=rng.random()<.15,unsupported_value=rng.randrange(8)))
        if cards:
            summon = ReserveCard(-1,101,4,(0,))
            cards[0] = replace(cards[0],summons=(summon,))
            if len(cards)>1: cards[1] = replace(cards[1],summons=(summon,))
        fixtures.append(tuple(cards))
    # More than 4096 assignments: parity includes the exact truncated order.
    fixtures.append(tuple(ReserveCard(k,k,1+k%4,(0,1,2),morale=k%3==0) for k in range(10)))
    fixtures.append(())
    actual = run([[asdict(c) for c in cards] for cards in fixtures], 'GwaiV8Reserve.power(data)')
    assert actual == [supported_reserve_power(cards) for cards in fixtures]


@pytest.mark.parametrize('effect', [-1,7,9,10,11,12,13,14,15,16,18,19,20,21,36,39,44])
def test_hand_recovery_muster_and_leader_reserve(board, effect):
    a = card(board,4,1,9,(31,))
    a.templateRef.summonFlags = [a.templateId]
    card(board,5,1,9,(33,))
    card(board,4,1,9,(32,))
    card(board,15,1,137,(33,))
    card(board,6,1,11)
    horn(board)
    card(board,7,2,9,(33,))
    card(board,8,2,9)
    card(board,9,5,9)
    card(board,12,2,9,player=1)
    card(board,14,5,9,player=1)
    state = capture(board)
    state.counts = {a.templateId:2}
    state.weights.update({29:6,'weather':5})
    if effect >= 0: state = with_leader(state,effect)
    variants = [state]
    unknown = state.clone(); unknown.unknown_draws=2; unknown.draw_value=7; variants.append(unknown)
    randomized = state.clone(); randomized.random_recovery=True; variants.append(randomized)
    empty = state.clone(); empty.grave={0:(),1:()}; variants.append(empty)
    inputs = [payload(s) for s in variants]
    assert run(inputs,'Object.assign(new GwaiV8Position(),data).reserve()') == [s.reserve() for s in variants]


def test_reserve_cache_dependencies_preserve_order_and_recovery(board):
    card(board,5,1,9,(33,))
    card(board,7,2,9)
    state = capture(board)
    altered = state.clone(); altered.grave={0:(),1:()}
    unknown = state.clone(); unknown.unknown_draws=1; unknown.draw_value=2
    reversed_hand = state.clone(); reversed_hand.hand=tuple(reversed(state.hand))
    samples = [state,altered,unknown,reversed_hand]
    actual = run([payload(s) for s in samples],'Object.assign(new GwaiV8Position(),data).reserveKey()')
    expected = [json.dumps(s.reserve_key(),separators=(',',':')) for s in samples]
    assert actual == expected
    assert actual[0] != actual[1] != actual[2]
    assert actual[0] == actual[3]
