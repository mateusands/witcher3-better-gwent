"""Original standard-wager contract, separate from AI settings and game rules."""
from dataclasses import dataclass

MAX_BETS = (10, 25, 50, 100, 150)
# Base dynamic-card requirements per level 1-15 (offset +80 Easy, -80 Hard deck variant).
REQUIREMENTS = (145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 205, 215, 220, 225, 230)
STANDARD_REWARD = 'generic_gwint_reward'


@dataclass(frozen=True)
class BettingSettings:
    max_bet: int = 10
    stronger_opponent: bool = False


@dataclass(frozen=True)
class Reward:
    name: str
    gold: int
    experience: int = 0
    item_count: int = 0
    achievement: int = 0
    level: int = 0

    @property
    def standard_pure_gold(self):
        return (self.name == STANDARD_REWARD and self.gold == 10 and
                not any((self.experience, self.item_count, self.achievement, self.level)))


@dataclass(frozen=True)
class BetPopup:
    eligible: bool
    minimum: int
    maximum: int
    initial: int
    settings: BettingSettings
    reward: Reward

    def accept(self, stake, wallet, gwent_mode=True):
        if not self.eligible or not gwent_mode or not self.reward.standard_pure_gold:
            raise ValueError('standard Gwent wager not active')
        if not isinstance(stake, int) or isinstance(stake, bool) or not 1 <= stake <= min(self.maximum, wallet):
            raise ValueError('stake outside captured limit or available money')
        return AcceptedBet(stake, self.settings.stronger_opponent)


@dataclass(frozen=True)
class AcceptedBet:
    stake: int
    stronger: bool

    @property
    def stage(self):
        if not self.stronger or self.stake <= 10:
            return 0
        return 3 if self.stake >= 100 else 2 if self.stake >= 50 else 1

    def native_difficulty(self, original):
        if original not in (1, 2, 3):
            raise ValueError('expected native Gwent difficulty 1/2/3')
        return max(original, 3 if self.stage >= 2 else 2 if self.stage else original)

    def dynamic_requirement(self, level, original_difficulty, repaired=False):
        """Requirement for a dynamic card level. repaired=True mirrors Better AI On, which
        applies the intended per-level requirements instead of the vanilla inverted check."""
        difficulty = self.native_difficulty(original_difficulty)
        if repaired:
            if self.stage == 3:
                return 0
            if level == 15 and self.stage:
                return 150 if difficulty == 3 else 230
            return REQUIREMENTS[level - 1] + {1: 80, 2: 0, 3: -80}[original_difficulty]
        if level != 15:
            return 0  # Preserve the observed 5.x native bug; do not repair silently.
        if self.stage == 3:
            return 0
        return 230 + {1: 80, 2: 0, 3: -80}[difficulty]

    @property
    def win_payment(self):
        return 2 * self.stake  # Gross payout; net gain is one stake.

    @property
    def loss(self):
        return self.stake


def normalize_betting_settings(raw):
    # Menu OPTIONS store the option index 0-4; legacy drafts stored the stake (migrated).
    text = raw.get('GwaiMaxBet')
    if text in tuple(map(str, MAX_BETS)):
        index = MAX_BETS.index(int(text))
    elif text in tuple(str(i) for i in range(len(MAX_BETS))):
        index = int(text)
    else:
        index = 0
    maximum = MAX_BETS[index]
    stronger = raw.get('GwaiStakesStronger') in ('true', '1')
    expected = dict(GwaiMaxBet=str(index), GwaiStakesStronger='true' if stronger else 'false')
    return BettingSettings(maximum, stronger), {k: v for k, v in expected.items() if raw.get(k) != v}


def open_popup(reward, wallet, settings, gwent_mode, override_percent=0):
    # Model original initial-value computation first. Special/non-Gwent wagers retain
    # their native limit and value; the mod's cap is applied only to the common reward.
    initial = max(1, min(reward.gold, wallet) * override_percent // 100) if override_percent > 0 else reward.gold
    eligible = gwent_mode and reward.standard_pure_gold and wallet > 0
    maximum = min(settings.max_bet, wallet) if eligible else reward.gold
    if eligible:
        initial = max(1, min(initial, maximum))
    return BetPopup(eligible, 1, maximum, initial, settings, reward)
