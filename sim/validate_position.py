#!/usr/bin/env python3
"""Compare supported public-position actions to observed native next-turn snapshots.

Ordered callback/grave fidelity remains tested separately by strict replay.
"""
import json
from pathlib import Path
from collections import Counter
from gwentsim.data import load_match
from gwentsim.rng import ReplayRandom
from gwentsim.position import Position,Action,UnsupportedPosition
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.match import run_match
from gwentsim import constants as C

ROOT=Path(__file__).resolve().parents[1]
ROW_NAMES=((5,'melee'),(4,'ranged'),(3,'siege'))


def recovery_chain(snapshot,choices):
    # Recorded Medic choices name instances; the following snapshot shows the row.
    chain=[]
    for key in choices:
        row=next((r for side in (0,1) for r,name in ROW_NAMES
                  if any(x[1]==key for x in snapshot['players'][side][name])),-1)
        chain.append((key,row))
    return tuple(chain)


def public_shape(state):
    return dict(scores=list(state.scores()),
        ownHand=Counter(state.cards[k].template for k in state.hand),
        board={str((p,r)):Counter(state.cards[k].template for k in ids) for (p,r),ids in state.board.items()},
        grave={str(p):Counter(state.cards[k].template for k in ids) for p,ids in state.grave.items()})


def observed_shape(snapshot,player):
    board={}
    for side in (0,1):
        for row,name in ((5,'melee'),(4,'ranged'),(3,'siege'),(8,'meleeMod'),(7,'rangedMod'),(6,'siegeMod')):
            board[str((side,row))]=Counter(x[0] for x in snapshot['players'][side][name])
    board[str((-1,9))]=Counter(x[0] for x in snapshot['weather'])
    return dict(scores=[p['score'] for p in snapshot['players']],
        ownHand=Counter(x[0] for x in snapshot['players'][player]['hand']),board=board,
        grave={str(side):Counter(x[0] for x in snapshot['players'][side]['grave']) for side in (0,1)})


def validate(path):
    match=load_match(path);expected=match.events
    human=any(e['k'] in ('H','P','C') for e in expected)
    pending=None;index=0;compared=[];unsupported=[];skipped=0;recovery=None
    def observe(event):
        nonlocal pending,index,skipped,recovery
        i=index;index+=1
        if event['k']==('H' if human else 'A') and event['tx'] is not None:
            if pending is not None or recovery is not None:skipped+=1;pending=recovery=None
            tx=event['tx'];player=event['player'];cm=CardManager.getInstance()
            state=Position.from_manager(cm,player)
            action=Action(tx['source'][1],tx['slot'],tx['target'][1] if tx['target'] else -1)
            card=state.cards.get(action.source)
            if action.source==state.leaders.get(player):
                # Leader choices (resurrection target, weather template) are read
                # from recorded choice events or from the following snapshot.
                recovery=(player,state,action,i,tx,[]);return
            if card is not None and card.has(C.CardEffect_Nurse) and state.recovery_targets(
                    1-player if card.is_type(C.CardType_Spy) else player):
                # Apply once the recorded choices and resulting rows are known.
                recovery=(player,state,action,i,tx,[]);return
            try:
                after=state.apply(action)
                pending=(player,after,dict(event=i,source=tx['source'],action=action.__dict__))
            except (ValueError,KeyError) as error:
                unsupported.append(dict(event=i,source=tx['source'],reason=str(error)))
        if event['k']=='C' and event['choice'] in ('nurse','resurrect','weather') and recovery is not None:
            recovery[5].append(int(event['arg']))
        if event['k']=='S' and event['tag'].startswith('t') and recovery is not None:
            player,state,action,start,tx,choices=recovery;recovery=None
            if action.source==state.leaders.get(player):
                options=state.leader_actions()
                if choices:
                    options=tuple(a for a in options if a.target==choices[0]) or (Action(action.source,target=choices[0]),)
                elif len(options)>1:
                    # Weather pick without a choice event: the new weather template.
                    before={state.cards[k].template for k in state.board[-1,9]}
                    added=[x[0] for x in event['weather'] if x[0] not in before]
                    options=tuple(a for a in options if a.target in added)
                if len(options)!=1:
                    unsupported.append(dict(event=start,source=tx['source'],
                        reason='leader action not modeled or ambiguous (%d options)'%len(options)))
                else:
                    try:
                        chosen=options[0]
                        pending=(player,state.apply(chosen),dict(event=start,source=tx['source'],leader=True,
                            action=dict(chosen.__dict__)))
                    except (ValueError,KeyError) as error:
                        unsupported.append(dict(event=start,source=tx['source'],reason=str(error)))
            else:
                if not choices:
                    # Older records lack choice events: the recovered instances are the
                    # graveyard cards now on a row; a recovered Medic resolves first.
                    on_board={x[1] for side in (0,1) for _,name in ROW_NAMES for x in event['players'][side][name]}
                    moved=[k for k in state.grave[player] if k in on_board]
                    choices=sorted(moved,key=lambda k:not state.cards[k].has(C.CardEffect_Nurse))
                action=Action(action.source,action.slot,action.target,recovery_chain(event,choices))
                try:
                    pending=(player,state.apply(action),dict(event=start,source=tx['source'],
                        action=dict(action.__dict__,chain=[list(x) for x in action.chain])))
                except (ValueError,KeyError) as error:
                    unsupported.append(dict(event=start,source=tx['source'],reason=str(error)))
        if event['k']=='S' and event['tag'].startswith('t') and pending is not None:
            player,after,entry=pending
            predicted=public_shape(after);actual=observed_shape(expected[i],player)
            # Spy draws have unknown identities. Verify their score/public board
            # effects and hand count without pretending to know the drawn cards.
            if after.unknown_draws:
                predicted['ownHand']={'count':len(after.hand)+after.unknown_draws}
                actual['ownHand']={'count':len(expected[i]['players'][player]['hand'])}
            entry.update(snapshotEvent=i,match=predicted==actual,
                mismatches=[key for key in predicted if predicted[key]!=actual[key]])
            if not entry['match']:entry.update(predicted=predicted,observed=actual)
            compared.append(entry);pending=None
    run_match(match.templates.values(),match.decks,match.card_values,ReplayRandom(match.randoms()),
        double_ai=not human,scripted_events=expected if human else None,on_event=observe)
    return dict(record=path.name,comparisons=compared,unsupported=unsupported,skipped=skipped)


if __name__=='__main__':
    report=dict(records=[],errors=[])
    for path in sorted((ROOT/'game/records').glob('g[0-9][0-9][0-9].json')):
        try:report['records'].append(validate(path))
        except Exception as e:report['errors'].append(dict(record=path.name,error=str(e)))
    report['compared']=sum(len(r['comparisons']) for r in report['records'])
    report['mismatches']=sum(not c['match'] for r in report['records'] for c in r['comparisons'])
    (ROOT/'game/evaluations/position-observed.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k!='records'})
    raise SystemExit(bool(report['errors'] or report['mismatches']))
