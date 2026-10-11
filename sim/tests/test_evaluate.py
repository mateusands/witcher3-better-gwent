"""Seeded evaluation infrastructure is repeatable and preserves deck provenance."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
from evaluate import trial


def test_seeded_trials_are_repeatable_and_swap_decks():
    path = ROOT / 'game/records/g101.json'
    original = trial(path, 0)
    repeated = trial(path, 0)
    assert original == repeated
    swapped = trial(path, 0, swap=True)
    assert swapped['decks'] == original['decks'][::-1]
    assert swapped['sourceSha256'] == original['sourceSha256']
    changed_seed = trial(path, 1)
    assert changed_seed['eventSha256'] != original['eventSha256']
    assert original['rounds'] and len(original['eventSha256']) == 64


def test_candidate_is_repeatable_in_both_seats_and_keeps_original_decks():
    path = ROOT / 'game/records/g113.json'
    baseline = trial(path, 3)
    for seat in (0, 1):
        result = trial(path, 3, candidate_player=seat)
        assert result == trial(path, 3, candidate_player=seat)
        assert result['decks'] == baseline['decks']
        assert result['sourceSha256'] == baseline['sourceSha256']
        assert result['policyDecisions']
        for decision in result['policyDecisions']:
            observation = decision['observation']
            assert 'opponent_hand' not in observation
            if decision['changed']:
                assert decision['override']
                assert not observation['own_losses'] or decision['reason'] == 'secured_round'


def test_horn_candidate_records_corrected_rows_and_repeats():
    path = ROOT / 'game/records/g113.json'
    result = trial(path, 0, candidate_player=0, candidate_policy='round-pass-horn-v2')
    assert result == trial(path, 0, candidate_player=0, candidate_policy='round-pass-horn-v2')
    assert result['decks'] == trial(path, 0)['decks']
    evaluations = [e for d in result['policyDecisions'] for e in d['hornEvaluations']]
    assert evaluations
    for evaluation in evaluations:
        options = evaluation['alternatives']
        if options:
            assert evaluation['correctedGain'] == max(o['gain'] for o in options)
            assert evaluation['correctedSlot'] in [o['modifier_slot'] for o in options]


def test_reserve_candidate_repeats_and_observes_only_own_cards():
    path = ROOT / 'game/records/g105.json'
    result = trial(path, 6, swap=True, candidate_player=1, candidate_policy='reserve-v4')
    assert result == trial(path, 6, swap=True, candidate_player=1, candidate_policy='reserve-v4')
    assert result['decks'] == trial(path, 6, swap=True)['decks']
    estimates = [d['reserveEvaluation'] for d in result['policyDecisions'] if d.get('reserveEvaluation')]
    assert estimates
    for decision in result['policyDecisions']:
        assert 'opponent_hand' not in decision['observation']
        if decision.get('reserveEvaluation'):
            assert all(value >= 0 for value in decision['reserveEvaluation']['marginals'].values())


def test_sequence_controller_repeats_profiles_and_preserves_deck_definitions():
    path=ROOT/'game/records/g113.json'
    baseline=trial(path,2)
    for profile in (0,1,2,3):
        result=trial(path,2,candidate_player=1,candidate_policy='sequence-v5',candidate_profile=profile)
        assert result==trial(path,2,candidate_player=1,candidate_policy='sequence-v5',candidate_profile=profile)
        assert result['decks']==baseline['decks']
        search=[d['sequenceSearch'] for d in result['policyDecisions'] if d.get('sequenceSearch')]
        assert search
        for entry in search:
            if 'nodes' in entry:
                assert entry['nodes']<=max(32,((1,2,2,3)[profile])*((4,8,12,16)[profile])*12)


def test_response_controller_repeats_and_preserves_original_decks():
    path=ROOT/'game/records/g101.json'
    result=trial(path,90,candidate_player=1,candidate_policy='response-v6')
    assert result==trial(path,90,candidate_player=1,candidate_policy='response-v6')
    assert result['decks']==trial(path,90)['decks']
    audits=[d['sequenceSearch'] for d in result['policyDecisions'] if d.get('sequenceSearch')]
    assert any(a.get('samples',0)>0 for a in audits)
    assert all(a.get('nodes',0)<=4096 for a in audits)
