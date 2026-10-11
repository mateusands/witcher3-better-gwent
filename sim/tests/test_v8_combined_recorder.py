"""Combined instrumentation preserves policy boundary and complete rematch logs."""
from pathlib import Path
import re
import sys
import subprocess
import json

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'sim'))
import pytest
import rec_read
from build_recorder import edit_classes,RANDOM_TAGS
from v8_recorder_patch import patch_restart
from v8_runtime_patch import patch,NATIVE_CLASSES
from v8_ai_patch import patch_ai
from v8_as_test import javascript

NATIVE=ROOT/'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'


def combined_sources():
    names=set(NATIVE_CLASSES)|set(RANDOM_TAGS)|{'HumanPlayerController'}
    files={name:(NATIVE/(name+'.as')).read_text() for name in names}
    for name in NATIVE_CLASSES:files[name]=patch(name,files[name])
    edit_classes(files,'\n',autoplay_mulligan=False)
    patch_restart(files)
    files['AIPlayerController']=patch_ai(files['AIPlayerController'])
    return files


def test_combined_instrumentation_logs_only_completed_decisions(capsys):
    files=combined_sources()
    source=files['AIPlayerController']
    start=source.index('function state_update_ChooseMove')
    end=source.index('function state_begin_SendingCard',start)
    update=source[start:end]
    assert update.index('gwaiPumpV8')<update.index('gwaiTx')
    assert update.count('gwaiTx(')==1
    # Adding recorder instrumentation does not skip player mulligan selection.
    flow=files['GwintGameFlowController']
    start=flow.index('function state_begin_Mulligan')
    end=flow.index('function state_update_Mulligan',start)
    assert 'this.handleDeclineMulligan();' not in flow[start:end]
    assert 'this.cardManager.reset();\n         this.cardManager.gwaiRecorderRestart();' in flow
    for name,tag in RANDOM_TAGS.items():
        expected=len(re.findall(r'Math\.random\(\)',(NATIVE/(name+'.as')).read_text()))
        actual=re.findall(r'CardManager.gwaiRnd\("('+tag+r'\d+)"\)',files[name])
        assert actual==[tag+str(n) for n in range(1,expected+1)]
    assert files['CardManager'].count('Math.random()')==1


def test_policy_never_reads_recorder_private_snapshots():
    for path in (ROOT/'mod/v8/as3').glob('*.as'):
        text=path.read_text()
        assert not any(name in text for name in ('gwaiBuf','gwaiSnap','gwaiDeck','gwaiRecorderRestart','OnGwaiRec'))


def recorder_javascript():
    block=(ROOT/'tools/recorder_as/CardManager.block.txt').read_text()
    restart=(ROOT/'tools/recorder_as/CardManager.restart.txt').read_text()
    # Restrict translation to this original observation-only recorder class.
    block=block.replace('a:*','a:Object')
    source='internal class CardManager {public static var lastInstanceID:int = 40;'+block+restart+'}'
    source=re.sub(r':\s+',':',source)
    return javascript(source)


