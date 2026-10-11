#!/usr/bin/env python3
"""Synthetic decision-quality audit, separate from complete-match strength tests.

Variations reproduce one horizon error class across rows and factions, not independent
real-game victories. Only own hand and public board enter either planner.
"""
import argparse,json
from pathlib import Path
from dataclasses import asdict
from gwentsim import constants as C
from gwentsim.gwint.card_manager import CardManager
from gwentsim.gwint.card_template import CardTemplate
from gwentsim.gwint.small import GwintCardValues
from gwentsim.position import Position
from gwentsim.options import Difficulty
from gwentsim.sequence_search import Context
from gwentsim.response_search import choose_response
from gwentsim.passed_refinement import choose_refinement
from evaluate import engine_hashes

FACTIONS=(C.FactionId_No_Mans_Land,C.FactionId_Nilfgaard,
    C.FactionId_Northern_Kingdom,C.FactionId_Scoiatael,C.FactionId_Skellige)
FLAGS={5:C.CardType_Melee,4:C.CardType_Ranged,3:C.CardType_Siege}


def scenario(row,powers):
    CardManager._instance=None;CardManager.lastInstanceID=0
    board=CardManager();board.cardValues=GwintCardValues()
    board.halfWeatherEnabled=lambda player:False
    def add(power,location,flags,effects=(),player=0):
        template=CardTemplate();template.index=len(board._cardTemplates)+1
        template.power=power;template.typeArray=flags
        template.effectFlags=list(effects);template.summonFlags=[]
        board._cardTemplates[template.index]=template
        card=board.spawnCardInstance(template.index,player,location)
        card.inList,card.listsPlayer=location,player
        board.getCardInstanceList(location,player).append(card)
    for power in powers:add(power,1,C.CardType_Creature|FLAGS[row])
    add(0,1,C.CardType_Row_Modifier|C.CardType_SeigeRangedMelee,(C.CardEffect_Horn,))
    add(2*sum(powers)-1,row,C.CardType_Creature|FLAGS[row],player=1)
    return Position.from_manager(board,0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    hashes=engine_hashes();cases=[]
    for faction in FACTIONS:
        for row in FLAGS:
            for powers in ((3,4,5),(4,5,6),(2,3,4),(5,6,7),(6,7,8)):
                state=scenario(row,powers);initial=state
                ctx=Context(2,1,1,True,0,faction,C.FactionId_No_Mans_Land)
                original=choose_response(state,ctx,Difficulty.EXPERT)
                refined=choose_refinement(state,ctx,Difficulty.EXPERT)
                actions=[]
                for _ in range(4):
                    decision=choose_refinement(state,ctx,Difficulty.EXPERT)
                    if decision.action is None:break
                    actions.append(asdict(decision.action));state=state.apply(decision.action)
                final=choose_refinement(state,ctx,Difficulty.EXPERT)
                cases.append(dict(faction=faction,row=row,powers=powers,
                    initialScores=initial.scores(),v7Value=original.value,
                    candidateValue=refined.value,witness=refined.winning_witness,
                    replannedActions=actions,finalScores=state.scores(),
                    finalPass=final.action is None and final.reason=='pass_for_match_resources',
                    inputUnchanged=initial.scores()==(0,2*sum(powers)-1) and len(initial.hand)==4))
    passed=all(c['v7Value']==0 and c['candidateValue']==1 and c['witness'] and
        c['finalScores'][0]>c['finalScores'][1] and c['finalPass'] and c['inputUnchanged'] for c in cases)
    report=dict(errorClass='Expert horizon misses a four-action deterministic finish',
        scope='75 correlated synthetic variations of one error class; not full matches or a win-rate estimate',
        cases=cases,allChecksPassed=passed,sourceUnchangedDuringRun=engine_hashes()==hashes,
        engineSourceSha256=hashes)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(cases=len(cases),allChecksPassed=passed,
        sourceUnchangedDuringRun=report['sourceUnchangedDuringRun'])))
    return int(not passed or not report['sourceUnchangedDuringRun'])


if __name__=='__main__':raise SystemExit(main())
