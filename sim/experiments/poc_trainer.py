"""Trainer and Offline Evaluator for Gwent AI PoC.

Trains:
1. Baseline Reference Model: 5 features (gap, hands, round, round wins)
2. Full Afterstate Model: all 25 features

Strict Group Partitioning:
- Partition by match_id: 70% Train, 15% Calibration, 15% Blind Test.
- No match_id appears in multiple sets.

Metrics:
- Log-Loss / Binary Cross-Entropy
- Brier Score
- Accuracy
- Platt Scaling Probability Calibration (ECE)
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np
import scipy.optimize as opt

ROOT = Path(__file__).resolve().parents[2]


def sigmoid(z):
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def log_loss(y_true, y_prob):
    eps = 1e-15
    p = np.clip(y_prob, eps, 1.0 - eps)
    return -float(np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))


def brier_score(y_true, y_prob):
    return float(np.mean((y_prob - y_true) ** 2))


def accuracy(y_true, y_prob):
    preds = (y_prob >= 0.5).astype(float)
    return float(np.mean(preds == y_true))


def expected_calibration_error(y_true, y_prob, n_bins=10):
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total = len(y_true)
    for i in range(n_bins):
        mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])
        if i == n_bins - 1:
            mask = mask | (y_prob == 1.0)
        bin_size = np.sum(mask)
        if bin_size > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(y_prob[mask])
            ece += (bin_size / total) * abs(bin_acc - bin_conf)
    return float(ece)


class LogisticModel:
    def __init__(self, l2_reg=1.0):
        self.l2_reg = l2_reg
        self.weights = None
        self.bias = 0.0
        self.calib_a = 1.0
        self.calib_b = 0.0

    def fit(self, X, y):
        n_samples, n_features = X.shape

        def loss_and_grad(params):
            w = params[:-1]
            b = params[-1]
            logits = np.dot(X, w) + b
            p = sigmoid(logits)
            eps = 1e-15
            p_clip = np.clip(p, eps, 1.0 - eps)
            loss = -np.mean(y * np.log(p_clip) + (1.0 - y) * np.log(1.0 - p_clip))
            loss += 0.5 * self.l2_reg * np.sum(w ** 2)

            diff = (p - y) / n_samples
            grad_w = np.dot(X.T, diff) + self.l2_reg * w
            grad_b = np.sum(diff)
            grad = np.append(grad_w, grad_b)
            return loss, grad

        init_params = np.zeros(n_features + 1)
        res = opt.minimize(loss_and_grad, init_params, jac=True, method='L-BFGS-B',
                           options={'maxiter': 500, 'ftol': 1e-9})
        self.weights = res.x[:-1]
        self.bias = float(res.x[-1])

    def predict_logits(self, X):
        return np.dot(X, self.weights) + self.bias

    def predict_proba(self, X, calibrated=False):
        logits = self.predict_logits(X)
        if calibrated:
            logits = logits * self.calib_a + self.calib_b
        return sigmoid(logits)

    def calibrate(self, X_val, y_val):
        """Fit Platt scaling (1D logistic regression over logits)."""
        logits = self.predict_logits(X_val)

        def calib_loss(params):
            a, b = params
            p = sigmoid(logits * a + b)
            eps = 1e-15
            p_clip = np.clip(p, eps, 1.0 - eps)
            return -np.mean(y_val * np.log(p_clip) + (1.0 - y_val) * np.log(1.0 - p_clip))

        res = opt.minimize(calib_loss, [1.0, 0.0], method='L-BFGS-B')
        self.calib_a = float(res.x[0])
        self.calib_b = float(res.x[1])


def run_training_experiment(dataset_path: Path):
    with open(dataset_path, 'r') as f:
        data = json.load(f)

    samples = data['samples']
    feature_names = data['metadata']['feature_names']
    print(f"Loaded {len(samples)} samples from {len(set(s['match_id'] for s in samples))} matches.")

    # Filter binary win/loss targets
    filtered = [s for s in samples if s['won_match'] in (0.0, 1.0)]
    X_full = np.array([s['features'] for s in filtered], dtype=np.float64)
    y = np.array([s['won_match'] for s in filtered], dtype=np.float64)
    match_ids = np.array([s['match_id'] for s in filtered], dtype=np.int32)

    # 5 baseline features:
    # 0: score_gap
    # 8: own_hand_count
    # 9: opp_hand_count
    # 21: round_index
    # 22-23: rounds_won_diff
    rounds_diff = (X_full[:, 22] - X_full[:, 23]).reshape(-1, 1)
    X_baseline = np.hstack([
        X_full[:, [0, 8, 9, 21]],
        rounds_diff
    ])

    # Split by match_id
    unique_matches = np.unique(match_ids)
    rng = np.random.RandomState(42)
    shuffled = rng.permutation(unique_matches)

    n_matches = len(unique_matches)
    n_train = int(n_matches * 0.70)
    n_calib = int(n_matches * 0.15)

    train_matches = set(shuffled[:n_train])
    calib_matches = set(shuffled[n_train:n_train + n_calib])
    test_matches = set(shuffled[n_train + n_calib:])

    train_mask = np.isin(match_ids, list(train_matches))
    calib_mask = np.isin(match_ids, list(calib_matches))
    test_mask = np.isin(match_ids, list(test_matches))

    print(f"Data Split by Match:")
    print(f"  Train: {len(train_matches)} matches ({np.sum(train_mask)} samples)")
    print(f"  Calibration: {len(calib_matches)} matches ({np.sum(calib_mask)} samples)")
    print(f"  Test: {len(test_matches)} matches ({np.sum(test_mask)} samples)")

    # 1. Train Baseline Model
    baseline_model = LogisticModel(l2_reg=0.1)
    baseline_model.fit(X_baseline[train_mask], y[train_mask])
    baseline_model.calibrate(X_baseline[calib_mask], y[calib_mask])

    # 2. Train Full Afterstate Model
    full_model = LogisticModel(l2_reg=0.1)
    full_model.fit(X_full[train_mask], y[train_mask])
    full_model.calibrate(X_full[calib_mask], y[calib_mask])

    # Evaluate on Test Set
    y_test = y[test_mask]

    p_base_raw = baseline_model.predict_proba(X_baseline[test_mask], calibrated=False)
    p_base_cal = baseline_model.predict_proba(X_baseline[test_mask], calibrated=True)

    p_full_raw = full_model.predict_proba(X_full[test_mask], calibrated=False)
    p_full_cal = full_model.predict_proba(X_full[test_mask], calibrated=True)

    results = {
        'baseline_raw': {
            'log_loss': log_loss(y_test, p_base_raw),
            'brier_score': brier_score(y_test, p_base_raw),
            'accuracy': accuracy(y_test, p_base_raw),
            'ece': expected_calibration_error(y_test, p_base_raw),
        },
        'baseline_calibrated': {
            'log_loss': log_loss(y_test, p_base_cal),
            'brier_score': brier_score(y_test, p_base_cal),
            'accuracy': accuracy(y_test, p_base_cal),
            'ece': expected_calibration_error(y_test, p_base_cal),
        },
        'full_model_raw': {
            'log_loss': log_loss(y_test, p_full_raw),
            'brier_score': brier_score(y_test, p_full_raw),
            'accuracy': accuracy(y_test, p_full_raw),
            'ece': expected_calibration_error(y_test, p_full_raw),
        },
        'full_model_calibrated': {
            'log_loss': log_loss(y_test, p_full_cal),
            'brier_score': brier_score(y_test, p_full_cal),
            'accuracy': accuracy(y_test, p_full_cal),
            'ece': expected_calibration_error(y_test, p_full_cal),
        },
    }

    print("\n" + "=" * 60)
    print("OFFLINE EVALUATION RESULTS ON BLIND TEST SET (15 matches)")
    print("=" * 60)
    print(f"{'Metric':<20} | {'Baseline (5 feat)':<18} | {'Full Model (25 feat)':<18} | {'Delta':<10}")
    print("-" * 72)
    for m in ['brier_score', 'log_loss', 'accuracy', 'ece']:
        b_val = results['baseline_calibrated'][m]
        f_val = results['full_model_calibrated'][m]
        delta = f_val - b_val
        print(f"{m:<20} | {b_val:<18.4f} | {f_val:<18.4f} | {delta:<+10.4f}")
    print("=" * 60)

    # Top Features
    weights = full_model.weights
    sorted_idx = np.argsort(np.abs(weights))[::-1]
    print("\nTop 10 Feature Weights in Full Model:")
    for rank, idx in enumerate(sorted_idx[:10], 1):
        print(f"  {rank:2d}. {feature_names[idx]:<24}: {weights[idx]:+.4f}")

    # Export Weights
    export_data = {
        'feature_names': feature_names,
        'weights': full_model.weights.tolist(),
        'bias': full_model.bias,
        'calib_a': full_model.calib_a,
        'calib_b': full_model.calib_b,
        'test_metrics': results,
    }
    weights_path = ROOT / 'sim/gwentsim/learned_evaluator_weights.json'
    weights_path.write_text(json.dumps(export_data, indent=2))
    print(f"\nSaved learned weights to {weights_path}")

    return export_data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train and evaluate PoC model")
    parser.add_argument('--dataset', type=Path, default=ROOT / 'game/evaluations/poc_mini_100/dataset.json')
    args = parser.parse_args()

    run_training_experiment(args.dataset)
