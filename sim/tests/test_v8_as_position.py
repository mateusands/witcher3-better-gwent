"""Numeric AS3 port parity via explicit JS subset adapter (not Flash execution)."""
from dataclasses import asdict
from pathlib import Path
import json,subprocess,sys
import pytest
from test_horn_evaluation import board,card,unit,horn
from test_position import capture
from gwentsim import constants as C
from gwentsim.position import Action,UnsupportedPosition
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from v8_as_test import core_javascript


def payload(position):
    data=asdict(position)
    for field in ('board','effects'):data[field]={f'{s}:{r}':list(v) for (s,r),v in getattr(position,field).items()}
    return data


def execute(position,actions=(),suffix=''):
    setup=json.dumps(payload(position))
    script=core_javascript()+f'\nvar data={setup}; var state=Object.assign(new GwaiV8Position(),data);'
    script+='\nvar before=JSON.stringify(state); var out={scores:state.scores(),actions:state.cardActions(),states:[]};'
    for action in actions:
        script+='\nout.states.push(state.applyCard('+json.dumps(asdict(action))+'));'
    script+='\nif(before !== JSON.stringify(state)) throw new Error("source mutated");'
    script+=suffix+'\nconsole.log(JSON.stringify(out));'
    result=subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def compare(position,actions):
    result=execute(position,actions)
    assert result['scores']==list(position.scores())
    python_actions=[asdict(a) for a in position.actions()]
    assert result['actions']==json.loads(json.dumps(python_actions))
    for action,after in zip(actions,result['states']):
        expected=payload(position.apply(action))
        for field in ('hand','board','grave','effects','counts','cards','unknown_draws','draw_value','next_key'):
            assert after[field]==json.loads(json.dumps(expected[field])),field
    return result


def test_unit_horn_weather_hero_and_bond(board):
    a=card(board,4,5,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SameTypeMorale,))
    a.templateRef.summonFlags=[a.templateId]
    b=board.spawnCardInstance(a.templateId,0,5);b.inList,b.listsPlayer=5,0;board.getCardInstanceList(5,0).append(b)
    unit(board,12,5,hero=True)
    h=horn(board)
    weather=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,))
    state=capture(board)
    state.add_effect(a.instanceId,b.instanceId);state.add_effect(b.instanceId,a.instanceId)
    compare(state,[Action(h.instanceId,8),Action(weather.instanceId,9)])


def test_scorch_all_ties_and_hero_immunity(board):
    unit(board,8,5);card(board,8,4,C.CardType_Creature|C.CardType_Ranged,player=1)
    unit(board,15,3,hero=True)
    s=card(board,0,1,C.CardType_Spell|C.CardType_Global_Effect,(C.CardEffect_Scorch,))
    compare(capture(board),[Action(s.instanceId)])


def test_decoy_retrieves_spy_without_native_mutation(board):
    spy=card(board,4,5,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,),player=0)
    spy.owningPlayer=1
    decoy=card(board,0,1,C.CardType_Spell,(C.CardEffect_UnsummonDummy,))
    compare(capture(board),[Action(decoy.instanceId,-1,spy.instanceId)])


def test_medic_chain_recovers_spy_draw_counts_without_draw_order(board):
    m=card(board,7,1,C.CardType_Creature|C.CardType_Ranged|C.CardType_Hero,(C.CardEffect_Nurse,))
    n=card(board,2,2,C.CardType_Creature|C.CardType_Siege,(C.CardEffect_Nurse,))
    spy=card(board,4,2,C.CardType_Creature|C.CardType_Melee|C.CardType_Spy,(C.CardEffect_Draw2,))
    filler=card(board,6,1,C.CardType_Creature|C.CardType_Melee)
    board.playerDeckDefinitions[0].cardIndicesInDeck=[filler.templateId]*3
    state=capture(board)
    compare(state,[Action(m.instanceId,4,chain=((n.instanceId,3),(spy.instanceId,5)))])


def test_muster_consumes_hand_and_own_counts_once(board):
    m=card(board,4,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SummonClones,))
    m.templateRef.summonFlags=[m.templateId]
    second=board.spawnCardInstance(m.templateId,0,1);second.inList,second.listsPlayer=1,0
    board.getCardInstanceList(1,0).append(second)
    board.playerDeckDefinitions[0].cardIndicesInDeck=[m.templateId]*2
    compare(capture(board),[Action(m.instanceId,5)])


