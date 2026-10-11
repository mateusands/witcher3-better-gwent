#!/usr/bin/env python3
"""Check native/V7 trajectories against a previously frozen comparison artifact."""
import argparse,hashlib,json
from pathlib import Path
from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from evaluate import engine_hashes

ROOT=Path(__file__).resolve().parents[1]


def check(trial):
    match=load_match(ROOT/'game/records'/trial['pair'])
    recorder,flow=run_match(match.templates.values(),list(reversed(match.decks)) if trial['swapped'] else match.decks,
        match.card_values,SeededRandom(trial['seed']),seat_policies=tuple(trial['policies']),
        candidate_profile=3,coin_toss_choice=lambda:True)
    digest=hashlib.sha256(json.dumps(recorder.events,sort_keys=True).encode()).hexdigest()
    return dict(record=trial['pair'],swapped=trial['swapped'],policies=trial['policies'],
        winnerMatched=flow.gameWinner==trial['winner'],eventDigestMatched=digest==trial['eventSha256'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--records',nargs='+',required=True)
    parser.add_argument('--jobs',type=int,default=3)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    reference=json.loads(args.reference.read_text())
    if reference['profile']!='expert':raise ValueError('this check uses Expert reference')
    rows=[t for t in reference['trials'] if t['source']=='record' and t['pair'] in args.records
        and set(t['policies'])<={'vanilla','response-v6'}]
    hashes=engine_hashes()
    if args.jobs>1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(args.jobs) as pool:checks=pool.map(check,rows)
    else:checks=list(map(check,rows))
    report=dict(checks=checks,allMatched=bool(checks) and all(c['winnerMatched'] and c['eventDigestMatched'] for c in checks),
        referenceArtifactSha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
        currentEngineSha256=hashes,sourceUnchangedDuringRun=engine_hashes()==hashes)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(trials=len(checks),allMatched=report['allMatched'],sourceUnchanged=report['sourceUnchangedDuringRun'])))
    return int(not report['allMatched'] or not report['sourceUnchangedDuringRun'])


if __name__=='__main__':raise SystemExit(main())
