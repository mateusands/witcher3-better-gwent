#!/usr/bin/env python3
"""Speed benchmark of the AS3 V8 search on real NPC decisions (node, explicit AS3 subset).

    python3 tools/v8_bench.py collect game/records/g17*.json      # fixtures from recorded matches
    python3 tools/v8_bench.py run [--reps 3] [--save out.json] [--compare base.json] [--prof DIR]

collect rebuilds each recorded match in the simulator (sim/record_review.py) and stores every NPC
decision as position + context + level in game/bench/fixtures.json (game/ is not in git).
run executes GwaiV8Policy.choose on every fixture with node and prints the time; --compare fails
when any decision differs from a saved run, so a speed change that alters a move is caught.
node runs the AS3 port as JavaScript with a JIT; the game's Scaleform does not, so only the
in-game MangoHud measurement proves a frame-rate gain.
"""
import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'sim'))
FIXTURES = ROOT / 'game/bench/fixtures.json'


def payload(position):
    data = asdict(position)
    for field in ('board', 'effects'):
        data[field] = {f'{s}:{r}': list(v) for (s, r), v in getattr(position, field).items()}
    return data


def collect(paths, out=FIXTURES):
    import record_review
    fixtures = []
    for path in paths:
        level = record_review.level_of(json.loads(Path(path).read_text())['events'])

        def on_decision(index, controller, position, context, recorded, path=path, level=level):
            fixtures.append(dict(match=Path(path).stem, index=index, level=level,
                                 state=payload(position), context=asdict(context)))
        try:
            record_review.rebuild(path, on_decision)
        except Exception as error:  # a replay that diverges keeps the decisions before it
            print('%s: stopped (%s)' % (Path(path).stem, str(error)[:80]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixtures))
    return fixtures


BENCH_JS = '''
var fixtures=JSON.parse(require("fs").readFileSync(process.argv[2],"utf8")), reps=+process.argv[3];
var outputs=[], times=[], nodes=0;
for(var f of fixtures){
    var best=Infinity, out=null;
    for(var r=0;r<reps;r++){
        var state=Object.assign(new GwaiV8Position(),f.state);
        var t=process.hrtime.bigint();
        out=GwaiV8Policy.choose(state,f.context,f.level);
        var ms=Number(process.hrtime.bigint()-t)/1e6; if(ms<best)best=ms;
    }
    outputs.push(out); times.push(best); nodes+=out.nodes||0;
}
console.log(JSON.stringify({outputs:outputs,times:times,nodes:nodes}));
'''


def run(fixtures=FIXTURES, reps=3, prof=None):
    from v8_as_test import core_javascript, script_file
    script = script_file(core_javascript() + BENCH_JS)
    cmd = ['node'] + (['--cpu-prof', '--cpu-prof-dir', str(prof)] if prof else []) + [script, str(fixtures), str(reps)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(done.stderr[-3000:])
    return json.loads(done.stdout)


def differences(base, new):
    """Indices of fixtures whose decision output changed (any field)."""
    return [i for i, (a, b) in enumerate(zip(base, new)) if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect'); c.add_argument('records', nargs='+')
    r = sub.add_parser('run'); r.add_argument('--reps', type=int, default=3)
    r.add_argument('--save'); r.add_argument('--compare'); r.add_argument('--prof')
    args = parser.parse_args(argv)
    if args.cmd == 'collect':
        print('fixtures', len(collect(args.records)), '->', FIXTURES)
        return
    result = run(reps=args.reps, prof=args.prof)
    times = sorted(result['times'])
    print('decisions %d  total %.0f ms  median %.1f ms  p90 %.1f ms  max %.1f ms  nodes %d' % (
        len(times), sum(times), times[len(times) // 2], times[int(len(times) * .9)], times[-1], result['nodes']))
    if args.save:
        Path(args.save).write_text(json.dumps(result))
    if args.compare:
        changed = differences(json.loads(Path(args.compare).read_text())['outputs'], result['outputs'])
        print('changed decisions:', changed if changed else 'none')
        if changed:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
