"""Execute native V8 controller hooks; actual Flash timing/FX remain unverified."""
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))

import pytest
from test_horn_evaluation import board
from v8_ai_patch import patch_ai
from v8_runtime_patch import patch
from v8_as_test import strip_types, close_brace, core_javascript

NATIVE=ROOT/'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'
SOURCE=patch_ai((NATIVE/'AIPlayerController.as').read_text())


def body(name):
    found=re.search(r'function '+name+r'\(([^)]*)\)[^{]*\{',SOURCE)
    return strip_types(found[1],True),strip_types(SOURCE[found.end():close_brace(SOURCE,found.end())-1])


def run(code,side=1,level=2,real=None):
    script='''
    const TACTIC_NONE=0,TACTIC_PASS=7,TACTIC_AVERAGE_WIN=4;
    const CardManager={CARD_LIST_LOC_HAND:1, getInstance:()=>manager,log:()=>{}};
    const getTimer=()=>0;
    var captures=0,contexts=0,prepares=0,ownRecalculations=0,cleared=[],states=[];
    var side=SIDE, level=LEVEL;
    var own=[{recalculatePowerPotential:()=>{++ownRecalculations;}}];
    var manager={gwaiClearPlan:s=>cleared.push(s),getCardInstanceList:(row,s)=>{
        if(s!==side)throw new Error("hidden hand accessed");return own;
    }};
    var fakeState={player:side};
    const GwaiV8Capture={capture:(m,s)=>{++captures;if(s!==side)throw new Error("wrong side");return fakeState;}};
    const GwaiV8Context={capture:()=>{++contexts;return {round_index:1};}};
    const GwaiV8Execution={prepare:(m,f,s,result)=>{++prepares;return {transaction:result.action,passing:result.action==null,reason:result.reason};}};
    class GwaiV8Runner{
        constructor(state,ctx,l){this.state=state;this.level=l;this.output=null;this.cancelled=false;this.slices=[];}
        advance(steps,millis,clock){this.slices.push([steps,millis,clock()]);return this.output!=null;}
        cancel(){this.cancelled=true;this.output=null;}
    }
    var flow={gameStarted:true,currentPlayer:side,gwaiRoundIndex:1,playerControllers:[],gwaiProfileForPlayer:s=>s===side?level:-1};
    Object.defineProperty(flow,"difficulty",{get:()=>{throw new Error("native difficulty accessed");}});
    var controller={playerID:side,gameFlowControllerRef:flow,_gwaiRunner:null,_gwaiPosition:null,_gwaiRound:-1,_gwaiLevel:-1,_gwaiReason:"",
       _decidedCardTransaction:null,attitude:0,_stateMachine:{ChangeState:s=>states.push(s)},
       ChooseAttitude:()=>{controller.attitude=TACTIC_AVERAGE_WIN;},decideWhichCardToPlay:()=>({native:true})};
    flow.playerControllers[side]=controller;
    '''.replace('SIDE',str(side)).replace('LEVEL',str(level))
    if real is not None:
        state, context = real
        script=script.replace('var fakeState={player:side};',
            'var fakeState=Object.assign(new GwaiV8Position(),'+json.dumps(state)+');')
        script=script.replace('const GwaiV8Capture={capture:', 'GwaiV8Capture.capture=').replace('return fakeState;}};', 'return fakeState;};')
        script=script.replace('const GwaiV8Context={capture:()=>{++contexts;return {round_index:1};}};',
            'GwaiV8Context.capture=()=>{++contexts;return '+json.dumps(context)+';};')
        script=script.replace('const GwaiV8Execution={prepare:', 'GwaiV8Execution.prepare=').replace('reason:result.reason};}};', 'reason:result.reason};};')
        start=script.index('    class GwaiV8Runner{')
        end=script.index('    var flow=',start)
        script=core_javascript()+script[:start]+script[end:]
    for name in ['gwaiCancelV8','gwaiShutdownV8','gwaiNote','gwaiBeginV8','gwaiAllowedPass','gwaiNativeFallback','gwaiPumpV8','gwaiTimeLimit','gwaiDecisionStats','gwaiPumpV8Step','state_begin_ChoseMove','state_update_ChooseMove']:
        params,method=body(name)
        script+='controller.'+name+'=function('+params+'){with(this){'+method+'}};\n'
    script+=code
    process=subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize('side',[0,1])
