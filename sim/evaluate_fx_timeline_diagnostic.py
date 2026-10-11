#!/usr/bin/env python3
"""Native-timeline diagnostic cohort; distinct from frozen default-engine results."""
import json
import multiprocessing
import os
from pathlib import Path
from time import perf_counter
import evaluate_secured_resources as paired
from evaluate import engine_hashes
from evaluate_npc_policies import setup
from mushroom_policy import mushroom_hook
from fx_timeline_diagnostic import timeline_hook

ROOT=Path(__file__).resolve().parents[1]

def main():
    os.setpriority(os.PRIO_PROCESS,0,19)
    paired.STATE.update(setup(True));paired.refinement_hook=mushroom_hook
    indices=[i for i,pair in enumerate(paired.STATE['pairs']) if all(d.faction==5 for d in pair)]
    seeds=[217,218,219]
    sources=[Path(__file__)]+[ROOT/'sim'/name for name in ('fx_timeline_diagnostic.py',
        'evaluate_secured_resources.py','evaluate_npc_policies.py','evaluate_mulligan.py',
        'evaluate.py','mushroom_policy.py','mushroom_position.py')]
    inputs=[ROOT/'game/records/g113.json',ROOT/'game/vanilla/swf/gwint_game.swf']+[
        ROOT/f'game/vanilla/as/scripts/{name}.as' for name in ('CardFXDeploy','CardFXScorch')]+sorted(
        (ROOT/'game/vanilla/xml/content0/gameplay/items').glob('*.xml'))
    engine=engine_hashes();source=paired.files_hash(sources);data=paired.files_hash(inputs)
    tasks=[(pair,seed,swap) for pair in indices for seed in seeds for swap in (False,True)]
    started=perf_counter()
    with timeline_hook() as timelines:
        with multiprocessing.get_context('fork').Pool(2) as pool:
            groups=pool.map(paired.group,tasks)
    rows=[r for subset,error in groups for r in subset];errors=[error for subset,error in groups if error]
    report=dict(revision='mushroom-projection-v1',engineVariant='native-deploy-scorch-timeline-diagnostic-v1',
        diagnosticOnly=True,profile='expert',seeds=seeds,
        pairPlan=[dict(pair=i,decks=[d.name for d in paired.STATE['pairs'][i]],leaders=[d.leader for d in paired.STATE['pairs'][i]]) for i in indices],
        trials=rows,errors=errors,summary=paired.summarize(rows),timelines=timelines,
        engineSourceSha256=engine,evaluationSourceSha256=source,inputDataSha256=data,
        engineUnchanged=engine==engine_hashes(),evaluationUnchanged=source==paired.files_hash(sources),
        inputsUnchanged=data==paired.files_hash(inputs),elapsedSeconds=perf_counter()-started,
        scope='Automatic Skellige resurrection timing diagnostic. Original V7 versus Mushroom projection on both seats/orders of unchanged native Skellige pairs. Both arms use the same isolated timeline hook. Known seeds included for regression coverage; not independent strength evidence. Never pool with default-engine results.')
    output=ROOT/'game/evaluations/mushroom-projection-v1/native-timeline-skellige-217-219-diagnostic.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('errors','summary','elapsedSeconds','engineUnchanged','evaluationUnchanged','inputsUnchanged')}),flush=True)
    return int(bool(errors) or not all(report[k] for k in ('engineUnchanged','evaluationUnchanged','inputsUnchanged')))

if __name__=='__main__':raise SystemExit(main())
