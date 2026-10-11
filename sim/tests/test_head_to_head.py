"""Independent policy seats, not candidate-vs-native masquerading as a direct duel."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from gwentsim.data import load_match
from gwentsim.gwint.match import run_match
from gwentsim.gwint.ai_player_controller import AIPlayerController
from gwentsim.gwint.sequence_ai_controller import ResponseAIPlayerController
from gwentsim.rng import SeededRandom

ROOT=Path(__file__).resolve().parents[2]


def duel(policies):
    match=load_match(ROOT/'game/records/g101.json')
    return run_match(match.templates.values(),match.decks,match.card_values,SeededRandom(160),
        seat_policies=policies,coin_toss_choice=lambda:True)


def test_direct_duel_constructs_both_requested_controllers_and_repeats():
    # Zero gameplay batches here: this test checks the engine seam on two short
    # complete matches. No strength conclusion follows from this seed.
    a,flow=duel(('round-pass-v1','round-pass-v1'))
    b,repeated=duel(('round-pass-v1','round-pass-v1'))
    assert a.events==b.events and flow.gameWinner==repeated.gameWinner
    assert all(type(c).__name__=='PlanningAIPlayerController' for c in flow.playerControllers)


def test_dual_policy_seam_matches_existing_single_candidate_path():
    match=load_match(ROOT/'game/records/g101.json')
    a,flow=duel(('round-pass-v1','vanilla'))
    b,_=run_match(match.templates.values(),match.decks,match.card_values,SeededRandom(160),
        candidate_player=0,candidate_policy='round-pass-v1',coin_toss_choice=lambda:True)
    assert a.events==b.events and type(flow.playerControllers[1]) is AIPlayerController


def test_incompatible_or_unknown_duel_configuration_is_rejected():
    with pytest.raises(ValueError,match='seat_policies'):
        duel(('round-pass-v1','missing-policy'))
    with pytest.raises(ValueError,match='seat_policies'):
        run_match([],[],{},SeededRandom(1),candidate_player=0,seat_policies=('vanilla','vanilla'))