def test_duplicate_weather_clear_and_half_weather(board):
    unit(board,9,5);unit(board,12,4)
    w=card(board,0,9,C.CardType_Weather,(C.CardEffect_Melee,),player=-1);w.owningPlayer=0
    duplicate=card(board,0,1,C.CardType_Weather,(C.CardEffect_Melee,))
    clear=card(board,0,1,C.CardType_Weather,(C.CardEffect_ClearSky,))
    state=capture(board);state.half_weather=(True,False)
    state.effects[0,5]=(w.instanceId,);state.effects[1,5]=(w.instanceId,)
    for k in state.board[0,5]:state.add_effect(k,w.instanceId)
    compare(state,[Action(duplicate.instanceId,9),Action(clear.instanceId,9)])


def test_random_medic_and_death_effect_explicitly_unsupported(board):
    m=card(board,5,1,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_Nurse,))
    s=card(board,0,1,C.CardType_Spell,(C.CardEffect_Scorch,))
    victim=card(board,9,5,C.CardType_Creature|C.CardType_Melee,(C.CardEffect_SuicideSummon,),player=1)
    state=capture(board);state.random_recovery=True
    assert not state.supported(state.cards[m.instanceId])
    with pytest.raises(UnsupportedPosition):state.apply(Action(s.instanceId))
    suffix='''
    out.randomMedicSupported=state.supported(state.cards[%d]);
    try {state.applyCard(%s);throw new Error("death accepted");}
    catch(error) {if(!(error instanceof GwaiV8Unsupported)) throw error; out.deathRejected=true;}
    '''%(m.instanceId,json.dumps(asdict(Action(s.instanceId))))
    out=execute(state,suffix=suffix)
    assert not out['randomMedicSupported'] and out['deathRejected']


def test_capture_never_reads_opponent_hand_deck_or_leader_private_usability(board):
    unit(board,5,5);card(board,8,1,C.CardType_Creature|C.CardType_Melee)
    state=capture(board)
    suffix='''
    var keys = Object.keys(data.cards);
    var units={}; var nativeTemplates={};
    for(var key of keys) {
      var c=data.cards[key]; var t={index:c.template,power:c.power,typeArray:c.types,effectFlags:c.effects,summonFlags:c.targets,factionIdx:c.faction};
      nativeTemplates[c.template]=t;
      units[key]={instanceId:c.key,templateRef:t,owningPlayer:c.owner,listsPlayer:c.player,inList:c.row,BanishInsteadOfGraveyard:c.banished_on_clear,effectedByCardsRefList:[]};
    }
    for(var key of keys) units[key].effectedByCardsRefList=data.cards[key].applied.map(k=>units[k]);
    var hidden=new Proxy({}, {get(){throw new Error("private deck read");}});
    var enemyLeader=Object.defineProperty(Object.assign({},units[keys[0]],{instanceId:999,inList:10,listsPlayer:1,owningPlayer:1,hasBeenUsed:false}),"canBeUsed",{get(){throw new Error("private leader usability read");}});
    var cm={playerDeckDefinitions:[{cardIndicesInDeck:[]},hidden],_cardTemplates:nativeTemplates,
      cardEffectManager:{doubleSpyEnabled:false,randomResEnabled:false,getEffectsForList:(r,s)=>(data.effects[s+":"+r]||[]).map(k=>units[k])},
      cardValues:{weatherCardValue:data.weights.weather,getEffectValueDictionary:()=>data.weights},
      halfWeatherEnabled:s=>false,getCardLeader:s=>s==1?enemyLeader:null,
      getCardInstanceList:(r,s)=>{if(r==1&&s==1)throw new Error("private hand read");return (r==1?data.hand:r==2?data.grave[s]:data.board[s+":"+r]).map(k=>units[k]);}};
    out.captured=GwaiV8Capture.capture(cm,0);
    '''
    out=execute(state,suffix=suffix)
    assert out['captured']['hand']==list(state.hand)
    assert out['captured']['board']==json.loads(json.dumps(payload(state)['board']))
