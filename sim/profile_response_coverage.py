#!/usr/bin/env python3
"""Read-only V7 search coverage diagnostic using Python return-frame inspection.

Delegates the ordinary own/public trace CLI. Never modifies rule/search code or
budgets. Counts complete own-root continuation evaluations; truncated roots do
not count as completed. Timing with this observer is not a performance benchmark.
"""
import argparse,hashlib,inspect,json,sys
from pathlib import Path
from evaluate import engine_hashes
from gwentsim import response_search
import trace_policy


def coverage(locals_,result):
    roots=locals_.get('roots',[]);profile=locals_.get('profile')
    eligible=min(len(roots),profile.beam_width) if profile and profile.search_depth>=2 else 0
    attempted=0;completed=0
    if 'root' in locals_:
        root=locals_['root']
        index=next((i for i,entry in enumerate(roots) if entry[1]==root),None)
        if index is not None:
            attempted=index+1
            completed=index if locals_.get('exhausted',False) else attempted
    return dict(nodes=result.nodes,budgetExhausted=result.budget_exhausted,
        evaluatedRoots=len(roots),eligibleContinuationRoots=eligible,
        attemptedContinuationRoots=attempted,completedContinuationRoots=completed,
        uncompletedEligibleRoots=max(0,eligible-completed))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coverage-output',type=Path,required=True)
    parser.add_argument('--seat',type=int,choices=(0,1),required=True)
    args,remaining=parser.parse_known_args()
    entries=[];original_trace=sys.gettrace();code=response_search.choose_response.__code__
    def local_trace(frame,event,arg):
        if event=='return' and hasattr(arg,'budget_exhausted'):
            context=frame.f_locals['context'];position=frame.f_locals['position']
            entries.append(dict(round=context.round_index,opponentPassed=context.opponent_passed,
                scores=position.scores(),handCount=len(position.hand),**coverage(frame.f_locals,arg)))
        return local_trace
    def observer(frame,event,arg):
        if event=='call' and frame.f_code is code and frame.f_locals['position'].player==args.seat:
            frame.f_trace_lines=False
            return local_trace
        return None
    source_paths=[Path(__file__),Path(inspect.getfile(trace_policy))]
    source={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    engine=engine_hashes();original_argv=sys.argv
    try:
        sys.argv=[str(Path(inspect.getfile(trace_policy)))]+remaining+['--seat',str(args.seat)]
        sys.settrace(observer)
        status=trace_policy.main()
    finally:
        sys.settrace(original_trace);sys.argv=original_argv
    report=dict(decisions=entries,engineSourceSha256=engine,engineUnchanged=engine==engine_hashes(),
        observerSourceSha256=source,observerUnchanged=source=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        scope='Read-only diagnostic. Correlated single trajectory, not strength or production performance evidence.')
    args.coverage_output.parent.mkdir(parents=True,exist_ok=True)
    args.coverage_output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(decisions=len(entries),exhausted=sum(e['budgetExhausted'] for e in entries),
        uncompletedRoots=sum(e['uncompletedEligibleRoots'] for e in entries))))
    return status


if __name__=='__main__':raise SystemExit(main())
