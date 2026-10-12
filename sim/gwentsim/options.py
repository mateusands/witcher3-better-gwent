"""Settings contract and provisional planning budgets, separate from vanilla rules.

The budgets are connected to an experimental local sequence search. Production
integration, mistake injection and measured difficulty progression remain pending.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping


class Difficulty(IntEnum):
    EASY = 0
    MEDIUM = 1
    HARD = 2
    EXPERT = 3


@dataclass(frozen=True)
class Profile:
    difficulty: Difficulty
    label: str
    search_depth: int
    beam_width: int
    mistake_probability: float
    status: str = 'provisional local search; strength and production unvalidated'


PROFILES = {
    Difficulty.EASY: Profile(Difficulty.EASY, 'Easy', 1, 4, 0.15),
    # The mod has three levels since 0.9.0 (Lab ladder: 512/768/2,048 nodes give 52.9/57.6/59.5%;
    # more nodes add nothing). Hard uses the former Medium search with 2,048 nodes; EXPERT is
    # kept for the simulator only.
    Difficulty.MEDIUM: Profile(Difficulty.MEDIUM, 'Normal', 2, 8, 0.05),
    Difficulty.HARD: Profile(Difficulty.HARD, 'Hard', 2, 8, 0.0),
    Difficulty.EXPERT: Profile(Difficulty.EXPERT, 'Expert', 3, 16, 0.0),
}


@dataclass(frozen=True)
class MatchOptions:
    """Capture once when a match starts; later menu edits cannot mutate it."""
    enabled: bool = False
    difficulty: Difficulty = Difficulty.HARD
    autoplay: bool = False

    @property
    def requested_profile(self):
        return PROFILES[self.difficulty] if self.enabled else None

    @property
    def autoplay_active(self):
        return self.enabled and self.autoplay

    @property
    def requested_player_profile(self):
        return self.requested_profile if self.autoplay_active else None

    @property
    def autoplay_control_enabled(self):
        return self.enabled

    @property
    def difficulty_control_enabled(self):
        return self.enabled


def normalize_settings(raw: Mapping[str, str]):
    """Return an immutable snapshot and only the writes needed in the GwentAI group.

    Native difficulty settings and unrelated keys are never touched. Off is the
    implementation fallback for an absent/invalid switch; Hard for difficulty.
    """
    enabled = raw.get('GwaiEnabled') in ('true', '1')
    value = raw.get('GwaiDifficulty')
    difficulty = Difficulty(int(value)) if value in ('0', '1', '2', '3') else Difficulty.HARD
    autoplay = raw.get('GwaiAutoPlay') in ('true', '1')
    normalized = {
        'GwaiEnabled': 'true' if enabled else 'false',
        'GwaiDifficulty': str(int(difficulty)),
        'GwaiAutoPlay': 'true' if autoplay else 'false',
    }
    writes = {key: value for key, value in normalized.items() if raw.get(key) != value}
    return MatchOptions(enabled=enabled, difficulty=difficulty, autoplay=autoplay), writes