def test_restart_produces_separate_parseable_complete_records_without_changing_counter():
    code=recorder_javascript()+'''
    var calls=[];
    class GameEvent{static CALL="call";constructor(type,name,args=[]){this.name=name;this.args=args;}}
    const GwintGameMenu={mSingleton:{dispatchEvent:event=>calls.push([event.name,event.args])}};
    CardManager.gwaiRec("Efinal");CardManager.gwaiEnd("final");calls=[];
    var manager=new CardManager();
    manager._cardTemplates={1:{index:1,power:6,factionIdx:3,typeArray:9,effectFlags:[],summonFlags:[]}};
    manager.playerDeckDefinitions=[0,1].map(p=>({deckName:"test",selectedKingIndex:1,specialCard:0,cardIndices:[1],dynamicCardRequirements:[],dynamicCards:[]}));
    manager.cardValues={weatherCardValue:5,hornCardValue:5,drawCardValue:1,scorchCardValue:8,summonClonesCardValue:0.5,unsummonCardValue:2,improveNeighboursCardValue:4,nurseCardValue:3};
    manager.gwaiRecorderRestart();CardManager.gwaiEnd("final");
    console.log(JSON.stringify([calls,CardManager.lastInstanceID]));
    '''
    process=subprocess.run(['node','-e',code],capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    calls,counter=json.loads(process.stdout)
    assert counter==40 and calls[0]==['OnGwaiStart',[]]
    assert calls[1][0]=='OnGwaiRec' and calls[1][1][0]==0
    chunks=[args for name,args in calls if name=='OnGwaiRec']
    raw={'g100_%04d'%seq:text for seq,text in chunks}
    raw['g100_end']='%d/%d/final'%(len(chunks),len(chunks))
    info,records,problems=rec_read.load_match(raw,100)
    assert not problems
    structured=rec_read.structure(info,records)
    assert structured['instanceBase']==40
    assert len(structured['templates'])==1 and set(structured['decks'])=={'0','1'}
    assert structured['events']==[{'k':'E','reason':'final'}]


def test_rematch_instance_base_is_explicit_and_invalid_headers_are_rejected():
    record=rec_read.parse_record('I234')
    assert rec_read.structure({},[record,{'k':'E','reason':'final'}])['instanceBase']==234
    for records in ([record,record],[{'k':'F','first':0},record]):
        with pytest.raises(rec_read.RecError):rec_read.structure({},records)
    with pytest.raises(rec_read.RecError):rec_read.parse_record('I-1')


def test_ws_restart_receiver_resets_only_record_identity_and_chunk_count():
    ws=(ROOT/'mod/recorder/modGwentAIRecorder/content/scripts/local/gwai_recorder.ws').read_text()
    body=re.search(r'event OnGwaiStart\(\)\s*\{([^}]+)\}',ws)[1]
    script='var gwaiGameSet=true,gwaiRecv=12,gwaiGame=100;'+body+'console.log(JSON.stringify([gwaiGameSet,gwaiRecv,gwaiGame]));'
    result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==[False,0,100]


def test_adapter_does_not_treat_comment_period_as_member_access():
    from v8_as_test import qualify
    assert qualify('// Completed.\nready = true;',{'ready':True},set(),'Example')=='// Completed.\nExample.ready = true;'


def test_rematch_replay_setup_retains_observed_instance_ids():
    from gwentsim.data import load_match
    from gwentsim.gwint.match import run_match
    from gwentsim.gwint.card_manager import CardManager
    match=load_match(ROOT/'game/records/g000.json')
    class InitialDealReached(Exception):pass
    captured=[]
    def observe(event):
        if event['k']=='S' and event['tag']=='deal':
            captured.append(event)
            raise InitialDealReached()
    with pytest.raises(InitialDealReached):
        run_match(match.templates.values(),match.decks,match.card_values,match.replay_random(),
            on_event=observe,instance_base=234)
    assert all(instance[1]>234 for player in captured[0]['players'] for instance in player['hand'])
    assert CardManager.lastInstanceID>234
    for invalid in (-1,True,1.5):
        with pytest.raises(ValueError,match='instance_base'):
            run_match([],[],{},None,instance_base=invalid)


@pytest.mark.parametrize('previous',['none','quit','final'])
def test_close_flushes_pending_record_and_is_idempotent(previous):
    script=recorder_javascript()+'''
    var calls=[];
    class GameEvent{static CALL="call";constructor(type,name,args=[]){this.name=name;this.args=args;}}
    const GwintGameMenu={mSingleton:{dispatchEvent:event=>calls.push([event.name,event.args])}};
    var previous=PREVIOUS;
    if(previous!=="none")CardManager.gwaiEnd(previous);
    if(previous!=="final")CardManager.gwaiRec("Cnomulligan");
    CardManager.gwaiEnd("close");var count=calls.length;
    CardManager.gwaiEnd("close");
    console.log(JSON.stringify([calls,count,calls.length,CardManager.gwaiBuf,CardManager.gwaiEnded]));
    '''.replace('PREVIOUS',json.dumps(previous))
    process=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
    calls,count,after,buffer,ended=json.loads(process.stdout)
    assert count==after and buffer=='' and ended
    chunks=[args for name,args in calls if name=='OnGwaiRec']
    end=[args for name,args in calls if name=='OnGwaiEnd'][-1]
    raw={'g100_%04d'%seq:text for seq,text in chunks}
    raw['g100_end']='%d/%d/%s'%(end[0],len(chunks),end[1])
    info,records,problems=rec_read.load_match(raw,100)
    assert problems==([] if previous=='final' else ['reason=close (match not finished normally)'])
    assert records[-1]=={'k':'E','reason':'final' if previous=='final' else 'close'}
    if previous=='quit':assert records[0]=={'k':'E','reason':'quit'}


def test_both_close_paths_flush_before_shutdown(capsys):
    files=combined_sources()
    from v8_as_test import close_brace
    for name in ['gwaiStopMatch','onGameFlowDone']:
        source=files['GwintGameMenu'];start=source.index('{',source.index('function '+name+'('))+1
        body=source[start:close_brace(source,start)-1]
        assert body.index('CardManager.gwaiEnd("close");')<body.index('this.gameFlowController.gwaiStopSearches();')
