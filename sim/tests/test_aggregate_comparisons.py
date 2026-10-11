"""Aggregation must refuse incomplete or incomparable strength evidence."""
import pytest
from test_compare_policies import rows
from aggregate_comparisons import aggregate


def report(pair='fixture'):
    trials=rows()+rows(True)
    for t in trials:t['pair']=pair
    return dict(status='exploratory',sourceUnchangedDuringRun=True,errors=[],profile='hard',
        comparisons='all',engineSourceSha256={'engine':'fixed'},
        validation={'records':22,'exact':21,'failures':[{'record':'g100.json','event':229}]},trials=trials)


def test_combines_only_disjoint_complete_pairs_and_preserves_failure():
    merged=aggregate([report('a'),report('b')],expected_records=2,expected_pool=0)
    assert len(merged['trials'])==28 and merged['summary']['direct']['matches']==8
    assert merged['validation']['exact']==21 and merged['validation']['failures']
    assert merged['summary']['pairedNativeOutcomes']=={'gains':0,'regressions':0,'equal':8}


def test_rejects_changed_or_different_sources_profiles_and_duplicates():
    for field,value in [('sourceUnchangedDuringRun',False),('errors',[{'detail':'failed'}]),
        ('engineSourceSha256',{'engine':'different'}),('profile','easy')]:
        changed=report('b');changed[field]=value
        with pytest.raises(ValueError):aggregate([report('a'),changed])
    with pytest.raises(ValueError,match='duplicate'):aggregate([report(),report()])


def test_rejects_partial_controller_group_missing_swap_and_coverage():
    incomplete=report();incomplete['trials'].pop()
    with pytest.raises(ValueError,match='controller'):aggregate([incomplete])
    unswapped=report();unswapped['trials']=[t for t in unswapped['trials'] if not t['swapped']]
    with pytest.raises(ValueError,match='exchange'):aggregate([unswapped])
    with pytest.raises(ValueError,match='coverage'):aggregate([report()],expected_records=22)
    with pytest.raises(ValueError,match='no comparison'):aggregate([])


def test_diagnostics_separates_seats_factions_and_search_limits():
    fixture=report()
    for trial in fixture['trials']:
        trial['leaders']=[11,22]
        trial['decisions']={'0':{'turns':2,'iterations':8,'exactIncomplete':1,'coverageCutoffs':1,'maxSearchSeconds':0.4},
                            '1':{'turns':3,'iterations':12,'exactComplete':1,'coverageCutoffs':2,'maxSearchSeconds':0.2}}
    result=aggregate([fixture])['diagnostics']
    assert set(result['directByISMCTSSeat'])=={'0','1'}
    assert set(result['directByISMCTSLeader'])=={'11','22'}
    assert sum(v['matches'] for v in result['directByISMCTSLeader'].values())==4
    cost=result['searchCost']['ismcts-v1']
    assert cost['decisions']==20 and cost['iterations']==80
    assert cost['coverageCutoffs']==12
    assert cost['exactIncomplete']==4 and cost['exactComplete']==4
    assert cost['maxDecisionSeconds']==0.4
    assert all(set(v)=={'ismcts-v1','response-v6'} for v in result['versusNativeByFaction'].values())


def test_rejects_candidate_or_input_changes_and_labels_refinement():
    changed=report('b');changed['candidate']='response-pass-v8'
    with pytest.raises(ValueError,match='candidate'):aggregate([report('a'),changed])
    changed=report();changed['inputDataUnchangedDuringRun']=False
    with pytest.raises(ValueError,match='input data'):aggregate([changed])
    refined=report();refined['candidate']='response-pass-v8'
    for trial in refined['trials']:trial['policies']=['response-pass-v8' if p=='ismcts-v1' else p for p in trial['policies']]
    merged=aggregate([refined])
    assert 'candidateScore' in merged['summary']['direct']
    assert 'directByCandidateLeader' in merged['diagnostics']


def test_stronger_faction_is_not_mistaken_for_a_policy_improvement():
    # Seat zero's deck wins every game for both policies. High faction win rate
    # must not imply that the candidate improved on V7 with that collection.
    result=aggregate([report()])['diagnostics']['pairedNative']
    assert result['byFaction']['1']['candidateScore']==2
    assert result['byFaction']['3']['candidateScore']==0
    assert all(b['netScoreDelta']==0 for b in result['byFaction'].values())
    assert result['meanPairedScoreDelta']==result['equalFactionMeanDelta']==0
    assert not result['allFiveFactionsCovered'] and result['matchedGames']==4


def test_paired_faction_delta_does_not_overweight_repeated_collections():
    a=report('a');b=report('b');c=report('c')
    for trial in a['trials']:
        if trial['kind']=='native' and 'ismcts-v1' in trial['policies']:
            trial['winner']=trial['policies'].index('ismcts-v1')
    # Repeat the already strong faction without adding any policy improvement.
    for trial in c['trials']:trial['factions']=[1,1]
    result=aggregate([a,b,c])['diagnostics']['pairedNative']
    assert result['byFaction']['3']['gains']==2
    assert result['byFaction']['1']['netScoreDelta']==0
    assert result['meanPairedScoreDelta']==pytest.approx(1/6)
    assert result['equalFactionMeanDelta']==0.25
    assert result['byPair']['record:a']['netScoreDelta']==2


def test_rejects_deck_changes_inside_an_otherwise_complete_controller_group():
    changed=report();changed['trials'][1]['factions']=[3,1]
    with pytest.raises(ValueError,match='deck metadata'):aggregate([changed])
