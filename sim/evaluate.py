#!/usr/bin/env python3
"""Reproducible vanilla baseline and experimental pass-planner evaluation.

Strict validation is required by default. --exploratory permits explicitly
unvalidated smoke runs while runtime gaps are being investigated. The optional candidate is a simulator-only pass overlay; results do not establish
validated difficulty levels. Paired seeds preserve initial randomness, not the
random-call alignment after policies make different moves.
"""
import argparse
import glob
import hashlib
import json
from pathlib import Path

import replay
from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.gwint.headless import SimulationStall
from gwentsim.rng import SeededRandom

ROOT = Path(__file__).resolve().parents[1]


def validation():
    paths = sorted(glob.glob(str(ROOT / 'game/records/g[0-9][0-9][0-9].json')))
    failures = []
    for path in paths:
        _, _, divergence = replay.replay(path)
        if divergence is not None:
            failures.append(dict(record=Path(path).name, event=divergence.index, detail=divergence.detail))
    return dict(records=len(paths), exact=len(paths) - len(failures), failures=failures)


def trial(path, seed, swap=False, candidate_player=None, candidate_policy='round-pass-v1', candidate_profile=2):
    match = load_match(path)
    decks = list(reversed(match.decks)) if swap else match.decks
    random = SeededRandom(seed)
    recorder, flow = run_match(match.templates.values(), decks, match.card_values, random,
                               coin_toss_choice=lambda: True, candidate_player=candidate_player, candidate_policy=candidate_policy, candidate_profile=candidate_profile)
    digest = hashlib.sha256(json.dumps(recorder.events, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    result = dict(record=Path(path).name, seed=seed, swapped=swap, winner=flow.gameWinner,
                decks=[{'name': deck.deck_name, 'leader': deck.selected_king_index,
                        'faction': match.templates[deck.selected_king_index].faction} for deck in decks],
                sourceSha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                rounds=[{'scores': [r.getPlayerScore(0), r.getPlayerScore(1)], 'winner': r.winningPlayer}
                        for r in flow.cardManager.roundResults if r.played],
                roundResources=[{'roundIndex': int(ev['tag'][2:]),
                    'hands': [len(p['hand']) for p in ev['players']]}
                    for ev in recorder.events if ev['k'] == 'S' and ev['tag'].startswith('rr')],
                eventCount=len(recorder.events), randomCalls=len(random.log), eventSha256=digest)
    if candidate_player is not None:
        decisions = flow.playerControllers[candidate_player].policy_decisions
        result.update(candidatePlayer=candidate_player, policy=candidate_policy, candidateProfile=candidate_profile,
                      candidateWon=flow.gameWinner == candidate_player, policyDecisions=decisions,
                      changedDecisions=sum(d['changed'] for d in decisions))
    return result


def trial_group(task):
    # One (record, seed, swap) group: baseline plus each candidate seat. Runs in its
    # own process when --jobs > 1; engine singletons are per process.
    path, seed, swap, candidate, policy, profile = task
    try:
        trials = [trial(path, seed, swap)]
        if candidate:
            for seat in (0, 1):
                trials.append(trial(path, seed, swap, candidate_player=seat, candidate_policy=policy, candidate_profile=profile))
        return trials, None
    except (SimulationStall, RuntimeError) as exc:
        return [], dict(record=path, seed=seed, swapped=swap, detail=str(exc))


def engine_hashes():
    return {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT/'sim/gwentsim').rglob('*.py'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', nargs='+', default=[str(ROOT / 'game/records/g101.json')])
    parser.add_argument('--seeds', nargs='+', type=int, default=[0, 1, 2])
    parser.add_argument('--swap', action='store_true', help='also exchange the players decks')
    parser.add_argument('--policy', choices=['round-pass-v1', 'round-pass-horn-v2', 'tactical-v3', 'reserve-v4', 'sequence-v5','response-v6','response-v8'], default='round-pass-v1', help='experimental candidate variant, requires --candidate')
    parser.add_argument('--profile', choices=['easy','medium','hard','expert'], default='hard', help='local sequence-search budget; not a validated production difficulty')
    parser.add_argument('--candidate', action='store_true', help='compare pass planner in both seats against vanilla')
    parser.add_argument('--exploratory', action='store_true', help='allow unvalidated diagnostic runs')
    parser.add_argument('--output', required=True)
    parser.add_argument('--jobs', type=int, default=1, help='worker processes; results keep the serial order')
    args = parser.parse_args()
    if args.policy != 'round-pass-v1' and not args.candidate:
        parser.error('--policy requires --candidate')
    if args.profile != 'hard' and args.policy not in ('sequence-v5','response-v6','response-v8'):
        parser.error('--profile requires sequence-v5, response-v6 or response-v8')
    selected_profile=['easy','medium','hard','expert'].index(args.profile)
    code_hashes=engine_hashes()
    gate = validation()
    report = dict(schema=2, engineSourceSha256=code_hashes, purpose='pass-planner-vs-vanilla' if args.candidate else 'vanilla-vs-vanilla evaluation infrastructure',
                  status='blocked' if gate['failures'] and not args.exploratory else 'exploratory',
                  validation=gate, candidatePolicy=args.policy if args.candidate else None, difficultyProfilesImplemented=False, searchBudgetsConnected=args.policy in ('sequence-v5','response-v6','response-v8'), selectedSearchProfile=args.profile, trials=[], errors=[])
    if report['status'] != 'blocked':
        tasks = [(path, seed, swap, args.candidate, args.policy, selected_profile)
                 for path in args.records for seed in args.seeds
                 for swap in ([False, True] if args.swap else [False])]
        if args.jobs > 1:
            import multiprocessing
            with multiprocessing.get_context('fork').Pool(args.jobs) as pool:
                groups = pool.map(trial_group, tasks, chunksize=1)
        else:
            groups = map(trial_group, tasks)
        for trials, error in groups:
            report['trials'].extend(trials)
            if error:
                report['errors'].append(error)
    if args.candidate:
        candidates = [t for t in report['trials'] if 'candidatePlayer' in t]
        baselines = {(t['record'], t['seed'], t['swapped']): t for t in report['trials'] if 'candidatePlayer' not in t}
        paired = [t for t in candidates if (t['record'], t['seed'], t['swapped']) in baselines]
        report['candidateSummary'] = dict(matches=len(candidates), wins=sum(t['candidateWon'] for t in candidates),
            draws=sum(t['winner'] not in (0, 1) for t in candidates),
            baselineSeatWins=sum(baselines[t['record'], t['seed'], t['swapped']]['winner'] == t['candidatePlayer'] for t in paired),
            gains=sum(t['candidateWon'] and baselines[t['record'], t['seed'], t['swapped']]['winner'] != t['candidatePlayer'] for t in paired),
            regressions=sum(not t['candidateWon'] and baselines[t['record'], t['seed'], t['swapped']]['winner'] == t['candidatePlayer'] for t in paired),
            changedDecisions=sum(t['changedDecisions'] for t in candidates),
            searchOverrides=sum(bool(d.get('sequenceSearch',{}).get('changed')) for t in candidates for d in t['policyDecisions']),
            selectionOverrides=sum(bool(d.get('reserveEvaluation')) and d['reserveEvaluation']['changed'] and not d['override']
                for t in candidates for d in t['policyDecisions']),
            baselineSeatDraws=sum(baselines[t['record'],t['seed'],t['swapped']]['winner'] not in (0,1) for t in paired),
            scope='Exploratory paired initial seeds; correlated seats/decks, vanilla opponent only. No strength claim.')
        report['candidateSummary']['score']=report['candidateSummary']['wins']+0.5*report['candidateSummary']['draws']
        report['candidateSummary']['baselineSeatScore']=report['candidateSummary']['baselineSeatWins']+0.5*report['candidateSummary']['baselineSeatDraws']
    report['sourceUnchangedDuringRun']=engine_hashes()==code_hashes
    if not report['sourceUnchangedDuringRun']:report['status']='invalidated-source-changed-during-run'
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print('%s: %d trials, %d errors; vanilla replay %d/%d exact; %s' %
          (report['status'], len(report['trials']), len(report['errors']), gate['exact'], gate['records'], destination))
    return int(report['status'] == 'blocked' or bool(report['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
