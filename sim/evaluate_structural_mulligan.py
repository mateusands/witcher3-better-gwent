#!/usr/bin/env python3
"""Same-deal NPC study of structural exchanges, with unchanged V7 gameplay.

Reuses the audited deal/exchange harness in a separate process. Prospective source
guards include this adapter and selector; no native engine or live harness edits.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import evaluate_mulligan as harness
from structural_mulligan import choose_structural_mulligan


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--all-npcs',action='store_true')
    adapter,remaining=parser.parse_known_args()
    output_parser=argparse.ArgumentParser(add_help=False)
    output_parser.add_argument('--output',type=Path,required=True)
    output_args,_=output_parser.parse_known_args(remaining)
    paths=[Path(__file__),Path(__file__).with_name('structural_mulligan.py'),Path(__file__).with_name('evaluate_npc_policies.py')]
    hashes={str(p.relative_to(harness.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if adapter.all_npcs:
        from evaluate_npc_policies import setup
        harness.STATE.update(setup(all_npcs=True))
    data=harness.setup()
    plan=[dict(pair=i,decks=[a.name,b.name],leaders=[a.leader,b.leader],factions=[a.faction,b.faction])
        for i,(a,b) in enumerate(data['pairs'])]
    sys.argv=[sys.argv[0],*remaining]
    harness.choose_mulligan=choose_structural_mulligan
    status=harness.main()
    output=output_args.output
    report=json.loads(output.read_text())
    report['selector']='structural-mulligan-v1'
    report['selectorSourceSha256']=hashes
    report['selectorSourceUnchanged']=hashes=={str(p.relative_to(harness.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    report['pairPlan']=plan
    scope=f'{len(plan)} fixed unchanged native NPC pairs, actual leaders, correlated seats/swaps; fresh seeds and different opponents remain necessary.'
    report['summary']['scope']=scope
    report['limitation']='Only redundant supported Muster groups are exchanged. Before/after potential is diagnostic, not the choice criterion. No expected-value or optimality claim. Unchanged V7 gameplay; production unintegrated. '+scope
    output.write_text(json.dumps(report,indent=2)+'\n')
    return status or int(not report['selectorSourceUnchanged'])


if __name__=='__main__':raise SystemExit(main())
