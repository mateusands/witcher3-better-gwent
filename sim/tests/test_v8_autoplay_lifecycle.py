"""Native controller lifecycle source execution, not actual Flash/WS acceptance."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from test_v8_runtime_context import method,execute,NATIVE
from v8_runtime_patch import patch
import pytest

FLOW=patch('GwintGameFlowController',(NATIVE/'GwintGameFlowController.as').read_text())
MENU=patch('GwintGameMenu',(NATIVE/'GwintGameMenu.as').read_text())
BASE=patch('BasePlayerController',(NATIVE/'BasePlayerController.as').read_text())


def js_method(source,name,params=''):
    body=method(source,name)
    body=re.sub(r'(\w+) is (AIPlayerController|HumanPlayerController)',r'\1 instanceof \2',body)
    body=body.replace('this.playerControllers[CardManager.PLAYER_1] is HumanPlayerController','this.playerControllers[CardManager.PLAYER_1] instanceof HumanPlayerController')
    body=body.replace('(this.playerControllers[CardManager.PLAYER_1] as HumanPlayerController)','this.playerControllers[CardManager.PLAYER_1]')
    body=body.replace('this.playerControllers[CardManager.PLAYER_1] as HumanPlayerController','asHuman(this.playerControllers[CardManager.PLAYER_1])')
    return 'function('+params+'){'+body+'}'


def harness():
    script='''
    function int(v){return v|0;}
    class AIPlayerController{constructor(){this.cancels=0;}gwaiShutdownV8(){++this.cancels;}}
    class HumanPlayerController{setChoiceDialog(value){this.choice=value;}}
    function asHuman(value){return value instanceof HumanPlayerController?value:null;}
    var clears=[],changes=[],resets=0;
    var manager={boardRenderer:{board:true},playerRenderers:[{side:0},{side:1}],cardTemplatesReceived:true,
        gwaiClearPlan:s=>clears.push(s),reset:()=>{++resets;}};
    const CardManager={PLAYER_1:0,PLAYER_2:1,getInstance:()=>manager};
    const CardFXManager={getInstance:()=>({})};
    var flow={_gwaiMatchSettings:null,gameStarted:false,currentRound:0,
        mcChoiceDialog:{dialog:true},_skipButton:{skip:true},mcMessageQueue:{PushMessage:()=>{}},
        stateMachine:{ChangeState:s=>changes.push(s)},shouldDisallowStateChangeFunc:()=>false,
        playerControllers:[new HumanPlayerController(),new AIPlayerController()]};
    '''
    for name,params in [('gwaiConfigure','data'),('gwaiApplyControllers',''),('gwaiStopSearches',''),('gwaiProfileForPlayer','side'),('gwaiSettingsSnapshot',''),('state_update_Initializing',''),('state_leave_Initializing',''),('state_begin_reset','')]:
        script+='flow.'+name+'='+js_method(FLOW,name,params)+';\n'
    script+='Object.defineProperty(flow,"gwaiSettingsReady",{get:function(){return this._gwaiMatchSettings!=null;}});'
    script+='var menu={gameFlowController:flow};menu.setAIEnabled='+js_method(MENU,'setAIEnabled','turnAIOn')+';'
    script+='menu.gwaiStopMatch='+js_method(MENU,'gwaiStopMatch','request')+';'
    return script


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('autoplay',[False,True])
@pytest.mark.parametrize('legacy_ai',[False,True])
def test_controller_selection_and_native_renderer_button_bindings(enabled,autoplay,legacy_ai):
    script=harness()
    script+='var enabled='+str(enabled).lower()+',autoplay='+str(autoplay).lower()+';'
    script+='if('+str(legacy_ai).lower()+')flow.playerControllers[0]=new AIPlayerController();var old=flow.playerControllers[0];'
    script+='flow.gwaiConfigure({version:1,enabled:enabled,difficulty:3,autoplay:autoplay});'
    script+='flow.state_update_Initializing();flow.state_leave_Initializing();var c=flow.playerControllers[0];'
    script+='console.log(JSON.stringify([c instanceof AIPlayerController,c===old,old.cancels||0,c.playerID==null?null:c.playerID,c.opponentID==null?null:c.opponentID,'
    script+='c.boardRenderer===manager.boardRenderer,c.playerRenderer===manager.playerRenderers[0],c instanceof HumanPlayerController?c.choice===flow.mcChoiceDialog:null,'
    script+='c instanceof HumanPlayerController?c.skipButton===flow._skipButton:null,flow.playerControllers[1].playerRenderer===manager.playerRenderers[1],changes]));'
    want_ai=autoplay if enabled else legacy_ai
    replaced=enabled and want_ai!=legacy_ai
    assert execute(script)==[want_ai,not replaced,1 if replaced and legacy_ai else 0,
        0 if replaced else None,1 if replaced else None,True,True,None if want_ai else True,None if want_ai else True,True,['Tutorials']]


def test_initialization_waits_for_ws_packet_and_complete_card_templates():
    script=harness()+'''
    flow.state_update_Initializing();var before=changes.slice();
    flow.gwaiConfigure({version:1,enabled:true,difficulty:0,autoplay:true});
    manager.cardTemplatesReceived=false;flow.state_update_Initializing();var partial=changes.slice();
    manager.cardTemplatesReceived=true;flow.state_update_Initializing();
    console.log(JSON.stringify([before,partial,changes]));
    '''
    assert execute(script)==[[],[],['Tutorials']]


@pytest.mark.parametrize('autoplay',[False,True])
def test_late_legacy_toggle_cannot_override_enabled_frozen_selection(autoplay):
    script=harness()+'flow.gwaiConfigure({version:1,enabled:true,difficulty:2,autoplay:'+str(autoplay).lower()+'});'
    script+='flow.turnOnAI=()=>{throw new Error("legacy AI override");};flow.turnOffAI=()=>{throw new Error("legacy manual override");};'
    script+='flow.state_leave_Initializing();var original=flow.playerControllers[0];menu.setAIEnabled(true);menu.setAIEnabled(false);'
    script+='console.log(JSON.stringify([flow.playerControllers[0]===original,flow.gwaiProfileForPlayer(0),flow.gwaiProfileForPlayer(1)]));'
    assert execute(script)==[True,2 if autoplay else -1,2]


def test_off_legacy_toggle_delegates_to_vanilla():
    script=harness()+'''
    flow.gwaiConfigure({version:1,enabled:false,difficulty:3,autoplay:true});
    var toggles=[];flow.turnOnAI=s=>toggles.push(["on",s]);flow.turnOffAI=s=>toggles.push(["off",s]);
    menu.setAIEnabled(true);menu.setAIEnabled(false);console.log(JSON.stringify(toggles));
    '''
    assert execute(script)==[['on',0],['off',1]]


@pytest.mark.parametrize('autoplay',[False,True])
def test_internal_restart_cancels_plans_and_preserves_frozen_profiles(autoplay):
    script=harness()+'flow.gwaiConfigure({version:1,enabled:true,difficulty:1,autoplay:'+str(autoplay).lower()+'});'
    script+='flow.state_leave_Initializing();var controllers=flow.playerControllers.slice(),settings=flow.gwaiSettingsSnapshot();'
    script+='flow.gameStarted=true;flow.currentRound=2;flow.state_begin_reset();'
    script+='console.log(JSON.stringify([flow.gameStarted,flow.currentRound,resets,clears,changes,JSON.stringify(settings)===JSON.stringify(flow.gwaiSettingsSnapshot()),'
    script+='controllers[0]===flow.playerControllers[0],controllers[1].cancels,controllers[0].cancels||0]));'
    assert execute(script)==[False,0,1,[0,1],['SpawnLeaders'],True,True,1,1 if autoplay else 0]


def test_ws_close_event_cancels_both_sides():
    script=harness()+'''
    flow.playerControllers[0]=new AIPlayerController();flow.gameStarted=true;
    menu.gwaiStopMatch(true);
    console.log(JSON.stringify([flow.gameStarted,clears,flow.playerControllers.map(c=>c.cancels)]));
    '''
    assert execute(script)==[False,[0,1],[1,1]]
    ws=(ROOT/'mod/settings/modGwentAISettings/content/scripts/local/gwai_betting.ws').read_text()
    assert 'm_flashValueStorage.SetFlashBool("gwai.match.stop", true);' in ws
    assert ws.index('SetFlashBool("gwai.match.stop"')<ws.index('wrappedMethod();',ws.index('OnClosingMenu()'))
    assert 'GameEvent.REGISTER,"gwai.match.stop",[this.gwaiStopMatch]' in MENU


@pytest.mark.parametrize('count',[0,1])
@pytest.mark.parametrize('usable',[False,True])
def test_enabled_round_reset_allows_own_leader_without_hand(count,usable):
    reset=method(BASE,'resetCurrentRoundStatus')
    script='const ROUND_PLAYER_STATUS_ACTIVE=1,ROUND_PLAYER_STATUS_DONE=2;'
    script+='var consulted=0;const CardManager={getInstance:()=>({gwaiPublicHandCount:()=>'+str(count)+',getCardLeader:()=>({get canBeUsed(){++consulted;return '+str(usable).lower()+';}})})};'
    script+='var controller={playerID:1,currentRoundStatus:2,gameFlowControllerRef:{gwaiProfileForPlayer:()=>2}};'
    script+='var reset=function(){'+reset+'};reset.call(controller);console.log(JSON.stringify([controller.currentRoundStatus,consulted]));'
    assert execute(script)==[1 if count or usable else 2,0 if count else 1]


def test_enabled_round_reset_handles_missing_leader_without_private_lookup():
    reset=method(BASE,'resetCurrentRoundStatus')
    script='const ROUND_PLAYER_STATUS_ACTIVE=1,ROUND_PLAYER_STATUS_DONE=2;'
    script+='const CardManager={getInstance:()=>({gwaiPublicHandCount:s=>{if(s!==1)throw new Error("wrong side");return 0;},getCardLeader:s=>{if(s!==1)throw new Error("opponent leader eligibility");return null;}})};'
    script+='var controller={playerID:1,currentRoundStatus:1,gameFlowControllerRef:{gwaiProfileForPlayer:()=>2}};'
    script+='var reset=function(){'+reset+'};reset.call(controller);console.log(JSON.stringify(controller.currentRoundStatus));'
    assert execute(script)==2


def test_final_result_and_menu_close_cleanup_anchors_precede_original_behavior():
    final=method(FLOW,'state_begin_ShowingFinalResult')
    close=method(MENU,'onGameFlowDone')
    assert final.lstrip().startswith('this.gwaiStopSearches();')
    assert close.index('this.gameFlowController.gwaiStopSearches();')<close.index('closeMenu();')
    assert FLOW.index('this.gwaiApplyControllers();')<FLOW.index('this.playerControllers[CardManager.PLAYER_1].boardRenderer =')
