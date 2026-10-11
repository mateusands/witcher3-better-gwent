#!/usr/bin/env python3
"""Fresh native public-state corpus for detached AS3 numeric subset parity.

Does not waive replay g100, claim Flash execution or inspect private cards in
policy. Simulation setup/RNG is administrative; the sampled position is fair.
"""
import gzip,hashlib,json,subprocess,sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sim'));sys.path.insert(0,str(ROOT/'tools'))
from gwentsim.data import load_match
from gwentsim.position import Position,UnsupportedPosition
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.match import run_match
from gwentsim.rng import SeededRandom
from v8_as_test import core_javascript


def payload(state):
    data=asdict(state)
    for field in ('board','effects'):data[field]={f'{s}:{r}':list(v) for (s,r),v in getattr(state,field).items()}
    return data


def main():
    dest=ROOT/'game/port-v8/core';dest.mkdir(parents=True,exist_ok=True)
    samples=[];errors=[];unsupported=Counter();games=0
    for path in sorted((ROOT/'game/records').glob('g[0-9][0-9][0-9].json')):
        match=load_match(path);per_match=0
        def observe(event):
            nonlocal per_match
            if event['k'] not in ('A','H') or per_match>=10:return
            state=Position.from_manager(CardManager.getInstance(),event['player']);per_match+=1
            candidates=[a for a in state.actions() if a.source in state.hand]
            transitions=[]
            for move in candidates[:8]:
                try:transitions.append(dict(action=asdict(move),after=payload(state.apply(move))))
                except (UnsupportedPosition,ValueError) as exc:unsupported[str(exc)]+=1
            samples.append(dict(record=path.name,position=payload(state),actions=[asdict(a) for a in candidates],
                scores=state.scores(),transitions=transitions))
        try:
            run_match(match.templates.values(),match.decks,match.card_values,SeededRandom(234),coin_toss_choice=lambda:True,on_event=observe)
            games+=1
        except Exception as exc:errors.append(dict(record=path.name,error=str(exc)))
    compressed=gzip.compress(json.dumps(samples).encode())
    (dest/'numeric-fixtures.json.gz').write_bytes(compressed)
    script=core_javascript()+'''
    var fs=require('fs');var corpus=JSON.parse(fs.readFileSync(0,'utf8'));var outputs=[];
    for(var sample of corpus) {
      var state=Object.assign(new GwaiV8Position(),sample.position);var before=JSON.stringify(state);
      var entry={scores:state.scores(),actions:state.cardActions(),transitions:[]};
      for(var transition of sample.transitions) entry.transitions.push(state.applyCard(transition.action));
      if(before!==JSON.stringify(state))throw new Error('source mutated');outputs.push(entry);
    }
    console.log(JSON.stringify(outputs));
    '''
    executed=subprocess.run(['node','-e',script],input=json.dumps(samples),capture_output=True,text=True)
    assert executed.returncode==0,executed.stderr
    outputs=json.loads(executed.stdout);checks=0;mismatches=[]
    for sample,out in zip(samples,outputs):
        for field in ('scores','actions'):
            checks+=1
            if json.loads(json.dumps(sample[field]))!=out[field]:mismatches.append(dict(record=sample['record'],field=field))
        for transition,after in zip(sample['transitions'],out['transitions']):
            expected=transition['after']
            for field in ('hand','board','grave','effects','counts','cards','unknown_draws','draw_value','next_key'):
                checks+=1
                if json.loads(json.dumps(expected[field]))!=after[field]:mismatches.append(dict(record=sample['record'],action=transition['action'],field=field))
    report=dict(status='passed' if not errors and not mismatches else 'failed',seed=234,jobs=1,
        attemptedGames=23,completedGames=games,errors=errors,positions=len(samples),
        supportedTransitions=sum(len(s['transitions']) for s in samples),checks=checks,mismatches=mismatches,
        unsupported=dict(unsupported),fixtureSha256=hashlib.sha256(compressed).hexdigest(),
        scope='Native public-state numeric AS3-subset parity via JS adapter; not Flash execution or strict replay acceptance',
        knownReplay='g100 graveyard order unresolved, not waived',
        sourceSha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'mod/v8/as3').glob('*.as')})
    (dest/'numeric-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    return int(report['status']!='passed')

if __name__=='__main__':raise SystemExit(main())
