"""Native transaction/choice bridge parity without a Flash-runtime claim."""
from dataclasses import asdict
import json
import subprocess

import pytest
from test_horn_evaluation import board,card
from test_position import capture
from test_v8_as_position import payload
from test_v8_runtime_context import method,NATIVE
from gwentsim.position import Action
from v8_as_test import core_javascript, script_file
from v8_runtime_patch import patch


def run(script):
    p=subprocess.run(['node',script_file(script)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    return json.loads(p.stdout)


@pytest.mark.parametrize('kind',['unit','spy','weather','horn','decoy','medic','pass'])
def test_prepare_only_own_real_source_and_exact_transaction(board,kind):
    plain=card(board,6,1,9)
    move=Action(plain.instanceId,5)
    if kind=='spy':source=card(board,4,1,265,(34,));move=Action(source.instanceId,5)
    if kind=='weather':source=card(board,0,1,16,(23,));move=Action(source.instanceId,9)
    if kind=='horn':source=card(board,0,1,71,(27,));move=Action(source.instanceId,7)
    if kind=='decoy':
        source=card(board,0,1,32,(26,));target=card(board,4,5,265,(34,));target.owningPlayer=1;move=Action(source.instanceId,target=target.instanceId)
    if kind=='medic':
        source=card(board,7,1,138,(33,));target=card(board,1,2,268,(34,));move=Action(source.instanceId,4,chain=((target.instanceId,3),))
    if kind=='pass':move=None
    state=capture(board)
    native={str(k):dict(instanceId=k,inList=c.row,listsPlayer=c.player) for k,c in state.cards.items()}
    script='class CardTransaction {sourceCardInstanceRef=null;targetCardInstanceRef=null;targetSlotID=-1;targetPlayerID=-1;}'+core_javascript()
    script+='\nvar state=Object.assign(new GwaiV8Position(),'+json.dumps(payload(state))+');var native='+json.dumps(native)+';var lookups=[];var plan=null;'
    script+='var manager={gwaiClearPlan:()=>{plan=null;},getCardInstance:key=>{lookups.push(key);return native[key];},gwaiStorePlan:(side,p)=>{plan=p;}};'
    script+='var out=GwaiV8Execution.prepare(manager,{currentPlayer:0,gwaiRoundIndex:0},state,'+json.dumps(dict(action=None if move is None else asdict(move),reason='concede_unwinnable_chase' if move is None else 'supported_response'))+');console.log(JSON.stringify({out,plan,lookups}));'
    result=run(script)
    if move is None:
        assert result==dict(out=dict(transaction=None,passing=True,reason='concede_unwinnable_chase'),plan=None,lookups=[])
        return
    tx=result['out']['transaction']
    assert tx['sourceCardInstanceRef']['instanceId']==move.source
    assert tx['targetSlotID']==move.slot
    assert tx['targetPlayerID']==(1 if kind=='spy' else -1 if kind=='weather' else 0)
    assert result['plan']['chain']==json.loads(json.dumps(move.chain))
    assert result['lookups']==[move.source]+([move.target] if kind=='decoy' else [])


def native_queue_script():
    source=patch('CardManager',(NATIVE/'CardManager.as').read_text())
    script='function int(v){return v|0;}const CardTemplate={CardType_Hero:128,CardType_Spy:256};var flow={currentPlayer:0,gwaiRoundIndex:1};const GwintGameFlowController={getInstance:()=>flow};var manager={_gwaiPlans:{0:null,1:null}};'
    for name,args in [('gwaiClearPlan','side'),('gwaiStorePlan','side,plan'),('gwaiActivePlan','side'),('gwaiLeaderTarget','side,source'),('gwaiNurseChoice','side,source,eligible'),('gwaiTakePlacement','side,instance')]:
        script+='manager.'+name+'=function('+args+'){'+method(source,name)+'};'
    script+='function nativeCard(id,flags){return {instanceId:id,templateRef:{isType:flag=>(flags&flag)===flag}};}'
    return script


def test_native_medic_chain_uses_exact_rows_and_placing_side():
    script=native_queue_script()+'''
    manager.gwaiStorePlan(0,{round:1,source:10,target:-1,expectedMedic:10,chain:[[11,5],[12,3]],placements:{}});
    var out=[];out.push(manager.gwaiNurseChoice(0,10,[nativeCard(11,9),nativeCard(12,268)]));
    out.push(manager.gwaiTakePlacement(0,11));out.push(manager.gwaiTakePlacement(0,11) ?? null);
    out.push(manager.gwaiNurseChoice(0,11,[nativeCard(12,268)]));out.push(manager.gwaiTakePlacement(0,12));
    out.push(manager.gwaiNurseChoice(0,12,[]));console.log(JSON.stringify(out));
    '''
    assert run(script)==[11,dict(row=5,side=0),None,12,dict(row=3,side=1),-1]


@pytest.mark.parametrize('invalid',['missing','hero','row','turn','round'])
def test_native_stale_or_illegal_choice_cancels_plan(invalid):
    script=native_queue_script()+'''
    manager.gwaiStorePlan(0,{round:1,source:10,target:11,expectedMedic:10,chain:[[11,5]],placements:{}});
    var eligible=[nativeCard(11,9)];
    '''
    script+=dict(missing='eligible=[];',hero='eligible=[nativeCard(11,137)];',row='eligible=[nativeCard(11,10)];',turn='flow.currentPlayer=1;',round='flow.gwaiRoundIndex=2;')[invalid]
    script+='console.log(JSON.stringify([manager.gwaiNurseChoice(0,10,eligible),manager.gwaiActivePlan(0)]));'
    assert run(script)==[-1,None]


def test_native_leader_target_is_bound_to_source_turn_and_round():
    script=native_queue_script()+'''
    manager.gwaiStorePlan(0,{round:1,source:10,target:12,expectedMedic:10,chain:[],placements:{}});
    var out=[manager.gwaiLeaderTarget(0,10),manager.gwaiLeaderTarget(0,11)];
    flow.gwaiRoundIndex=2;out.push(manager.gwaiLeaderTarget(0,10));out.push(manager.gwaiActivePlan(0));
    console.log(JSON.stringify(out));
    '''
    assert run(script)==[12,-1,-1,None]


def test_execution_rejects_hypothetical_source_before_native_lookup(board):
    plain=card(board,6,1,9);state=capture(board)
    script='class CardTransaction {}'+core_javascript()+'\nvar state=Object.assign(new GwaiV8Position(),'+json.dumps(payload(state))+');'
    script+='var looked=false;var plan=null;var manager={gwaiClearPlan:()=>{plan=null;},getCardInstance:()=>{looked=true;throw new Error("hidden identity");}};var rejected=false;'
    script+='try{GwaiV8Execution.prepare(manager,{currentPlayer:0,gwaiRoundIndex:0},state,{action:{source:-200000000,slot:5,target:-1,chain:[]},reason:"supported_response"});}catch(error){rejected=error.message==="source outside own hand/leader";}console.log(JSON.stringify([rejected,looked,plan]));'
    assert run(script)==[True,False,None]
