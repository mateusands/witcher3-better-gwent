#!/usr/bin/env python3
"""Local own/public decision trace for V7 and terminal-refinement loss analysis.

Never records opponent hand identities or composition. Inputs are existing local
fixtures; outputs remain private simulator diagnostics. Not a strength benchmark.
"""
import argparse,json,hashlib
from contextlib import nullcontext
from pathlib import Path
from dataclasses import asdict,replace
from time import perf_counter
from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.gwint.card_manager import CardManager
from gwentsim.position import Position
from gwentsim.rng import SeededRandom
from evaluate import engine_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--record',type=Path)
    source.add_argument('--npc-pair',type=int,help='fixed unchanged NPC pair from the five-faction study')
    parser.add_argument('--all-npcs',action='store_true',help='use the unchanged 51-collection NPC pair plan')
    parser.add_argument('--belief-prior',choices=['v7','semantic','scorch'],default='v7',help='candidate-only opponent-scenario seed experiment')
    parser.add_argument('--initial-exchanges',choices=['none','structural'],default='none')
    parser.add_argument('--decision-refinement',choices=['none','hero-pass','secured-resources','secured-continuation','round-transition','concession-eligibility','mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both'],default='none',help='explicit simulator-only candidate search hook')
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--seat',type=int,choices=[0,1],required=True)
    parser.add_argument('--swap',action='store_true')
    parser.add_argument('--profile',choices=['easy','medium','hard','expert'],default='hard')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--policy',choices=['response-v6','response-pass-v8','resource-v9'],default='response-v6')
    parser.add_argument('--opponent',choices=['vanilla','response-v6'],default='vanilla')
    parser.add_argument('--force-pass-round',type=int,choices=[0,1,2],help='diagnostic single-decision intervention, not a policy')
    parser.add_argument('--force-pass-template',type=int,help='optional own card template filter, avoids search-retry ambiguity')
    parser.add_argument('--force-pass-turn',type=int,default=0,help='zero-based own search invocation within selected round; retries may precede one applied move')
    args=parser.parse_args()
    if args.decision_refinement in ('round-transition','mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both') and args.force_pass_round is not None:
        parser.error('trace the phase correction and forced intervention separately')
    if args.force_pass_template is not None and args.force_pass_round is None:parser.error('template filter requires --force-pass-round')
    if args.record:
        match=load_match(args.record);decks=match.decks;source_name=args.record.name
    else:
        from evaluate_npc_policies import setup
        data=setup(all_npcs=args.all_npcs)
        if not 0<=args.npc_pair<len(data['pairs']):parser.error('NPC pair index out of range')
        match=data['match'];pair=data['pairs'][args.npc_pair]
        decks=[d.for_player(i) for i,d in enumerate(reversed(pair) if args.swap else pair)]
        source_name=f'native-npc-pair-{args.npc_pair}'
    if args.record and args.swap:decks=list(reversed(decks))
    observations=[];hashes=engine_hashes()
    from gwentsim import response_search
    original_hypotheses=response_search.hypotheses
    if args.belief_prior=='semantic':
        from public_belief_prior import semantic_hypotheses
        def selected_hypotheses(position,context,samples=4):
            return semantic_hypotheses(position,context,samples) if position.player==args.seat else original_hypotheses(position,context,samples)
        response_search.hypotheses=selected_hypotheses
    elif args.belief_prior=='scorch':
        from scorch_belief import scorch_hypotheses
        def selected_hypotheses(position,context,samples=4):
            return scorch_hypotheses(position,context,samples) if position.player==args.seat else original_hypotheses(position,context,samples)
        response_search.hypotheses=selected_hypotheses
    interventions=[];phase_context=nullcontext()
    if args.decision_refinement=='round-transition':
        if args.policy!='response-v6':parser.error('phase diagnostic requires V7')
        from evaluate_round_transition import transition_hook
        phase_context=transition_hook(args.seat,interventions)
    elif args.decision_refinement in ('mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both'):
        if args.policy!='response-v6':parser.error('projection diagnostic requires V7')
        from mushroom_policy import mushroom_hook
        if args.decision_refinement=='mushroom-reserve':
            from mushroom_reserve import mushroom_reserve_hook
            phase_context=mushroom_reserve_hook(args.seat,interventions)
        elif args.decision_refinement in ('mushroom-own','mushroom-opponent','mushroom-both'):
            from mushroom_role import mushroom_roles_hook
            role=args.decision_refinement.removeprefix('mushroom-')
            phase_context=mushroom_roles_hook({args.seat:role},{args.seat:interventions})
        else:
            phase_context=mushroom_hook(args.seat,interventions)
    if args.decision_refinement not in ('none','round-transition','mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both'):
        if args.policy!='response-v6':parser.error('resource diagnostic requires V7')
        from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
        if args.decision_refinement=='hero-pass':
            from hero_pass_refinement import refine_hero_pass as refiner
        elif args.decision_refinement=='concession-eligibility':
            from concession_eligibility import refine_concession_eligibility as refiner
        elif args.decision_refinement=='secured-continuation':
            from secured_resource_continuation import refine_secured_continuation
            profile=['easy','medium','hard','expert'].index(args.profile)
            refiner=lambda position,context,result:refine_secured_continuation(position,context,result,profile)
        else:
            from secured_resource_search import refine_secured_resources
            profile=['easy','medium','hard','expert'].index(args.profile)
            refiner=lambda position,context,result:refine_secured_resources(position,context,result,profile)
        initial_search=ResponseAIPlayerController.search
        refinement_base_search=initial_search
        def refined_search(controller,position,context):
            result=refinement_base_search(controller,position,context)
            if controller.playerID!=args.seat:return result
            corrected=refiner(position,context,result)
            if corrected is not result:interventions.append(dict(kind=args.decision_refinement,context=asdict(context),reference=result.audit(),candidate=corrected.audit()))
            return corrected
        ResponseAIPlayerController.search=refined_search
    if args.force_pass_round is not None:
        if args.policy!='response-v6':parser.error('diagnostic pass intervention requires V7')
        from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
        if args.decision_refinement=='none':initial_search=ResponseAIPlayerController.search
        intervention_base_search=ResponseAIPlayerController.search;turns={}
        def diagnostic_search(controller,position,context):
            result=intervention_base_search(controller,position,context)
            if controller.playerID!=args.seat:return result
            turn=turns.get(context.round_index,0);turns[context.round_index]=turn+1
            template_match=(result.action is not None and position.cards[result.action.source].template==args.force_pass_template)
            selected=template_match if args.force_pass_template is not None else turn==args.force_pass_turn
            if context.round_index==args.force_pass_round and selected:
                interventions.append(dict(kind='forced-pass',round=context.round_index,turn=turn,scores=position.scores(),sourceTemplate=args.force_pass_template,reference=result.audit()))
                return replace(result,action=None,reason='pass_for_match_resources')
            return result
        ResponseAIPlayerController.search=diagnostic_search
    policies=tuple(args.policy if s==args.seat else args.opponent for s in (0,1))
    def observe(event):
        if event['k']!='A' or event['player']!=args.seat:return
        cm=CardManager.getInstance();position=Position.from_manager(cm,args.seat)
        # Copy only observer-owned hand/counts and public row/grave identities.
        observations.append(dict(decision=event,scores=position.scores(),
            nativeCachedScores=list(cm.currentPlayerScores),
            nativeComputedScores=[sum(cm.calculatePlayerScore(row,side) for row in (5,4,3)) for side in (0,1)],
            cardPowerDifferences=[dict(key=k,template=position.cards[k].template,modeled=position.power(k),native=cm.getCardInstance(k).getTotalPower())
                for (side,row),keys in position.board.items() if side in (0,1) and row in (5,4,3) for k in keys
                if position.power(k)!=cm.getCardInstance(k).getTotalPower()],
            ownHand=[asdict(position.cards[k]) for k in position.hand],ownCounts=position.counts,
            publicBoard=[dict(side=side,row=row,cards=[asdict(position.cards[k]) for k in keys])
                for (side,row),keys in position.board.items()],
            publicGraves={str(s):[asdict(position.cards[k]) for k in position.grave[s]] for s in (0,1)}))
    exchanges=[];exchange_context=nullcontext();original_selector=None
    if args.initial_exchanges=='structural':
        import evaluate_mulligan as harness
        from structural_mulligan import choose_structural_mulligan
        original_selector=harness.choose_mulligan;harness.choose_mulligan=choose_structural_mulligan
        exchange_context=harness.exchange_hook(args.seat,'evaluated',args.seed,exchanges)
    refinement_paths=[Path(__file__)]
    if args.belief_prior=='semantic':refinement_paths.append(Path(__file__).with_name('public_belief_prior.py'))
    if args.belief_prior=='scorch':refinement_paths.append(Path(__file__).with_name('scorch_belief.py'))
    if args.decision_refinement=='round-transition':
        refinement_paths.extend(Path(__file__).with_name(name) for name in ('evaluate_round_transition.py','round_transition_value.py','evaluate_secured_resources.py'))
    elif args.decision_refinement in ('mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both'):
        if args.decision_refinement=='mushroom-reserve':refinement_paths.append(Path(__file__).with_name('mushroom_reserve.py'))
        if args.decision_refinement in ('mushroom-own','mushroom-opponent','mushroom-both'):refinement_paths.append(Path(__file__).with_name('mushroom_role.py'))
        refinement_paths.extend(Path(__file__).with_name(name) for name in ('mushroom_policy.py','mushroom_position.py'))
    elif args.decision_refinement!='none':
        filename={'hero-pass':'hero_pass_refinement.py','secured-resources':'secured_resource_search.py',
                  'concession-eligibility':'concession_eligibility.py','secured-continuation':'secured_resource_continuation.py'}[args.decision_refinement]
        refinement_paths.append(Path(__file__).with_name(filename))
    refinement_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in refinement_paths}
    started=perf_counter()
    try:
        with exchange_context,phase_context:
            recorder,flow=run_match(match.templates.values(),decks,
                match.card_values,SeededRandom(args.seed),seat_policies=policies,
                candidate_profile=['easy','medium','hard','expert'].index(args.profile),
                coin_toss_choice=lambda:True,on_event=observe)
    finally:
        response_search.hypotheses=original_hypotheses
        if original_selector is not None:harness.choose_mulligan=original_selector
        if args.decision_refinement not in ('none','round-transition','mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both') or args.force_pass_round is not None:ResponseAIPlayerController.search=initial_search
    if args.decision_refinement in ('round-transition','mushroom-projection','mushroom-reserve','mushroom-own','mushroom-opponent','mushroom-both'):
        for row in interventions:row['kind']=args.decision_refinement
    audits=flow.playerControllers[args.seat].policy_decisions
    if len(audits)!=len(observations):raise RuntimeError('decision audit/trace alignment mismatch')
    for observed,audit in zip(observations,audits):observed['audit']=audit
    report=dict(record=source_name,seed=args.seed,seat=args.seat,swapped=args.swap,
        profile=args.profile,beliefPrior=args.belief_prior,policies=policies,winner=flow.gameWinner,observations=observations,
        initialExchanges=args.initial_exchanges,initialExchangeDecisions=exchanges,
        decisionRefinement=args.decision_refinement,forcedPassRound=args.force_pass_round,forcedPassTurn=args.force_pass_turn,forcedPassTemplate=args.force_pass_template,
        diagnosticInterventions=interventions,
        interventionScope=('Audited simulator-only resource refinement and any explicitly reported forced intervention; one-opponent diagnostic, not aggregate strength evidence'
            if args.decision_refinement!='none' else 'One forced own pass; causal comparison against this particular opponent, not strength evidence') if interventions else None,
        elapsedSeconds=perf_counter()-started,engineSourceSha256=hashes,
        sourceUnchangedDuringRun=engine_hashes()==hashes,
        refinementSourceSha256=refinement_hashes,refinementSourceUnchangedDuringRun=refinement_hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in refinement_paths},
        rounds=[dict(scores=[r.getPlayerScore(0),r.getPlayerScore(1)],winner=r.winningPlayer)
            for r in flow.cardManager.roundResults if r.played])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('winner','rounds','elapsedSeconds','sourceUnchangedDuringRun')}))
    return int(not report['sourceUnchangedDuringRun'])


if __name__=='__main__':raise SystemExit(main())
