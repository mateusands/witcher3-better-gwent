#!/usr/bin/env python3
"""Observe V7 pass/selection disagreements without changing moves or game RNG.

Counts search invocations, including retries, rather than applied decisions.
Only own cards and public context are saved. A heuristic disagreement is a lead
for investigation, not proof that passing is the better actual match decision.
"""
import argparse,json
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import evaluate_secured_resources as paired
from evaluate import engine_hashes
from evaluate_npc_policies import setup
from concession_eligibility import inert_mushroom_veto
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController

ROOT=Path(__file__).resolve().parents[1]


@contextmanager
def observe_pass_veto(seat,audit):
    original=ResponseAIPlayerController.search
    def search(controller,position,context):
        result=original(controller,position,context)
        if controller.playerID==seat and not context.opponent_passed and result.action is not None and result.pass_value>result.value+1e-12:
            unsupported=[position.cards[k] for k in position.hand if not position.supported(position.cards[k])]
            reasons=[]
            if context.own_losses:reasons.append('critical_life')
            if context.own_leader_available:reasons.append('unmodeled_available_leader')
            if unsupported:reasons.append('unsupported_hand')
            audit.append(dict(context=asdict(context),scores=position.scores(),
                result=result.audit(),eligibilityVetoes=reasons,
                inertMushroom=bool(inert_mushroom_veto(position)),
                ownHand=[asdict(position.cards[k]) for k in position.hand],
                unsupportedHand=[asdict(c) for c in unsupported],
                ownLeaderReady=bool((position.leader_ready or {}).get(seat)),
                unknownOwnDraws=position.unknown_draws))
        return result
    ResponseAIPlayerController.search=search
    try:yield
    finally:ResponseAIPlayerController.search=original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds',nargs='+',type=int,required=True)
    parser.add_argument('--all-npcs',action='store_true')
    parser.add_argument('--pair-indices',nargs='+',type=int)
    parser.add_argument('--reference-report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();paired.STATE.update(setup(args.all_npcs))
    indices=args.pair_indices if args.pair_indices is not None else list(range(len(paired.STATE['pairs'])))
    if not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(paired.STATE['pairs']) for i in indices):parser.error('invalid pair indices')
    source_paths=[Path(__file__),ROOT/'sim/concession_eligibility.py',ROOT/'sim/evaluate_secured_resources.py',ROOT/'sim/evaluate_npc_policies.py',ROOT/'sim/evaluate_mulligan.py',ROOT/'sim/evaluate.py']
    fixtures=[ROOT/'game/records/g113.json']+sorted((ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    if args.reference_report:fixtures.append(args.reference_report.resolve())
    engine=engine_hashes();sources=paired.files_hash(source_paths);inputs=paired.files_hash(fixtures)
    references={}
    if args.reference_report:
        for r in json.loads(args.reference_report.read_text())['trials']:
            if r['variant']=='v7' and r['kind']=='native':references[r['pair'],r['seed'],r['swapped'],r['seat']]=r
    rows=[];errors=[];started=perf_counter()
    for pair in indices:
        for seed in args.seeds:
            for swap in (False,True):
                for seat in (0,1):
                    audit=[];key=(pair,seed,swap,seat)
                    try:
                        with observe_pass_veto(seat,audit):row=paired.run(pair,seed,swap,seat,'v7','native')
                        row['passDisagreements']=audit
                        if references:
                            if key not in references:raise ValueError('missing reference match')
                            ref=references[key]
                            row['observerPreservesReference']=all(row[k]==ref[k] for k in ('initialDealSha256','eventSha256','winner','rounds'))
                            if not row['observerPreservesReference']:raise ValueError('observer changed the reference trajectory')
                        rows.append(row)
                    except (ValueError,RuntimeError) as exc:errors.append(dict(case=key,error=str(exc)))
    entries=[(r,x) for r in rows for x in r['passDisagreements']]
    summary=dict(matches=len(rows),searchDisagreements=len(entries),
        completeNoncriticalDisagreements=sum(not x['context']['own_losses'] and not x['result']['budget_exhausted'] for r,x in entries),
        inertMushroomDisagreements=sum(x['inertMushroom'] for r,x in entries),
        byFaction=dict(Counter(str(r['faction']) for r,x in entries)),
        eligibilityVetoes=dict(Counter(reason for r,x in entries for reason in x['eligibilityVetoes'])))
    report=dict(revision='pass-veto-observer-v1',trials=rows,errors=errors,summary=summary,
        engineSourceSha256=engine,observerSourceSha256=sources,inputDataSha256=inputs,
        engineUnchanged=engine==engine_hashes(),observerUnchanged=sources==paired.files_hash(source_paths),
        inputsUnchanged=inputs==paired.files_hash(fixtures),elapsedSeconds=perf_counter()-started,
        scope='Read-only own/public search-invocation audit, not action changes or strength. Native NPC decks/leaders; no opponent private cards/deck/order.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('summary','errors','engineUnchanged','observerUnchanged','inputsUnchanged','elapsedSeconds')}))
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged','observerUnchanged','inputsUnchanged')))


if __name__=='__main__':raise SystemExit(main())
