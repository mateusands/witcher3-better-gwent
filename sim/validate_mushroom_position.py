#!/usr/bin/env python3
"""Differential Mushroom projection check against unchanged native execution.

Uses real NPC collections/leaders and vanilla controllers, not candidate play.
Observed projections keep only own hand and public board/grave data. Runtime
recording coverage and AI strength are separate from this headless rule check.
"""
import argparse,json
from pathlib import Path
from time import perf_counter
from gwentsim import constants as C
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.position import Action
from gwentsim.rng import SeededRandom
from mushroom_position import MushroomPosition
from validate_position import public_shape,observed_shape
from evaluate import engine_hashes
from evaluate_secured_resources import files_hash

ROOT=Path(__file__).resolve().parents[1]


def validate_pair(match,decks,seed):
    pending=None;comparisons=[];unsupported=[];unexecuted=[];skipped=0
    def close_before_next_decision():
        nonlocal pending,skipped
        if pending is None:return
        side,after,entry,before=pending;pending=None
        cm=CardManager.getInstance();actual=MushroomPosition.from_manager(cm,side)
        observed=public_shape(actual)
        observed['scores']=[sum(cm.calculatePlayerScore(row,player) for row in (5,4,3)) for player in (0,1)]
        source=entry['action']['source']
        if source in actual.hand:
            # Native A events include planning retries. Require the complete
            # own/public state to be unchanged, not merely the source in hand.
            if observed==before:
                unexecuted.append(dict(sourceTemplate=entry['sourceTemplate'],
                    source=source,ownPublicStateUnchanged=True))
            else:skipped+=1
            return
        predicted=public_shape(after)
        identity_match=all(actual.cards.get(k) and actual.cards[k].template==t for k,t in entry['transformedInstances'].items())
        entry.update(match=predicted==observed and identity_match,
            identityMatches=bool(identity_match),verification='native_before_next_A',
            mismatches=[k for k in predicted if predicted[k]!=observed[k]])
        if not entry['match']:entry.update(predicted=predicted,observed=observed)
        comparisons.append(entry)
    def observe(event):
        nonlocal pending,skipped
        if event['k']=='A':
            close_before_next_decision()
            tx=event['tx']
            if tx is None:return
            side=event['player'];state=MushroomPosition.from_manager(CardManager.getInstance(),side)
            source=state.cards.get(tx['source'][1])
            if source is None or not any(source.has(e) for e in (C.CardEffect_Mushroom,C.CardEffect_Morph)):return
            action=Action(source.key,tx['slot'],tx['target'][1] if tx['target'] else -1)
            try:after=state.apply(action)
            except (ValueError,KeyError) as exc:
                unsupported.append(dict(sourceTemplate=source.template,reason=str(exc)));return
            changed={k:c.template for k,c in after.cards.items() if k in state.cards and c.template!=state.cards[k].template}
            pending=(side,after,dict(sourceTemplate=source.template,action=action.__dict__,
                transformedInstances=changed),public_shape(state))
        if event['k']=='S' and event['tag'].startswith('t') and pending is not None:
            side,after,entry,before=pending;pending=None
            predicted=public_shape(after);observed=observed_shape(event,side)
            public_templates={p[1]:p[0] for player in event['players']
                for name in ('melee','ranged','siege','meleeMod','rangedMod','siegeMod','grave')
                for p in player[name]}
            identity_match=all(public_templates.get(k)==t for k,t in entry['transformedInstances'].items())
            entry.update(match=predicted==observed and identity_match,
                identityMatches=identity_match,mismatches=[k for k in predicted if predicted[k]!=observed[k]])
            if not entry['match']:entry.update(predicted=predicted,observed=observed)
            comparisons.append(entry)
    recorder,flow=run_match(match.templates.values(),decks,match.card_values,SeededRandom(seed),on_event=observe,coin_toss_choice=lambda:True)
    close_before_next_decision()
    return dict(seed=seed,decks=[d.deck_name for d in decks],leaders=[d.selected_king_index for d in decks],
        comparisons=comparisons,unsupported=unsupported,unexecuted=unexecuted,skipped=skipped)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,default=list(range(10)))
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    fixture=ROOT/'game/records/g113.json';directory=ROOT/'game/vanilla/xml/content0/gameplay/items'
    sources=[Path(__file__),ROOT/'sim/mushroom_position.py',ROOT/'sim/validate_position.py']
    source=files_hash(sources);engine=engine_hashes();inputs=files_hash([fixture]+sorted(directory.glob('*.xml')))
    match=load_match(fixture);native=NativeDecks(directory,match.templates)
    plan=[('SkelEasy','Crach'),('SkelNormal','Olgierd'),('SkelHard','SkelNormal'),('SkelTournament2','SkelHard')]
    rows=[];errors=[];started=perf_counter()
    for a,b in plan:
        for seed in args.seeds:
            for swap in (False,True):
                names=(b,a) if swap else (a,b)
                try:rows.append(validate_pair(match,[native.build(name,3,player=i) for i,name in enumerate(names)],seed))
                except (ValueError,RuntimeError) as exc:errors.append(dict(decks=names,seed=seed,error=str(exc)))
    checks=[c for r in rows for c in r['comparisons']]
    report=dict(revision='mushroom-projection-v1.1',matches=len(rows),records=rows,errors=errors,
        compared=len(checks),mismatches=sum(not c['match'] for c in checks),
        transformingActions=sum(bool(c['transformedInstances']) for c in checks),
        transformedInstances=sum(len(c['transformedInstances']) for c in checks),
        unsupported=sum(len(r['unsupported']) for r in rows),skipped=sum(r['skipped'] for r in rows),
        verifiedUnexecutedDecisions=sum(len(r['unexecuted']) for r in rows),
        engineSourceSha256=engine,projectionSourceSha256=source,inputDataSha256=inputs,
        engineUnchanged=engine==engine_hashes(),projectionUnchanged=source==files_hash(sources),
        inputsUnchanged=inputs==files_hash([fixture]+sorted(directory.glob('*.xml'))),
        elapsedSeconds=perf_counter()-started,
        scope='Unchanged native-rule/controller differential test; real NPC decks and leaders. No new game-runtime coverage or measured candidate strength.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','engineSourceSha256','projectionSourceSha256','inputDataSha256')}))
    return int(bool(errors) or not checks or report['mismatches'] or report['skipped'] or report['unsupported'] or not all(report[k] for k in ('engineUnchanged','projectionUnchanged','inputsUnchanged')))


if __name__=='__main__':raise SystemExit(main())
