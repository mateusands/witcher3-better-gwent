#!/usr/bin/env python3
"""Paired original candidate/V7/native comparisons on records or synthetic pool.

Every group exchanges controller seats; every task pair exchanges decks. Errors
remove a whole group, never one inconvenient result. Source hashes guard each run.
Exploratory only while strict g100 replay remains unresolved; no production claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter
from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.gwint.headless import SimulationStall
from gwentsim.rng import SeededRandom
from evaluate import validation,engine_hashes

ROOT=Path(__file__).resolve().parents[1]
V7='response-v6';ISMCTS='ismcts-v1'


def configurations(comparisons,candidate=ISMCTS):
    rows=[]
    if comparisons in ('all','vanilla'):
        rows.append(('baseline',('vanilla','vanilla')))
        for policy in (V7,candidate):
            rows.extend((('native',(policy,'vanilla')),('native',('vanilla',policy))))
    if comparisons in ('all','direct'):
        rows.extend((('direct',(candidate,V7)),('direct',(V7,candidate))))
    return rows


def group(task):
    source,pair,seed,swap,profile,comparisons=task[:6]
    candidate=task[6] if len(task)>6 else ISMCTS
    if source=='record':
        match=load_match(pair);decks=list(reversed(match.decks)) if swap else match.decks
        names=[d.deck_name for d in decks]
    else:
        from evaluate_pool import setup
        state=setup();match=state['match'];a,b=state['pairs'][pair]
        seats=(b,a) if swap else (a,b);decks=[s.for_player(i) for i,s in enumerate(seats)]
        names=[s.name for s in seats]
    out=[]
    try:
        for kind,policies in configurations(comparisons,candidate):
            started=perf_counter()
            recorder,flow=run_match(match.templates.values(),decks,match.card_values,SeededRandom(seed),
                coin_toss_choice=lambda:True,seat_policies=policies,candidate_profile=profile)
            decisions={}
            for side,controller in enumerate(flow.playerControllers):
                if policies[side]!='vanilla':
                    audits=[d.get('sequenceSearch',{}) for d in controller.policy_decisions]
                    decisions[str(side)]=dict(turns=len(audits),revisions=sorted({a['revision'] for a in audits if 'revision' in a}),
                        changed=sum(bool(a.get('changed')) for a in audits),
                        fallback=sum(a.get('fallback') is not None for a in audits),
                        nativeUnsupported=sum(a.get('reason')=='native_unsupported_choice' for a in audits),
                        iterations=sum(a.get('iterations',0) for a in audits),
                        terminalRollouts=sum(a.get('terminal_rollouts',0) for a in audits),
                        cutoffRollouts=sum(a.get('cutoff_rollouts',0) for a in audits),
                        coverageCutoffs=sum(a.get('coverage_cutoffs',0) for a in audits),
                        exactComplete=sum(a.get('exact_complete') is True for a in audits),
                        exactIncomplete=sum(a.get('exact_complete') is False for a in audits),
                        maxSearchSeconds=max((a.get('elapsed_seconds',0) for a in audits),default=0))
            out.append(dict(source=source,pair=Path(pair).name if source=='record' else pair,
                seed=seed,swapped=swap,kind=kind,policies=policies,winner=flow.gameWinner,
                decks=names,factions=[match.templates[d.selected_king_index].faction for d in decks],
                leaders=[d.selected_king_index for d in decks],elapsedSeconds=perf_counter()-started,
                eventSha256=hashlib.sha256(json.dumps(recorder.events,sort_keys=True).encode()).hexdigest(),
                rounds=[dict(scores=[r.getPlayerScore(0),r.getPlayerScore(1)],winner=r.winningPlayer)
                    for r in flow.cardManager.roundResults if r.played],decisions=decisions,
                roundResources=[dict(roundIndex=int(e['tag'][2:]),hands=[len(p['hand']) for p in e['players']])
                    for e in recorder.events if e['k']=='S' and e['tag'].startswith('rr')]))
    except (SimulationStall,RuntimeError,ValueError) as exc:
        return [],dict(source=source,pair=str(pair),seed=seed,swapped=swap,detail=str(exc))
    return out,None


def score(winner,side):return 0.5 if winner not in (0,1) else float(winner==side)


def summarize(trials,candidate=ISMCTS):
    candidate_key='ismctsScore' if candidate==ISMCTS else 'candidateScore'
    direct=[t for t in trials if t['kind']=='direct']
    def direct_block(rows):
        value=sum(score(t['winner'],t['policies'].index(candidate)) for t in rows)
        return dict(matches=len(rows),**{candidate_key:value},v7Score=len(rows)-value,
            wins=sum(t['winner']==t['policies'].index(candidate) for t in rows),
            draws=sum(t['winner'] not in (0,1) for t in rows))
    native={}
    base={(t['source'],t['pair'],t['seed'],t['swapped']):t for t in trials if t['kind']=='baseline'}
    for policy in (V7,candidate):
        rows=[t for t in trials if t['kind']=='native' and policy in t['policies']]
        native[policy]=dict(matches=len(rows),score=sum(score(t['winner'],t['policies'].index(policy)) for t in rows),
            baselineSeatScore=sum(score(base[t['source'],t['pair'],t['seed'],t['swapped']]['winner'],
                t['policies'].index(policy)) for t in rows))
    by_pair={};by_faction={}
    for row in direct:
        by_pair.setdefault(str(row['pair']),[]).append(row)
        faction=str(row['factions'][row['policies'].index(candidate)])
        by_faction.setdefault(faction,[]).append(row)
    d=direct_block(direct)
    comparable=native[V7]['matches']>0 and native[V7]['matches']==native[candidate]['matches']
    return dict(direct=d,versusNative=native,
        directByPair={k:direct_block(v) for k,v in by_pair.items()},
        **{('directByISMCTSFaction' if candidate==ISMCTS else 'directByCandidateFaction'):{k:direct_block(v) for k,v in by_faction.items()}},
        sampleReplacementGate=bool(d['matches'] and d[candidate_key]>d['v7Score'] and comparable
            and native[candidate]['score']>native[V7]['score']
            and native[candidate]['score']>native[candidate]['baselineSeatScore']),
        scope='Exploratory correlated pairs; a positive sample gate alone does not establish robust improvement.')


def input_hashes():
    paths=sorted((ROOT/'game/records').glob('g[0-9][0-9][0-9].json'))+sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def evaluation_hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/'sim/compare_policies.py',ROOT/'sim/evaluate.py',ROOT/'sim/evaluate_pool.py',ROOT/'sim/replay.py')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--records',nargs='+',type=Path)
    selection.add_argument('--pool',action='store_true')
    parser.add_argument('--pairs',type=int,help='pool smoke limit, all 110 by default')
    parser.add_argument('--pair-indices',nargs='+',type=int,help='explicit pool indices for short disjoint batches')
    parser.add_argument('--seeds',nargs='+',type=int,required=True)
    parser.add_argument('--jobs',type=int,default=11)
    parser.add_argument('--profile',choices=['easy','medium','hard','expert'],default='hard')
    parser.add_argument('--candidate',choices=['ismcts-v1','response-pass-v8','resource-v9','response-v8'],default=ISMCTS)
    parser.add_argument('--comparisons',choices=['all','direct','vanilla'],default='all')
    parser.add_argument('--exploratory',action='store_true')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.jobs<1 or args.pairs is not None and args.pairs<1:parser.error('positive jobs/pairs required')
    if args.pair_indices is not None and (not args.pool or args.pairs is not None):
        parser.error('--pair-indices requires --pool and cannot combine with --pairs')
    hashes=engine_hashes();inputs=input_hashes();evaluation=evaluation_hashes();gate=validation();started=perf_counter()
    report=dict(status='exploratory',validation=gate,profile=args.profile,seeds=args.seeds,
        comparisons=args.comparisons,candidate=args.candidate,jobs=args.jobs,engineSourceSha256=hashes,inputDataSha256=inputs,evaluationSourceSha256=evaluation,trials=[],errors=[])
    if gate['failures'] and not args.exploratory:report['status']='blocked'
    else:
        if args.pool:
            from evaluate_pool import setup
            count=len(setup()['pairs'])
            indices=args.pair_indices if args.pair_indices is not None else list(range(min(args.pairs or count,count)))
            if any(i<0 or i>=count for i in indices) or len(set(indices))!=len(indices):
                parser.error('pool indices must be unique and in range')
            source='pool'
        else:indices=[str(p.resolve()) for p in args.records];source='record'
        tasks=[(source,p,s,w,['easy','medium','hard','expert'].index(args.profile),args.comparisons,args.candidate)
            for p in indices for s in args.seeds for w in (False,True)]
        if args.jobs>1:
            import multiprocessing
            with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
                groups=pool.map(group,tasks,chunksize=1)
        else:groups=list(map(group,tasks))
        for rows,error in groups:
            report['trials'].extend(rows)
            if error:report['errors'].append(error)
    report['summary']=summarize(report['trials'],args.candidate);report['sourceUnchangedDuringRun']=engine_hashes()==hashes
    report['inputDataUnchangedDuringRun']=input_hashes()==inputs
    report['evaluationSourceUnchangedDuringRun']=evaluation_hashes()==evaluation
    report['elapsedSeconds']=perf_counter()-started
    if not report['sourceUnchangedDuringRun'] or not report['inputDataUnchangedDuringRun'] or not report['evaluationSourceUnchangedDuringRun']:report['status']='invalidated-source-changed-during-run'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','summary','elapsedSeconds','sourceUnchangedDuringRun')}))
    print('trials=%d errors=%d report=%s'%(len(report['trials']),len(report['errors']),args.output))
    return int(report['status']!='exploratory' or bool(report['errors']))


if __name__=='__main__':raise SystemExit(main())
