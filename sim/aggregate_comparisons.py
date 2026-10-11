#!/usr/bin/env python3
"""Validate and combine disjoint paired comparison batches without hiding failures.

Reject changed/different engine snapshots, errors, duplicate trials, incomplete
controller groups, missing deck exchanges and mismatched profiles. Strict replay
failures remain visible; this tool cannot turn exploratory results into acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compare_policies import configurations,summarize,ISMCTS,V7,score


def paired_native_analysis(trials,candidate):
    """Contrast policies on the same deck, seat, opponent and initial seed.

    Raw faction wins reflect collection strength as well as policy strength.
    Report paired differences instead, and give each observed faction equal
    weight in the secondary mean. Correlated deals are not independent evidence.
    """
    native={};baseline={}
    for trial in trials:
        key=(trial['source'],trial['pair'],trial['seed'],trial['swapped'])
        if trial['kind']=='baseline':baseline[key]=trial
        if trial['kind']!='native':continue
        side=next(i for i,p in enumerate(trial['policies']) if p!='vanilla')
        native.setdefault((*key,side),{})[trial['policies'][side]]=trial
    factions={};pairs={}
    def add(bucket,key,candidate_score,reference_score,baseline_score):
        block=bucket.setdefault(key,dict(matches=0,candidateScore=0,v7Score=0,
            nativeBaselineScore=0,netScoreDelta=0,gains=0,regressions=0,equal=0))
        delta=candidate_score-reference_score
        block['matches']+=1;block['candidateScore']+=candidate_score
        block['v7Score']+=reference_score;block['nativeBaselineScore']+=baseline_score
        block['netScoreDelta']+=delta
        block['gains']+=delta>0;block['regressions']+=delta<0;block['equal']+=delta==0
    for key,policies in native.items():
        if candidate not in policies or V7 not in policies:continue
        current,reference=policies[candidate],policies[V7];side=key[-1]
        for field in ('factions','leaders','decks'):
            if current.get(field)!=reference.get(field):
                raise ValueError('mismatched paired deck metadata: '+field)
        a=score(current['winner'],side);b=score(reference['winner'],side)
        base=score(baseline[key[:-1]]['winner'],side)
        add(factions,str(current['factions'][side]),a,b,base)
        add(pairs,f'{key[0]}:{key[1]}',a,b,base)
    count=sum(b['matches'] for b in factions.values())
    return dict(byFaction=factions,byPair=pairs,matchedGames=count,
        meanPairedScoreDelta=sum(b['netScoreDelta'] for b in factions.values())/count if count else None,
        equalFactionMeanDelta=sum(b['netScoreDelta']/b['matches'] for b in factions.values())/len(factions) if factions else None,
        allFiveFactionsCovered=set(factions)=={'1','2','3','4','5'},
        limits='Same inputs isolate the measured policy contrast, not universal strength. Equal-faction mean uses only observed factions; correlated decks/seeds and unsupported rules remain limitations.')


def diagnostics(trials,candidate=ISMCTS):
    candidate_key='ismctsScore' if candidate==ISMCTS else 'candidateScore'
    """Describe leader/seat regressions and search cost without causal claims."""
    by_leader={};by_seat={};native_factions={};search_cost={}
    for trial in trials:
        for side,policy in enumerate(trial['policies']):
            if policy=='vanilla':continue
            points=score(trial['winner'],side)
            if trial['kind']=='direct' and policy==candidate:
                for bucket,key in ((by_leader,str(trial.get('leaders',[None,None])[side])),(by_seat,str(side))):
                    block=bucket.setdefault(key,dict(matches=0,**{candidate_key:0},v7Score=0))
                    block['matches']+=1;block[candidate_key]+=points;block['v7Score']+=1-points
            if trial['kind']=='native':
                key=str(trial['factions'][side])
                block=native_factions.setdefault(key,{}).setdefault(policy,dict(matches=0,score=0))
                block['matches']+=1;block['score']+=points
            audit=trial.get('decisions',{}).get(str(side),{})
            if not audit:continue
            block=search_cost.setdefault(policy,dict(decisions=0,iterations=0,terminalRollouts=0,
                cutoffRollouts=0,coverageCutoffs=0,exactComplete=0,exactIncomplete=0,fallback=0,
                nativeUnsupported=0,maxDecisionSeconds=0))
            block['decisions']+=audit.get('turns',0)
            for field in ('iterations','terminalRollouts','cutoffRollouts','coverageCutoffs','exactComplete','exactIncomplete','fallback','nativeUnsupported'):
                block[field]+=audit.get(field,0)
            block['maxDecisionSeconds']=max(block['maxDecisionSeconds'],audit.get('maxSearchSeconds',0))
    return dict(**{('directByISMCTSLeader' if candidate==ISMCTS else 'directByCandidateLeader'):by_leader,
        ('directByISMCTSSeat' if candidate==ISMCTS else 'directByCandidateSeat'):by_seat},
        versusNativeByFaction=native_factions,pairedNative=paired_native_analysis(trials,candidate),searchCost=search_cost,
        limits='Correlated trials; scheduling affects wall time; counts do not establish the cause of a loss.')


def aggregate(reports,*,expected_records=None,expected_pool=None):
    if not reports:raise ValueError('no comparison reports')
    first=reports[0];candidate=first.get('candidate',ISMCTS);trials=[];identities=set();groups={};sources=set();seeds=set();deck_metadata={}
    for report in reports:
        if report.get('status')!='exploratory' or not report.get('sourceUnchangedDuringRun'):
            raise ValueError('invalid or source-changed batch')
        if report.get('errors'):raise ValueError('batch has simulation errors')
        if report.get('candidate',ISMCTS)!=candidate:raise ValueError('mismatched candidate')
        if report.get('inputDataUnchangedDuringRun') is False:raise ValueError('input data changed')
        if report.get('evaluationSourceUnchangedDuringRun') is False:raise ValueError('evaluation source changed')
        for key in ('engineSourceSha256','profile','comparisons','validation','inputDataSha256','evaluationSourceSha256'):
            if report.get(key)!=first.get(key):raise ValueError('mismatched '+key)
        for trial in report['trials']:
            identity=(trial['source'],trial['pair'],trial['seed'],trial['swapped'],trial['kind'],tuple(trial['policies']))
            if identity in identities:raise ValueError('duplicate comparison trial')
            metadata=tuple(trial.get(field) for field in ('factions','leaders','decks'))
            group_key=identity[:4]
            if group_key in deck_metadata and metadata!=deck_metadata[group_key]:
                raise ValueError('mismatched controller-group deck metadata')
            deck_metadata[group_key]=metadata
            identities.add(identity);trials.append(trial);sources.add(trial['source']);seeds.add(trial['seed'])
            groups.setdefault(identity[:4],set()).add(identity[4:])
    expected=set((kind,tuple(policies)) for kind,policies in configurations(first['comparisons'],candidate))
    if not groups or any(rows!=expected for rows in groups.values()):
        raise ValueError('incomplete paired controller group')
    pairs={}
    for source,pair,seed,swap in groups:
        pairs.setdefault(source,set()).add(pair)
        if (source,pair,seed,not swap) not in groups:raise ValueError('missing deck exchange')
    for source,count in (('record',expected_records),('pool',expected_pool)):
        if count is not None and len(pairs.get(source,set()))!=count:
            raise ValueError('unexpected '+source+' pair coverage')
    # Require a complete Cartesian pair/seed coverage within each source. Record
    # and pool may deliberately use different fresh seed sets; do not pool profiles.
    for source,items in pairs.items():
        source_seeds={seed for s,pair,seed,swap in groups if s==source}
        if any((source,pair,seed,swap) not in groups for pair in items for seed in source_seeds for swap in (False,True)):
            raise ValueError('incomplete pair/seed coverage')
    summary=summarize(trials,candidate)
    native={}
    for t in trials:
        if t['kind']=='native':
            side=next(i for i,p in enumerate(t['policies']) if p!='vanilla')
            native.setdefault((t['source'],t['pair'],t['seed'],t['swapped'],side),{})[t['policies'][side]]=score(t['winner'],side)
    gains=regressions=equal=0
    for outcome in native.values():
        if candidate in outcome and V7 in outcome:
            delta=outcome[candidate]-outcome[V7]
            gains+=delta>0;regressions+=delta<0;equal+=delta==0
    summary['pairedNativeOutcomes']=dict(gains=gains,regressions=regressions,equal=equal)
    return dict(status='exploratory',profile=first['profile'],seeds=sorted(seeds),
        comparisons=first['comparisons'],candidate=candidate,
        inputDataSha256=first.get('inputDataSha256'),evaluationSourceSha256=first.get('evaluationSourceSha256'),engineSourceSha256=first['engineSourceSha256'],
        validation=first['validation'],sourceUnchangedDuringRun=True,
        coverage={source:sorted(items,key=str) for source,items in pairs.items()},
        trials=trials,errors=[],summary=summary,diagnostics=diagnostics(trials,candidate),
        validationLimits='Strict replay failure remains visible; correlated seeds/seats/decks; no in-game or production acceptance.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',nargs='+',type=Path)
    parser.add_argument('--expected-records',type=int)
    parser.add_argument('--expected-pool',type=int)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:result=aggregate([json.loads(p.read_text()) for p in args.reports],expected_records=args.expected_records,expected_pool=args.expected_pool)
    except ValueError as exc:parser.error(str(exc))
    result['inputArtifacts']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in args.reports]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(coverage={s:len(pairs) for s,pairs in result['coverage'].items()},summary=result['summary'])))


if __name__=='__main__':main()
