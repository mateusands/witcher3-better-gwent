"""Mandatory seat/deck pairing and honest two-gate summary calculations."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compare_policies import configurations,summarize,V7,ISMCTS


def rows(swapped=False,direct_winner=0):
    return [dict(source='record',pair='fixture',seed=162,swapped=swapped,kind=kind,
        policies=policies,winner=direct_winner if kind=='direct' else 0,factions=[1,3])
        for kind,policies in configurations('all')]


def test_direct_runs_each_controller_in_both_seats():
    direct=configurations('direct')
    assert direct==[('direct',(ISMCTS,V7)),('direct',(V7,ISMCTS))]
    assert len(configurations('all'))==7
    result=summarize(rows()+rows(True))
    assert result['direct']['matches']==4
    assert result['direct']['ismctsScore']==result['direct']['v7Score']==2
    assert result['versusNative'][ISMCTS]['matches']==4
    assert not result['sampleReplacementGate']


def test_direct_gain_alone_cannot_pass_native_gate():
    data=rows()+rows(True)
    for row in data:
        if row['kind']=='direct':row['winner']=row['policies'].index(ISMCTS)
    result=summarize(data)
    assert result['direct']['ismctsScore']==4 and not result['sampleReplacementGate']
    for row in data:
        if row['kind']=='native' and ISMCTS in row['policies']:row['winner']=row['policies'].index(ISMCTS)
    assert summarize(data)['sampleReplacementGate']
    assert not summarize([])['sampleReplacementGate']


def test_refinement_comparison_is_labeled_and_requires_both_gates():
    candidate='response-pass-v8'
    data=[dict(source='record',pair='fixture',seed=169,swapped=swap,kind=kind,
        policies=policies,winner=policies.index(candidate) if candidate in policies else 0,factions=[1,3])
        for swap in (False,True) for kind,policies in configurations('all',candidate)]
    result=summarize(data,candidate)
    assert result['direct']['candidateScore']==4 and result['sampleReplacementGate']
    assert candidate in result['versusNative'] and 'ismcts-v1' not in result['versusNative']
    assert 'directByCandidateFaction' in result and 'ismctsScore' not in result['direct']
