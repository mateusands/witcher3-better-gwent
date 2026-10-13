"""Sequential probability ratio test on paired match differences (as chess engines test patches).

Each matchup gives d = candidate score - base score, in [-1, 1], with the same deal and luck for
both. H0: mean d = mu0 (no gain); H1: mean d = mu1 (a real gain). The log-likelihood ratio uses the
normal approximation with the sample variance (Fishtest's normalised SPRT). The test accepts H1
above log((1 - beta) / alpha), H0 below log(beta / (1 - alpha)), and needs at least min_n matchups.
"""
import math

VARIANCE_FLOOR = 1e-4     # all-equal samples: a tiny variance instead of a division by zero


class Stats:
    """Running count, sum and sum of squares of paired differences."""

    def __init__(self, n=0, total=0.0, squares=0.0):
        self.n, self.total, self.squares = n, total, squares

    def add(self, d):
        self.n += 1
        self.total += d
        self.squares += d * d

    @property
    def mean(self):
        return self.total / self.n if self.n else 0.0

    @property
    def variance(self):
        if self.n < 2:
            return VARIANCE_FLOOR
        return max(VARIANCE_FLOOR, (self.squares - self.n * self.mean ** 2) / (self.n - 1))

    @property
    def z(self):
        return self.mean / math.sqrt(self.variance / self.n) if self.n else 0.0

    def as_dict(self):
        return dict(n=self.n, total=self.total, squares=self.squares)


def bounds(alpha, beta):
    return math.log(beta / (1 - alpha)), math.log((1 - beta) / alpha)


def llr(stats, mu0, mu1):
    return (mu1 - mu0) / stats.variance * (stats.total - stats.n * (mu0 + mu1) / 2)


def decide(stats, mu0, mu1, alpha, beta, min_n):
    """'H1' (a real gain), 'H0' (no gain), or None (keep playing)."""
    if stats.n < min_n:
        return None
    low, high = bounds(alpha, beta)
    value = llr(stats, mu0, mu1)
    if value >= high:
        return 'H1'
    if value <= low:
        return 'H0'
    return None
