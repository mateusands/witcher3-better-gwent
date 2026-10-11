"""Designer safeguards for incomplete continuation evaluation in experimental V3."""
from dataclasses import replace

from test_round_policy import scenario
from gwentsim.round_policy import HandEstimate, decide_pass
from gwentsim.gwint.tactical_ai_controller import TacticalPlanningAIPlayerController


def planner(extra=0, complete=True):
    policy = TacticalPlanningAIPlayerController.__new__(TacticalPlanningAIPlayerController)
    policy.combo_extra, policy.combo_coverage_complete = extra, complete
    return policy


def test_possible_unit_horn_sequence_prevents_false_unreachable_concession():
    state = scenario(score=0, opponent_score=12, hand=(HandEstimate(8, 8), HandEstimate(0, 0)))
    assert decide_pass(state).override
    assert not planner(extra=8).decide_round_pass(state).override


def test_unknown_recovery_or_muster_continuation_defers_concession():
    state = scenario()
    assert not planner(complete=False).decide_round_pass(state).override
    assert planner().decide_round_pass(state).override


def test_chase_cost_alone_does_not_justify_concession():
    state = scenario(score=25, hand=(HandEstimate(10, 10), HandEstimate(8, 8)))
    assert decide_pass(state).override
    assert not planner().decide_round_pass(state).override
    assert not planner().decide_round_pass(replace(state, opponent_passed=True)).override


def test_g113_late_state_still_concedes_when_combination_cannot_catch():
    state = scenario(score=24, opponent_score=34, opponent_hand_count=8,
        hand=(HandEstimate(0, 0), HandEstimate(0, 0), HandEstimate(5, 5)))
    assert planner(extra=5).decide_round_pass(state).override
    assert not planner(extra=5).decide_round_pass(replace(state, own_losses=1)).override
