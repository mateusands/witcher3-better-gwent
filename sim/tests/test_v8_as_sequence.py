"""Exact sequence-plan and public utility parity through the scoped JS adapter."""
from dataclasses import asdict, replace
import json
import random
import subprocess

import pytest
from test_horn_evaluation import board, card, horn, unit
from test_position import capture
from test_v8_as_position import payload
from test_v8_as_leaders import with_leader
from gwentsim import constants as C
from gwentsim.position import Action
from gwentsim.sequence_search import Context, utility, public_opponent_average, faction_carry, overtaking_bounds, choose_sequence
from v8_as_test import core_javascript, script_file


def run(samples, expression):
    script = core_javascript()+'\nvar samples=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += '\nconsole.log(JSON.stringify(samples.map(data => {var state=Object.assign(new GwaiV8Position(),data.state); var before=JSON.stringify(state); var out='+expression+'; if(before!==JSON.stringify(state))throw new Error("input mutated"); return out;})));'
    process = subprocess.run(['node',script_file(script)],input=json.dumps(samples),capture_output=True,text=True)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def ctx(**changes):
    return replace(Context(1,0,1,True,0,3,1),**changes)


def test_seed234_utility_and_faction_carry_matrix(board):
    unit(board,6,5); card(board,4,1,9)
    card(board,8,5,9,player=1); card(board,3,2,265,(34,))
    card(board,7,2,9,player=1); card(board,15,5,137)
    state=capture(board); state.counts={1:2}; state=with_leader(state,18)
    rng=random.Random(234); samples=[]; expected=[]
    for n in range(400):
        context=ctx(round_index=rng.randrange(3),own_losses=rng.randrange(2),opponent_losses=rng.randrange(2),
            opponent_passed=bool(rng.randrange(2)),opponent_hand_count=rng.randrange(10),
            own_faction=rng.randrange(1,6),opponent_faction=rng.randrange(1,6),
            own_leader_available=bool(rng.randrange(2)),opponent_leader_available=bool(rng.randrange(2)))
        depth=rng.randrange(4); reserve=rng.randrange(40); passing=bool(rng.randrange(2)); enemy=None if n%2 else rng.randrange(40)
        mean=public_opponent_average(state)
        samples.append(dict(state=payload(state),context=asdict(context),depth=depth,reserve=reserve,passing=passing,enemy=enemy))
        expected.append([mean,faction_carry(state,0,context.own_faction,context.round_index+1),
                         utility(state,context,depth,reserve,mean,passing,enemy)])
    actual=run(samples,'[GwaiV8Sequence.opponentAverage(state),GwaiV8Sequence.factionCarry(state,0,data.context.own_faction,data.context.round_index+1),GwaiV8Sequence.utility(state,data.context,data.depth,data.reserve,GwaiV8Sequence.opponentAverage(state),data.passing,data.enemy)]')
    for a,b in zip(actual,expected): assert a == pytest.approx(b,abs=1e-14)


@pytest.mark.parametrize('scenario',range(9))
def test_optimistic_bounds_and_explicit_unknown_cases(board,scenario):
    unit(board,6,5); unit(board,15,5,hero=True)
    card(board,12,5,9,player=1); card(board,16,3,140,player=1)
    a=card(board,4,1,9,(35,)); a.templateRef.summonFlags=[a.templateId]
    if scenario==1: horn(board)
    if scenario==2: card(board,0,1,16,(23,))
    if scenario==3: card(board,0,1,2080,(29,))
    if scenario==4: card(board,4,1,265,(34,))
    if scenario==5: card(board,0,1,32,(26,));card(board,4,5,265,(34,))
    if scenario==6: a.templateRef.effectFlags=[31];a.templateRef.summonFlags=[a.templateId]
    if scenario==7: card(board,4,5,9,(42,))
    if scenario==8: card(board,5,1,9,(42,))
    state=capture(board)
    if scenario==6: state.counts={a.templateId:2}
    actual=run([dict(state=payload(state))],'GwaiV8Sequence.bounds(state)')[0]
    expected=overtaking_bounds(state)
    assert actual == (None if expected is None else list(expected))


@pytest.mark.parametrize('level',range(4))
@pytest.mark.parametrize('scenario',range(7))
def test_sequence_decisions_budgets_and_action_order(board,scenario,level):
    cheap=card(board,5,1,9)
    card(board,10,1,137)
    horn(board)
    card(board,13,5,9,player=1)
    context=ctx()
    if scenario==1: context=ctx(own_losses=1,opponent_losses=0,opponent_passed=False,opponent_hand_count=4)
    if scenario==2: unit(board,20,5)
    if scenario==3: context=ctx(opponent_faction=2,own_faction=2)
    if scenario==4: context=ctx(round_index=0,opponent_losses=0,opponent_passed=False,opponent_hand_count=6)
    if scenario==5: card(board,4,1,265,(34,))
    if scenario==6:
        card(board,12,5,9,(42,),player=1);card(board,0,1,2080,(29,))
    state=capture(board)
    samples=[dict(state=payload(state),context=asdict(context),level=level)]
    actual=run(samples,'GwaiV8Sequence.choose(state,data.context,data.level)')[0]
    expected=json.loads(json.dumps(asdict(choose_sequence(state,context,level))))
    for key in ('utility','pass_utility'): assert actual.pop(key) == pytest.approx(expected.pop(key),abs=1e-12)
    assert actual == expected


@pytest.mark.parametrize('level',range(4))
@pytest.mark.parametrize('scenario',range(3))
def test_sequence_searches_recovery_decoy_and_muster(board,scenario,level):
    card(board,17,5,9,player=1)
    card(board,6,1,9)
    context=ctx(own_losses=1,opponent_losses=0,opponent_passed=False,opponent_hand_count=3)
    if scenario==0:
        card(board,5,1,9,(33,));card(board,7,2,9,(33,));card(board,4,2,265,(34,))
    if scenario==1:
        card(board,0,1,32,(26,));spy=card(board,4,5,265,(34,));spy.owningPlayer=1
    if scenario==2:
        trigger=card(board,4,1,9,(31,));trigger.templateRef.summonFlags=[trigger.templateId];horn(board)
    state=capture(board)
    if scenario==2:
        state.counts={trigger.templateId:2};state=with_leader(state,18)
    actual=run([dict(state=payload(state),context=asdict(context),level=level)],'GwaiV8Sequence.choose(state,data.context,data.level)')[0]
    expected=json.loads(json.dumps(asdict(choose_sequence(state,context,level))))
    for key in ('utility','pass_utility'): assert actual.pop(key) == pytest.approx(expected.pop(key),abs=1e-12)
    assert actual == expected
