"""Texel-style tuning of the V8 utility weights (sim/texel_tune.py).

Given/When/Then specification. Kept light: four benchmark matches in total.
"""
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gwentsim import tuning  # noqa: E402
from gwentsim.tuning import DEFAULTS  # noqa: E402
from gwentsim.sequence_search import utility  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'
# Pair 2 has a Northern Kingdoms NPC: its own-draw term and spy draws are covered too.
MATCHES = ((0, 1401, False), (1, 1402, False), (2, 1402, False))


@pytest.fixture(scope='module')
def collected():
    """Three benchmark-scene matches, each NPC decision kept with the real position it evaluates."""
    import texel_tune
    samples, probes = [], []
    for pair, seed, swap in MATCHES:
        def probe(position, context, sample):
            probes.append((position, context, sample))
        samples += texel_tune.collect(pair, seed, swap, 'hard', 'balanced', SCENE, probe=probe)
    return samples, probes


def real_utility(position, context, sample, weights):
    """The AI's own leaf utility of the recorded position, computed on the real Position object."""
    saved = tuning.ACTIVE
    tuning.ACTIVE = dict(weights)
    try:
        return utility(position, context, sample['depth'], position.reserve(), sample['mean'],
                       passing=sample['passing'])
    finally:
        tuning.ACTIVE = saved


def test_collect_records_npc_decisions_with_match_result(collected):
    # Given three benchmark-scene matches, When they are collected,
    samples, probes = collected
    # Then every NPC decision gives a JSON-serialisable sample with the NPC's final result.
    assert samples and len(samples) == len(probes)
    assert all(s['result'] in (0, 0.5, 1) for s in samples)
    for pair, seed, swap in MATCHES:
        match = [s for s in samples if (s['pair'], s['seed'], s['swap']) == (pair, seed, swap)]
        assert match, (pair, seed)
        assert len({s['result'] for s in match}) == 1
        assert all(s['player'] == s['npcSeat'] for s in match)
    for s in samples:
        assert json.loads(json.dumps(s)) == s


def test_static_value_with_defaults_equals_the_ai_utility(collected):
    import texel_tune
    samples, probes = collected
    # Given the recorded samples, When valued statically with the shipped weights,
    # Then the value is the AI's own utility of that position.
    for position, context, sample in probes:
        assert texel_tune.static_value(sample, DEFAULTS) == pytest.approx(
            real_utility(position, context, sample, DEFAULTS), abs=1e-9)


def test_static_value_follows_the_ai_utility_under_other_weights(collected):
    import texel_tune
    _, probes = collected
    # Given other weights (every weight changed), When valued statically,
    # Then the value still equals the AI's utility under those weights.
    for factor in (0.5, 2.0):
        weights = {n: v * factor for n, v in DEFAULTS.items()}
        for position, context, sample in probes:
            assert texel_tune.static_value(sample, weights) == pytest.approx(
                real_utility(position, context, sample, weights), abs=1e-9)


def test_static_value_changes_with_a_weight_and_is_deterministic(collected):
    import texel_tune
    samples, _ = collected
    before = tuning.ACTIVE
    base = [texel_tune.static_value(s, DEFAULTS) for s in samples]
    # Given the same weights twice, Then the values are identical and ACTIVE is restored.
    assert base == [texel_tune.static_value(s, DEFAULTS) for s in samples]
    assert tuning.ACTIVE is before
    # When the reserve weight, the scale or the draw weight changes, Then some position changes value.
    for name in ('reserve_weight', 'scale_base', 'draw_weight'):
        changed = [texel_tune.static_value(s, dict(DEFAULTS, **{name: DEFAULTS[name] * 3})) for s in samples]
        assert any(abs(a - b) > 1e-9 for a, b in zip(base, changed)), name


def test_fit_k_is_no_worse_than_the_raw_utility(collected):
    import texel_tune
    samples, _ = collected
    # Given samples, When K is fitted, Then it is positive and no worse than K = 1 (raw utility).
    k = texel_tune.fit_k(samples)
    assert k > 0
    assert texel_tune.loss(samples, DEFAULTS, k) <= texel_tune.loss(samples, DEFAULTS, 1.0) + 1e-12


def test_tune_lowers_the_loss_and_keeps_bounds(collected):
    import texel_tune
    samples, _ = collected
    # Given samples labelled by a known weight vector (synthetic results),
    truth = dict(DEFAULTS, reserve_weight=DEFAULTS['reserve_weight'] * 3, scale_base=DEFAULTS['scale_base'] / 2)
    synthetic = [dict(s, result=1 if texel_tune.static_value(s, truth) > 0.5 else 0) for s in samples]
    k = texel_tune.fit_k(synthetic)
    start = texel_tune.loss(synthetic, DEFAULTS, k)
    # When tuned by coordinate descent,
    best, history = texel_tune.tune(synthetic, start=DEFAULTS, steps=6, k=k)
    # Then the loss never rises, ends no higher than at the start, and every weight stays in bounds.
    losses = [h['loss'] for h in history]
    assert losses[0] == pytest.approx(start)
    assert all(b <= a + 1e-12 for a, b in zip(losses, losses[1:]))
    assert texel_tune.loss(synthetic, best, k) <= start + 1e-12
    for name, value in best.items():
        assert 0.25 * DEFAULTS[name] - 1e-12 <= value <= 4.0 * DEFAULTS[name] + 1e-12


def test_tune_with_one_sided_results_stays_within_bounds(collected):
    import texel_tune
    samples, _ = collected
    # Given results that push every weight towards an extreme (every NPC position won),
    won = [dict(s, result=1) for s in samples]
    # When tuned, Then no weight leaves 0.25x .. 4x of its default.
    best, _ = texel_tune.tune(won, start=DEFAULTS, steps=8, k=1.0)
    for name, value in best.items():
        assert 0.25 * DEFAULTS[name] - 1e-12 <= value <= 4.0 * DEFAULTS[name] + 1e-12


def test_cli_collect_and_fit_write_valid_json(tmp_path):
    import texel_tune
    data = tmp_path / 'samples.jsonl'
    out = tmp_path / 'weights.json'
    # Given the CLI, When one match is collected and fitted,
    assert texel_tune.main(['collect', '--pairs', '1', '--seeds', '1403', '--swap', 'off', '--jobs', '1',
                            '--npc-decks', 'balanced', '--out', str(data)]) == 0
    lines = data.read_text().splitlines()
    # Then every line is a JSON sample, and the fit writes weights within bounds.
    assert lines and all(json.loads(line)['result'] in (0, 0.5, 1) for line in lines)
    assert texel_tune.main(['fit', '--data', str(data), '--out', str(out), '--steps', '3']) == 0
    report = json.loads(out.read_text())
    assert set(report['weights']) == set(DEFAULTS)
    assert report['samples'] == len(lines)
    assert math.isfinite(report['loss']['end']) and report['loss']['end'] <= report['loss']['start'] + 1e-12
    for name, value in report['weights'].items():
        assert 0.25 * DEFAULTS[name] - 1e-12 <= value <= 4.0 * DEFAULTS[name] + 1e-12
