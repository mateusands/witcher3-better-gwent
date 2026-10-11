"""Consolidated V8 parity: actual search and isolated guard priority scenarios."""
from dataclasses import asdict, replace
import json
import subprocess

import pytest
from test_horn_evaluation import board, card, unit
from test_position import capture
from test_v8_as_position import payload
from gwentsim.sequence_search import Context
from gwentsim.position import Action
from gwentsim.response_search import ResponseResult
import gwentsim.response_v8 as reference
from v8_as_test import core_javascript


def compare(state,context,level=2,base=None):
    script=core_javascript()+'\nvar data=JSON.parse(require("fs").readFileSync(0,"utf8"));var state=Object.assign(new GwaiV8Position(),data.state);'
    script+='\nvar before=JSON.stringify(state);var baseBefore=JSON.stringify(data.base);var out=data.base==null?GwaiV8Policy.choose(state,data.context,data.level):GwaiV8Policy.guards(state,data.context,data.base);if(before!==JSON.stringify(state)||baseBefore!==JSON.stringify(data.base))throw new Error("input mutated");console.log(JSON.stringify(out));'
    process=subprocess.run(['node','-e',script],input=json.dumps(dict(state=payload(state),context=asdict(context),level=level,base=None if base is None else asdict(base))),capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    actual=json.loads(process.stdout);expected=json.loads(json.dumps(asdict(reference.choose_response_v8(state,context,level))))
    for field in ('value','pass_value'):assert actual.pop(field)==pytest.approx(expected.pop(field),abs=1e-12)
    aa=actual.pop('alternatives');ee=expected.pop('alternatives');assert len(aa)==len(ee)
    for a,e in zip(aa,ee):assert a['action']==e['action'] and a['oneTurnValue']==pytest.approx(e['oneTurnValue'],abs=1e-12)
    assert actual==expected
    return actual


@pytest.mark.parametrize('scenario',range(10))
def test_guard_branches_and_priority_against_forced_search(board,monkeypatch,scenario):
    plain=card(board,6,1,9)
    context=Context(0,0,0,True,0,3,1)
    move=Action(plain.instanceId,5)
    if scenario==0:unit(board,10,5);card(board,2,5,9,player=1)
    if scenario==1:
        unit(board,10,5);card(board,1,5,9,player=1);spy=card(board,1,1,265,(34,));move=Action(spy.instanceId,5)
    if scenario==2:
        card(board,5,5,9,player=1);move=None;context=replace(context,own_losses=1,round_index=1)
    if scenario==3:
        card(board,60,5,9,player=1);context=replace(context,own_leader_available=True)
    if scenario in (4,5):
        decoy=card(board,0,1,32,(26,));spy=card(board,4,5,265,(34,));spy.owningPlayer=1
        friend=unit(board,7,4);context=replace(context,opponent_passed=False,opponent_hand_count=3)
        if scenario==5:context=replace(context,own_losses=1);move=Action(decoy.instanceId,target=friend.instanceId)
    if scenario in (6,7,8,9):
        medic=card(board,7,1,138,(33,));spy=card(board,1,2,268,(34,));normal=card(board,10,2,9)
        context=replace(context,opponent_passed=False,opponent_hand_count=3)
        move=Action(medic.instanceId,4,chain=((normal.instanceId,5),))
        if scenario==7:move=None
        if scenario==8:context=replace(context,own_losses=1)
        if scenario==9:card(board,5,2,9,(33,))
    state=capture(board)
    if scenario==1:state.counts={plain.templateId:2}
    base=ResponseResult(move,.3,.2,4,12,0,False,'supported_response')
    monkeypatch.setattr(reference,'choose_response',lambda *args:base)
    result=compare(state,context,base=base)
    expected={0:'pass_for_match_resources',2:'overtake_passed_opponent_win',3:'concede_unwinnable_chase',4:'proactive_decoy_spy',5:'decoy_spy_retarget',6:'medic_spy_retarget',7:'proactive_medic_spy',9:'medic_spy_retarget'}
    if scenario in expected:assert result['reason']==expected[scenario]
    if scenario==9:assert len(result['action']['chain'])==2


@pytest.mark.parametrize('level',range(4))
@pytest.mark.parametrize('scenario',range(6))
def test_complete_v8_search_and_final_action(board,scenario,level):
    card(board,6,1,9);card(board,10,1,137);card(board,12,5,9,player=1)
    context=Context(0,0,0,False,3,3,1)
    if scenario==0:context=replace(context,opponent_passed=True,opponent_hand_count=0)
    if scenario==1:unit(board,20,5);context=replace(context,opponent_passed=True,opponent_hand_count=0)
    if scenario==2:
        card(board,0,1,32,(26,));spy=card(board,4,5,265,(34,));spy.owningPlayer=1
    if scenario==3:card(board,7,1,138,(33,));card(board,1,2,268,(34,))
    if scenario==4:
        card(board,7,1,138,(33,));card(board,1,2,268,(34,));card(board,5,2,9,(33,))
    if scenario==5:context=replace(context,own_losses=1,round_index=2)
    compare(capture(board),context,level)