@pytest.mark.parametrize('level',range(4))
def test_begin_captures_selected_profile_and_yields_in_native_state(side,level):
    actual=run('''
    controller.state_begin_ChoseMove();var runner=controller._gwaiRunner;
    controller.state_update_ChooseMove();
    console.log(JSON.stringify([captures,contexts,runner.level,runner.slices,states,controller.attitude,cleared]));
    ''',side,level)
    assert actual==[1,1,level,[[1024,20,0]],[],0,[side]]


def test_off_returns_to_original_begin_without_capture():
    assert run('console.log(JSON.stringify([controller.gwaiBeginV8(),captures,contexts]));',level=-1)==[False,0,0]


@pytest.mark.parametrize('reason',['pass_for_match_resources','proven_no_supported_overtake','concede_unwinnable_chase'])
def test_authorized_passes_reach_native_idle(reason):
    actual=run('''
    controller.gwaiBeginV8();controller._gwaiRunner.output={action:null,reason:REASON};
    controller.state_update_ChooseMove();
    console.log(JSON.stringify([controller.attitude,controller._decidedCardTransaction,controller._gwaiReason,prepares,ownRecalculations,states]));
    '''.replace('REASON',json.dumps(reason)))
    assert actual==[7,None,reason,1,0,['Idle']]


@pytest.mark.parametrize('reason',['supported_response','overtake_passed_opponent_win','proactive_decoy_spy','medic_spy_retarget'])
def test_concrete_actions_reach_native_transaction_state_without_overrides(reason):
    actual=run('''
    controller.gwaiBeginV8();controller._gwaiRunner.output={action:{source:31},reason:REASON};
    controller.state_update_ChooseMove();
    console.log(JSON.stringify([controller.attitude,controller._decidedCardTransaction,controller._gwaiReason,prepares,ownRecalculations,states,cleared]));
    '''.replace('REASON',json.dumps(reason)))
    assert actual==[4,{'source':31},reason,1,0,['SendingCardToTransaction'],[1]]


@pytest.mark.parametrize('reason',['no_supported_plan','insufficient_public_catalog'])
def test_no_plan_runs_only_own_hand_native_fallback(reason):
    actual=run('''
    controller.gwaiBeginV8();controller._gwaiRunner.output={action:null,reason:REASON};
    controller.state_update_ChooseMove();
    console.log(JSON.stringify([prepares,ownRecalculations,controller.attitude,controller._decidedCardTransaction,states,controller._gwaiReason]));
    '''.replace('REASON',json.dumps(reason)))
    assert actual==[0,1,4,{'native':True},['SendingCardToTransaction'],'native_fallback:'+reason]


def test_replaced_controller_cancels_search_and_idles():
    actual=run('''
    controller.gwaiBeginV8();var runner=controller._gwaiRunner;flow.playerControllers[side]={};
    var waiting=controller.gwaiPumpV8();
    console.log(JSON.stringify([waiting,runner.cancelled,controller._gwaiRunner,controller.attitude,prepares,ownRecalculations,states,cleared]));
    ''')
    assert actual==[True,True,None,0,0,0,['Idle'],[1,1]]


@pytest.mark.parametrize('change',['flow.currentPlayer=1-side','flow.gwaiRoundIndex=2','level=3','flow.gameStarted=false'])
def test_stale_search_in_own_choose_move_falls_back_natively(change):
    # In-game a stalled ChooseMove never ends the turn; the native decision must take over.
    actual=run('''
    controller.gwaiBeginV8();var runner=controller._gwaiRunner;CHANGE;
    var waiting=controller.gwaiPumpV8();
    console.log(JSON.stringify([waiting,runner.cancelled,controller._gwaiReason,controller._decidedCardTransaction,prepares,ownRecalculations,states]));
    '''.replace('CHANGE',change))
    assert actual==[False,True,'native_fallback:stale_search',{'native':True},0,1,[]]


