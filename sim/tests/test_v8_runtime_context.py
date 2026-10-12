"""Native bridge source checks/execution; no real Flash or WS engine claimed."""
from dataclasses import asdict
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"sim"))
sys.path.insert(0,str(ROOT/"tools"))

import pytest
from gwentsim.sequence_search import Context
from v8_as_test import core_javascript, close_brace, strip_types, script_file
from v8_runtime_patch import patch, NATIVE_CLASSES

ROOT=Path(__file__).resolve().parents[2]
NATIVE=ROOT/'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'


def method(source,name,accessor=''):
    pattern=r'function\s+'+(accessor+r'\s+' if accessor else '')+name+r'\([^)]*\)[^{]*\{'
    match=re.search(pattern,source)
    assert match,name
    return strip_types(source[match.end():close_brace(source,match.end())-1])


def execute(script):
    result=subprocess.run(['node',script_file(script)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def test_native_status_cache_updates_on_observation_set_and_round_reset():
    source=patch('BasePlayerController',(NATIVE/'BasePlayerController.as').read_text())
    getter=method(source,'currentRoundStatus','get');setter=method(source,'currentRoundStatus','set')
    safe=method(source,'gwaiObservedRoundStatus','get')
    script='''
    const ROUND_PLAYER_STATUS_DONE=2;
    var consulted=0, empty=false, controller={playerID:1,_currentRoundStatus:1,_gwaiObservedRoundStatus:1};
    const CardManager={CARD_LIST_LOC_HAND:1,getInstance:()=>({getCardInstanceList:()=>({length:empty?0:3}),getCardLeader:()=>({get canBeUsed(){++consulted;return false;}})})};
    var getNative=function(){%s};var setNative=function(value){%s};var getPublic=function(){%s};
    var out=[];out.push(getPublic.call(controller));
    empty=true;out.push(getNative.call(controller));out.push(getPublic.call(controller));
    out.push(consulted);setNative.call(controller,1);out.push(getPublic.call(controller));
    setNative.call(controller,2);out.push(getPublic.call(controller));out.push(consulted);
    console.log(JSON.stringify(out));
    ''' % (getter,setter,safe)
    assert execute(script)==[1,2,2,1,1,2,1]
    # The public getter contains neither a native status read nor deck eligibility.
    assert 'canBeUsed' not in safe and 'getCardInstanceList' not in safe


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('autoplay',[False,True])
@pytest.mark.parametrize('level',range(4))
def test_native_match_snapshot_and_both_side_profile_contract(enabled,autoplay,level):
    source=patch('GwintGameFlowController',(NATIVE/'GwintGameFlowController.as').read_text())
    configure=method(source,'gwaiConfigure');profile=method(source,'gwaiProfileForPlayer');snapshot=method(source,'gwaiSettingsSnapshot')
    data=json.dumps(dict(version=1,enabled=enabled,autoplay=autoplay,difficulty=level))
    script='function int(v){return v|0;} var flow={_gwaiMatchSettings:null,gameStarted:false};'
    script+='var configure=function(data){'+configure+'};var profile=function(side){'+profile+'};var snapshot=function(){'+snapshot+'};'
    script+='var accepted=configure.call(flow,'+data+');var first=snapshot.call(flow);first.difficulty=99;'
    script+='var rejected=configure.call(flow,{version:1,enabled:true,difficulty:3,autoplay:true});'
    script+='console.log(JSON.stringify([accepted,rejected,snapshot.call(flow),profile.call(flow,0),profile.call(flow,1),profile.call(flow,2)]));'
    level=min(level,2)   # an old Expert (3) plays as Hard
    expected=dict(enabled=enabled,difficulty=level,autoplay=enabled and autoplay)
    assert execute(script)==[True,False,expected,level if enabled and autoplay else -1,level if enabled else -1,-1]


@pytest.mark.parametrize('level', range(4))
def test_enabled_profiles_for_both_sides_never_consult_native_difficulty(level):
    source=patch('GwintGameFlowController',(NATIVE/'GwintGameFlowController.as').read_text())
    configure=method(source,'gwaiConfigure');profile=method(source,'gwaiProfileForPlayer')
    script=core_javascript()+'\nvar out=[];'
    script+='var configure=function(data){'+configure+'};var profile=function(side){'+profile+'};'
    script+='for(var nativeLevel of [0,1,2,3]){var flow={_gwaiMatchSettings:null,gameStarted:false};'
    script+='Object.defineProperty(flow,"difficulty",{get:()=>{throw new Error("native difficulty read");}});'
    script+='Object.defineProperty(flow,"gwent_difficulty",{get:()=>{throw new Error("native fact read");}});'
    script+='configure.call(flow,{version:1,enabled:true,autoplay:true,difficulty:'+str(level)+'});'
    script+='out.push([0,1].map(side=>GwaiV8Sequence.profile(profile.call(flow,side))));}'
    script+='console.log(JSON.stringify(out));'
    level=min(level,2)   # an old Expert (3) plays as Hard
    expected=dict(label=['Easy','Normal','Hard'][level],search_depth=[1,2,2][level],beam_width=[4,8,8][level])
    assert execute(script)==[[expected,expected]]*4


@pytest.mark.parametrize('side',[0,1])
@pytest.mark.parametrize('winners',[[],[0],[1],[-1],[0,1]])
def test_fair_context_uses_only_public_status_count_results_and_leaders(side,winners):
    script=core_javascript()+'''
    var own=%s;var winners=%s;
    // leader_ready differs from leaderUnmodeled on purpose: the context must use the latter
    // (a modeled, unused leader must not block passing; in-game match g126).
    var state={player:own,cards:{10:{faction:3},11:{faction:2}},leaders:{0:10,1:11},leader_ready:{0:true,1:true},
       leaderUnmodeled:s=>s===1};
    var controller={gwaiObservedRoundStatus:2,get currentRoundStatus(){throw new Error("private status getter");}};
    var manager={roundResults:winners.map(w=>({played:true,getRoundWinner:()=>w})),gwaiPublicHandCount:side=>7,
       get playerDeckDefinitions(){throw new Error("private deck access");}};
    var flow={gwaiRoundIndex:winners.length,playerControllers:[controller,controller]};
    console.log(JSON.stringify(GwaiV8Context.capture(manager,flow,state)));
    ''' % (side,json.dumps(winners))
    losses=[sum(w!=s for w in winners) for s in (0,1)]
    expected=Context(len(winners),losses[side],losses[1-side],True,7,[3,2][side],[3,2][1-side],side==1,side!=1)
    assert execute(script)==json.loads(json.dumps(asdict(expected)))


def test_native_anchors_and_ws_packet_channel_are_connected():
    for name in NATIVE_CLASSES:
        result=patch(name,(NATIVE/(name+'.as')).read_text())
        assert 'gwai' in result
        with pytest.raises(ValueError):patch(name,result)
    source=(ROOT/'mod/settings/modGwentAISettings/content/scripts/local/gwai_settings.ws').read_text()
    assert 'm_flashValueStorage.SetFlashObject("gwai.match.settings", packet);' in source
    assert 'packet.SetMemberFlashInt("version", 1);' in source
    menu=patch('GwintGameMenu',(NATIVE/'GwintGameMenu.as').read_text())
    assert 'GameEvent.REGISTER,"gwai.match.settings",[this.gwaiConfigureMatch]' in menu


def test_invalid_packet_levels_normalize_and_late_packets_cannot_reconfigure():
    source=patch('GwintGameFlowController',(NATIVE/'GwintGameFlowController.as').read_text())
    configure=method(source,'gwaiConfigure')
    script='function int(v){return v|0;}var configure=function(data){'+configure+'};var out=[];'
    script+='for(var level of [-1,4,"3",null,2.5]){var flow={_gwaiMatchSettings:null,gameStarted:false};out.push(configure.call(flow,{version:1,enabled:true,difficulty:level,autoplay:true}),flow._gwaiMatchSettings.difficulty);}'
    script+='var late={_gwaiMatchSettings:null,gameStarted:true};out.push(configure.call(late,{version:1,enabled:true}),late._gwaiMatchSettings);'
    script+='var invalid={_gwaiMatchSettings:null,gameStarted:false};out.push(configure.call(invalid,{version:"1",enabled:true}),invalid._gwaiMatchSettings);console.log(JSON.stringify(out));'
    assert execute(script)==[True,2]*5+[False,None,False,None]


def test_public_hand_count_reads_length_without_any_identity():
    source=patch('CardManager',(NATIVE/'CardManager.as').read_text())
    count=method(source,'gwaiPublicHandCount')
    script='const CARD_LIST_LOC_HAND=1;var list=new Proxy({length:7},{get:(target,key)=>{if(key!=="length")throw new Error("hidden card identity");return 7;}});'
    script+='var manager={getCardInstanceList:(row,side)=>list};var count=function(side){'+count+'};console.log(JSON.stringify(count.call(manager,1)));'
    assert execute(script)==7
