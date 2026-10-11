"""Full public-belief alternating response-plan parity, including budgets."""
from dataclasses import asdict
import json
import subprocess

import pytest
from test_horn_evaluation import board, card, horn
from test_position import capture
from test_v8_as_position import payload
from test_v8_as_leaders import with_leader
from gwentsim.sequence_search import Context
from gwentsim.response_search import choose_response
from v8_as_test import core_javascript


def compare(state,context,level):
    script=core_javascript()+'\nvar data=JSON.parse(require("fs").readFileSync(0,"utf8"));var state=Object.assign(new GwaiV8Position(),data.state);'
    script+='\nvar before=JSON.stringify(state);var out=GwaiV8Response.choose(state,data.context,data.level);if(before!==JSON.stringify(state))throw new Error("input mutated");console.log(JSON.stringify(out));'
    p=subprocess.run(['node','-e',script],input=json.dumps(dict(state=payload(state),context=asdict(context),level=level)),capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    actual=json.loads(p.stdout); expected=json.loads(json.dumps(asdict(choose_response(state,context,level))))
    for field in ('value','pass_value'):assert actual.pop(field)==pytest.approx(expected.pop(field),abs=1e-12)
    aa=actual.pop('alternatives');ee=expected.pop('alternatives')
    assert len(aa)==len(ee)
    for a,e in zip(aa,ee):
        assert a['action']==e['action'];assert a['oneTurnValue']==pytest.approx(e['oneTurnValue'],abs=1e-12)
    assert actual==expected
    return actual


@pytest.mark.parametrize('level',range(4))
@pytest.mark.parametrize('scenario',range(8))
def test_response_decisions_reply_order_and_all_profiles(board,scenario,level):
    card(board,5,1,9);card(board,10,1,137)
    card(board,8,5,9,player=1);card(board,4,4,10)
    # Public catalog has both creatures and specials; opposing private hand is unused.
    card(board,0,1,16,(23,));card(board,0,1,2080,(29,));horn(board)
    context=Context(0,0,0,False,3,3,1)
    state=capture(board)
    if scenario==1:context=Context(1,1,0,False,2,2,3)
    if scenario==2:context=Context(1,0,1,True,0,3,2)
    if scenario==3:state=with_leader(state,14)
    if scenario==4:state=with_leader(state,18)
    if scenario==5:
        card(board,4,2,265,(34,));card(board,5,1,9,(33,));state=capture(board)
    if scenario==6:
        card(board,20,5,9,(42,),player=1);state=capture(board)
    if scenario==7:context=Context(0,0,0,False,99,3,1)
    compare(state,context,level)


def test_initial_reply_search_stops_at_exact_budget(board):
    for n in range(60):card(board,1+n%8,1,15)
    state=capture(board);state.hand=()
    context=Context(0,0,0,False,100,3,1)
    result=compare(state,context,0)
    assert result['nodes']==512 and result['budget_exhausted']
    assert result['reason']=='no_supported_plan' and result['action'] is None
