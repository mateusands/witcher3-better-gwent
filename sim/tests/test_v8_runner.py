"""Cooperative search parity and scheduling via the explicit AS3 source adapter.

This does not execute Flash frames or prove a hard per-frame time ceiling.
"""
from dataclasses import asdict, replace
import json
import subprocess

import pytest
from test_horn_evaluation import board, card, unit, horn
from test_position import capture
from test_v8_as_position import payload
from test_v8_as_leaders import with_leader
from gwentsim.sequence_search import Context, choose_sequence
from gwentsim.response_v8 import choose_response_v8
from v8_as_test import core_javascript, script_file


def execute(state, context, level, code):
    script = core_javascript() + '\nvar data=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script += 'var state=Object.assign(new GwaiV8Position(),data.state);var before=JSON.stringify(state);'
    script += code + '\nif(before!==JSON.stringify(state))throw new Error("input mutated");'
    process = subprocess.run(['node', script_file(script)], input=json.dumps(dict(state=payload(state), context=asdict(context), level=level)), capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def same(actual, expected):
    expected = json.loads(json.dumps(asdict(expected)))
    for field in ('value', 'pass_value', 'utility', 'pass_utility'):
        if field in expected:
            assert actual.pop(field) == pytest.approx(expected.pop(field), abs=1e-12)
    if 'alternatives' in expected:
        aa, ee = actual.pop('alternatives'), expected.pop('alternatives')
        assert len(aa) == len(ee)
        for a, e in zip(aa, ee):
            assert a['action'] == e['action']
            assert a['oneTurnValue'] == pytest.approx(e['oneTurnValue'], abs=1e-12)
    assert actual == expected


@pytest.mark.parametrize('level', range(4))
@pytest.mark.parametrize('scenario', range(9))
def test_runner_slices_preserve_full_python_v8_result(board, scenario, level):
    card(board,6,1,9); card(board,10,1,137); card(board,12,5,9,player=1)
    context = Context(0,0,0,False,3,3,1)
    if scenario == 0: context = replace(context,opponent_passed=True,opponent_hand_count=0)
    if scenario == 1:
        unit(board,20,5); context = replace(context,opponent_passed=True,opponent_hand_count=0)
    if scenario == 2:
        card(board,0,1,32,(26,)); spy=card(board,4,5,265,(34,)); spy.owningPlayer=1
    if scenario in (3,4):
        card(board,7,1,138,(33,)); card(board,1,2,268,(34,))
        if scenario == 4: card(board,5,2,9,(33,))
    if scenario == 5: context = replace(context,own_losses=1,round_index=2)
    if scenario == 6:
        horn(board); card(board,0,1,16,(23,)); context = replace(context,opponent_hand_count=8)
    if scenario == 7: context = replace(context,own_losses=1,opponent_losses=1,opponent_hand_count=0)
    state = capture(board)
    if scenario == 8: state = with_leader(state,18)
    actual = execute(state,context,level,'''
    var results=[];var baseline=GwaiV8Policy.choose(state,data.context,data.level);
    for(var slice of [1,7,32]){
        var runner=new GwaiV8Runner(state,data.context,data.level), calls=0;
        while(!runner.advance(slice,2)){
            if(runner.lastSteps>slice || ++calls>100000)throw new Error("slice limit");
        }
        if(JSON.stringify(runner.output)!==JSON.stringify(baseline))throw new Error("synchronous mismatch");
        results.push(runner.output);
    }
    console.log(JSON.stringify(results));
    ''')
    expected = choose_response_v8(state,context,level)
    for result in actual: same(result,expected)


@pytest.mark.parametrize('level', range(4))
@pytest.mark.parametrize('scenario', range(4))
def test_sequence_task_preserves_nodes_ties_and_limits(board,level,scenario):
    for n in range(20 if scenario==3 else 4): card(board,1+n%7,1,15)
    context=Context(1,0,1,True,0,3,1)
    card(board,40,5,9,player=1)
    if scenario==1: context=replace(context,own_losses=1,opponent_losses=0)
    if scenario==2: unit(board,100,5)
    state=capture(board)
    actual=execute(state,context,level,'''
    var task=new GwaiV8SequenceTask(state,data.context,data.level), calls=0, nodes=0;
    while(task.output==null){task.step();if(task.nodes-nodes>1||++calls>10000)throw new Error("step limit");nodes=task.nodes;}
    if(JSON.stringify(task.output)!==JSON.stringify(GwaiV8Sequence.choose(state,data.context,data.level)))throw new Error("sequence mismatch");
    console.log(JSON.stringify(task.output));
    ''')
    same(actual,choose_sequence(state,context,level))


def test_deadline_yields_between_steps_and_cancel_cannot_return_pass(board):
    card(board,6,1,9);card(board,7,1,9);card(board,8,5,9,player=1)
    state=capture(board);context=Context(0,0,0,False,3,3,1)
    actual=execute(state,context,2,'''
    var runner=new GwaiV8Runner(state,data.context,data.level), now=0,calls=0;
    while(!runner.advance(32,2,()=>now++)){
        if(runner.lastSteps>2||++calls>100000)throw new Error("clock limit");
    }
    var output=runner.output;var cancelled=new GwaiV8Runner(state,data.context,data.level);
    cancelled.advance(1,2);cancelled.cancel();var status=cancelled.advance(32,2);
    console.log(JSON.stringify([output,cancelled.cancelled,status,cancelled.output,cancelled.lastSteps]));
    ''')
    same(actual[0],choose_response_v8(state,context,2))
    assert actual[1:]==[True,True,None,0]


def test_unrelated_errors_propagate_and_invalid_slices_reject(board):
    card(board,6,1,9)
    actual=execute(capture(board),Context(0,0,0,True,0,3,1),2,'''
    var errors=[];
    for(var limits of [[0,2],[2,0],[-1,2]]){
        try{new GwaiV8Runner(state,data.context,2).advance(limits[0],limits[1]);}
        catch(error){errors.push(error.message);}
    }
    var runner=new GwaiV8Runner(state,data.context,2);state.reserve=()=>{throw new Error("unexpected projection error");};
    try{runner.advance();}catch(error){errors.push(error.message);}
    console.log(JSON.stringify(errors));
    ''')
    assert actual==['invalid V8 slice budget']*3+['unexpected projection error']


def test_initial_response_cap_is_exact_across_frames(board):
    for n in range(60):card(board,1+n%8,1,15)
    state=capture(board);state.hand=()
    context=Context(0,0,0,False,100,3,1)
    actual=execute(state,context,0,'''
    var runner=new GwaiV8Runner(state,data.context,0),calls=0;
    while(!runner.advance(7,2)){if(++calls>100000)throw new Error("nonterminal");}
    console.log(JSON.stringify(runner.output));
    ''')
    assert actual['nodes']==512 and actual['budget_exhausted']
    same(actual,choose_response_v8(state,context,0))


@pytest.mark.parametrize('cap', [40,70,150,300])
def test_exhaustion_during_root_or_continuation_matches_synchronous(board,cap):
    for n in range(10):card(board,2+n,1,9)
    card(board,8,5,9,player=1)
    context=Context(1,1,1,False,3,3,1)
    actual=execute(capture(board),context,2,'''
    var original=GwaiV8Response.prototype.charge;
    GwaiV8Response.prototype.charge=function(){this.budget=Math.min(this.budget,CAP);return original.call(this);};
    var baseline=GwaiV8Policy.choose(state,data.context,data.level);
    var runner=new GwaiV8Runner(state,data.context,data.level),calls=0;
    while(!runner.advance(1,2)){if(++calls>100000)throw new Error("nonterminal");}
    console.log(JSON.stringify([baseline,runner.output]));
    '''.replace('CAP',str(cap)))
    assert actual[0]==actual[1]
    assert actual[1]['budget_exhausted'] and actual[1]['nodes']==cap


def test_adapter_qualifies_ternary_members_but_preserves_object_keys():
    from v8_as_test import qualify
    text='return ready ? passValue : bestValue; return {passValue:passValue,bestValue:bestValue};'
    assert qualify(text,dict(ready=False,passValue=False,bestValue=False),set(),'Example') == (
        'return this.ready ? this.passValue : this.bestValue; return {passValue:this.passValue,bestValue:this.bestValue};')