def test_unknown_null_action_reason_falls_back_instead_of_stalling():
    actual=run('''
    controller.gwaiBeginV8();controller._gwaiRunner.output={action:null,reason:"unexpected"};
    var waiting=controller.gwaiPumpV8();
    console.log(JSON.stringify([waiting,controller._gwaiReason,controller._decidedCardTransaction,prepares,ownRecalculations,states]));
    ''')
    assert actual==[False,'native_fallback:error',{'native':True},0,1,[]]


def test_errors_in_begin_or_search_never_stall_the_turn():
    actual=run('''
    GwaiV8Capture.capture=()=>{throw new Error("capture boom");};
    var began=controller.gwaiBeginV8();
    console.log(JSON.stringify([began,controller._gwaiRunner,cleared]));
    ''')
    assert actual==[False,None,[1,1]]
    actual=run('''
    controller.gwaiBeginV8();controller._gwaiRunner.advance=()=>{throw new Error("search boom");};
    var waiting=controller.gwaiPumpV8();
    console.log(JSON.stringify([waiting,controller._gwaiRunner,controller._gwaiReason,controller._decidedCardTransaction]));
    ''')
    assert actual==[False,None,'native_fallback:error',{'native':True}]


def test_new_decision_cancels_old_search_and_clears_effect_plan():
    assert run('''
    controller.gwaiBeginV8();var previous=controller._gwaiRunner;controller.gwaiBeginV8();
    console.log(JSON.stringify([previous.cancelled,captures,cleared,controller._gwaiRunner!==previous]));
    ''')==[True,2,[1,1],True]


def test_native_hooks_and_off_fallback_remain_in_actual_source():
    assert SOURCE.index('if(this.gwaiBeginV8()) return;')<SOURCE.index('CardManager.getInstance().CalculateCardPowerPotentials();')
    assert 'this.attitude = prepared.passing ? TACTIC_PASS : TACTIC_AVERAGE_WIN;' in SOURCE
    assert SOURCE.count('gwaiObservedRoundStatus')==2
    assert SOURCE.count('.templateRef.factionIdx : cardManagerRef.playerDeckDefinitions[')==2
    params,fallback=body('gwaiNativeFallback')
    assert 'CalculateCardPowerPotentials' not in fallback
    assert 'getCardInstanceList(CardManager.CARD_LIST_LOC_HAND,this.playerID)' in fallback
    base=patch('BasePlayerController',(NATIVE/'BasePlayerController.as').read_text())
    assert 'gwaiProfileForPlayer(this.playerID) >= 0 ?' in base
    with pytest.raises(ValueError):patch_ai(SOURCE)


@pytest.mark.parametrize('level',range(4))
@pytest.mark.parametrize('scenario',range(4))
def test_native_hook_pumps_actual_v8_to_reference_action(board,level,scenario):
    from dataclasses import asdict, replace
    from test_horn_evaluation import card, unit
    from test_position import capture
    from test_v8_as_position import payload
    from gwentsim.sequence_search import Context
    from gwentsim.response_v8 import choose_response_v8
    card(board,6,1,9);card(board,10,1,137);card(board,12,5,9,player=1)
    context=Context(0,0,0,False,3,3,1)
    if scenario==1:
        unit(board,20,5);context=replace(context,opponent_passed=True,opponent_hand_count=0)
    if scenario==2:
        card(board,60,5,9,player=1);context=replace(context,opponent_passed=True,opponent_hand_count=0)
    if scenario==3:
        card(board,7,1,138,(33,));card(board,1,2,268,(34,))
    state=capture(board);expected=choose_response_v8(state,context,level)
    result=run('''
    controller.state_begin_ChoseMove();var calls=0;
    while(controller._gwaiRunner!=null){controller.state_update_ChooseMove();if(++calls>10000)throw new Error("nonterminal");}
    console.log(JSON.stringify([controller._decidedCardTransaction,controller._gwaiReason,controller.attitude,states,ownRecalculations,prepares]));
    ''',side=0,level=level,real=(payload(state),asdict(context)))
    action=None if expected.action is None else json.loads(json.dumps(asdict(expected.action)))
    assert result==[action,expected.reason,7 if action is None else 4,
        ['Idle'] if action is None else ['SendingCardToTransaction'],0,1]


