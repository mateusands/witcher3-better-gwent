"""Designer properties of the simulator-only pass overlay (asset independent)."""
import sys
from pathlib import Path
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gwentsim.round_policy import HandEstimate, RoundObservation, decide_pass


def scenario(**changes):
    base = RoundObservation(1, 0, 1, 29, 40, False, False, 7,
                            (HandEstimate(5, 5), HandEstimate(0, 0)))
    return replace(base, **changes)


def test_concede_unreachable_second_round_but_not_critical_round():
    assert decide_pass(scenario()).reason == 'no_estimated_catchup'
    assert not decide_pass(scenario(own_losses=1)).override
    # A tied previous round costs both players a life.
    assert not decide_pass(scenario(own_losses=1, opponent_losses=1)).override


def test_chase_cost_and_remaining_quality_not_a_fixed_card_reserve():
    hand = (HandEstimate(10, 10), HandEstimate(8, 8), HandEstimate(0, 0))
    state = scenario(hand=hand, score=25)
    assert decide_pass(state).reason == 'preserve_round_three'
    # Same count and gap, but one useful reserve makes the chase acceptable.
    better_reserve = (HandEstimate(10, 2), HandEstimate(8, 2), HandEstimate(5, 20))
    assert not decide_pass(replace(state, hand=better_reserve)).override


def test_cheap_two_zero_and_attainable_finish_after_opponent_passes():
    assert not decide_pass(scenario(score=38)).override
    hand = (HandEstimate(10, 10), HandEstimate(8, 8))
    assert not decide_pass(scenario(hand=hand, score=25, opponent_passed=True)).override


def test_pass_secured_round_and_respect_nilfgaard_tie_rule():
    assert decide_pass(scenario(score=41, opponent_passed=True)).override
    assert not decide_pass(scenario(score=40, opponent_passed=True)).override
    assert decide_pass(scenario(score=40, opponent_passed=True, wins_ties=True)).override


def test_resource_moves_leader_and_round_one_not_conceded_by_overlay():
    for changes in ({'resource_action': True}, {'leader_available': True}, {'round_index': 0}):
        assert not decide_pass(scenario(**changes)).override


def test_resource_building_can_continue_after_a_secured_round_but_not_match():
    state = scenario(score=41, opponent_passed=True, opponent_losses=0, resource_action=True)
    assert not decide_pass(state).override
    assert decide_pass(replace(state, opponent_losses=1)).override


def test_zero_base_power_specials_are_not_assumed_worthless_next_round():
    assert not decide_pass(scenario(hand=(HandEstimate(0, 0),))).override


def test_g113_observed_late_round_state_preserves_griffin():
    # Event 147: ahead 1-0 in rounds, behind 24-34 in points; Horn, Fog,
    # Griffin remain. The native cached gains are 0, 0, 5 respectively.
    state = scenario(score=24, opponent_score=34, opponent_hand_count=8,
                     hand=(HandEstimate(0, 0), HandEstimate(0, 0), HandEstimate(5, 5)))
    assert decide_pass(state).override
    assert not decide_pass(replace(state, own_losses=1)).override