@pytest.mark.parametrize('side',[0,1])
def test_actual_native_fallback_attitude_uses_public_opponent_status_and_faction(side):
    params,attitude=body('ChooseAttitude')
    attitude=re.sub(r'(\bvar \w+):\*',r'\1',attitude)
    attitude=attitude.replace('new Vector.<CardInstance>()','[]')
    code='''
    function int(v){return v|0;}
    const ROUND_PLAYER_STATUS_DONE=2;
    const TACTIC_BESERKER=10,TACTIC_PLAY_SUICIDE=11,TACTIC_SPY_DUMMY_BEST_THEN_PASS=1,
        TACTIC_MINIMIZE_LOSS=1,TACTIC_MINIMIZE_WIN=2,TACTIC_MINIMAL_WIN=5,TACTIC_SPY=9,
        TACTIC_WAIT_DUMMY=8,TACTIC_MAXIMIZE_WIN=3,TACTIC_JUST_WAIT=6;
    const CardTemplate={CardType_Creature:8,FactionId_Nilfgaard:2};
    CardManager.PLAYER_INVALID=-1;
    controller.opponentID=1-side;
    controller.attitudeToString=()=>"test";
    flow.playerControllers[1-side]={gwaiObservedRoundStatus:2,get currentRoundStatus(){throw new Error("private eligibility getter");}};
    Object.defineProperty(manager,"playerDeckDefinitions",{get:()=>{throw new Error("private deck read");}});
    own[0].templateRef={isType:()=>true,power:6};
    var original=manager.getCardInstanceList;
    manager.getCardInstanceList=(row,s)=>s===side?original(row,s):new Proxy({length:3},{get:(target,key)=>{if(key!=="length")throw new Error("hidden identity");return 3;}});
    manager.roundResults=[];manager.currentPlayerScores=[0,0];
    manager.getCardLeader=s=>({templateRef:{factionIdx:3}});
    manager.getCardsInSlotIdWithEffect=()=>[];manager.getFirstCardInHandWithEffect=()=>null;
    controller.ChooseAttitude=function(){with(this){ATTITUDE}};
    controller.gwaiNativeFallback("no_supported_plan");
    console.log(JSON.stringify([controller.attitude,ownRecalculations,controller._decidedCardTransaction]));
    '''.replace('ATTITUDE',attitude)
    assert run(code,side=side)==[5,1,{'native':True}]



def test_shutdown_cancels_search_delay_and_transaction_before_idle():
    result=run('''
    const TimerEvent={TIMER_COMPLETE:"timerComplete"};
    controller.gwaiBeginV8();var runner=controller._gwaiRunner;
    var timer=[];controller.waitingTimer={stop:()=>timer.push("stop"),removeEventListener:(name,fn)=>timer.push(name)};
    controller.waitingForTimer=true;controller.transactionCard={pending:true};controller._decidedCardTransaction={source:31};
    controller.gwaiShutdownV8();
    console.log(JSON.stringify([runner.cancelled,timer,controller.waitingTimer,controller.waitingForTimer,
        controller.transactionCard,controller._decidedCardTransaction,controller.attitude,controller._turnOver,states]));
    ''')
    assert result==[True,['stop','timerComplete'],None,False,None,None,0,True,['Idle']]
