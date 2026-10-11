"""Original betting arithmetic, isolation and captured-setting designer scenarios."""
import sys
from pathlib import Path
from dataclasses import replace
import struct

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gwentsim.betting import BettingSettings, Reward, AcceptedBet, open_popup, normalize_betting_settings


def test_defaults_and_settings_independent_of_main_ai():
    for enabled in ('true', 'false'):
        raw = dict(GwaiEnabled=enabled, GwaiDifficulty='3', gwent_difficulty='1')
        settings, writes = normalize_betting_settings(raw)
        assert settings == BettingSettings()
        assert writes == dict(GwaiMaxBet='0', GwaiStakesStronger='false')
        raw.update(writes)
        assert not normalize_betting_settings(raw)[1]
        assert raw['gwent_difficulty'] == '1'


def test_standard_initial_value_and_cap_respect_money_and_percentage():
    reward = Reward('generic_gwint_reward', 10)
    for maximum in (10, 25, 50, 100, 150):
        settings = BettingSettings(maximum)
        assert open_popup(reward, 1000, settings, True).initial == 10
        assert open_popup(reward, 1000, settings, True, 50).initial == 5
        poor = open_popup(reward, 3, settings, True)
        assert (poor.maximum, poor.initial) == (3, 3)
        assert not open_popup(reward, 0, settings, True).eligible


def test_special_and_non_gwent_rewards_stay_native_and_mixed_rewards_rejected():
    settings = BettingSettings(150, True)
    rewards = [Reward('high_price_gwint_reward', 100), Reward('cg700_generic_gwint_reward', 50, level=1),
               Reward('generic_gwint_reward', 10, experience=5), Reward('generic_gwint_reward', 10, item_count=1)]
    for reward in rewards:
        popup = open_popup(reward, 1000, settings, True)
        assert not popup.eligible and popup.maximum == reward.gold and popup.initial == reward.gold
        with pytest.raises(ValueError): popup.accept(100, 1000)
    ordinary = open_popup(Reward('generic_gwint_reward', 10), 1000, settings, False)
    assert not ordinary.eligible and ordinary.maximum == 10


def test_max_bet_reads_menu_index_and_migrates_legacy_stake():
    for index, stake in enumerate((10, 25, 50, 100, 150)):
        settings, writes = normalize_betting_settings(dict(GwaiMaxBet=str(index), GwaiStakesStronger='false'))
        assert settings.max_bet == stake and not writes
        settings, writes = normalize_betting_settings(dict(GwaiMaxBet=str(stake), GwaiStakesStronger='false'))
        assert settings.max_bet == stake and writes == dict(GwaiMaxBet=str(index))


def test_snapshot_survives_options_change_and_acceptance_rechecks_wallet():
    raw = dict(GwaiMaxBet='150', GwaiStakesStronger='true')
    settings, _ = normalize_betting_settings(raw)
    popup = open_popup(Reward('generic_gwint_reward', 10), 200, settings, True)
    raw.update(GwaiMaxBet='10', GwaiStakesStronger='false')
    assert popup.accept(150, 200).stage == 3
    for invalid in (0, 151, 100.5, True):
        with pytest.raises(ValueError): popup.accept(invalid, 200)
    with pytest.raises(ValueError): popup.accept(150, 149)
    with pytest.raises(ValueError): popup.accept(10, 200, gwent_mode=False)


def test_integer_wagers_have_exact_gross_payout_and_net_gain_or_loss():
    def f32(value): return struct.unpack('<f', struct.pack('<f', value))[0]
    for stake in range(1, 151):
        bet = AcceptedBet(stake, False)
        native_multiplier = f32(f32(stake / 10) * 2)
        rounded_gold = int(f32(native_multiplier * 10) + 0.5)
        assert rounded_gold == bet.win_payment == 2 * stake
        assert 1000 - stake + bet.win_payment == 1000 + stake
        assert 1000 - bet.loss == 1000 - stake


def test_stake_curve_uses_actual_wager_never_downgrades_and_preserves_low_levels():
    for stake, expected in ((10, 0), (11, 1), (49, 1), (50, 2), (99, 2), (100, 3), (150, 3)):
        bet = AcceptedBet(stake, True)
        assert bet.stage == expected
        for native in (1, 2, 3):
            assert bet.native_difficulty(native) >= native
            assert all(bet.dynamic_requirement(level, native) == 0 for level in range(1, 15))
    assert AcceptedBet(100, True).dynamic_requirement(15, 1) == 0
    assert AcceptedBet(50, True).dynamic_requirement(15, 1) == 150
    assert AcceptedBet(25, True).dynamic_requirement(15, 1) == 230
    assert AcceptedBet(150, False).native_difficulty(1) == 1
    assert AcceptedBet(150, False).dynamic_requirement(15, 1) == 310


def test_repaired_requirements_mirror_better_ai_on():
    from gwentsim.betting import REQUIREMENTS
    for variant, offset in ((1, 80), (2, 0), (3, -80)):
        bet = AcceptedBet(10, False)
        assert [bet.dynamic_requirement(level, variant, repaired=True) for level in range(1, 16)] == \
            [v + offset for v in REQUIREMENTS]
    assert all(AcceptedBet(100, True).dynamic_requirement(level, 1, repaired=True) == 0 for level in range(1, 16))
    assert AcceptedBet(50, True).dynamic_requirement(15, 1, repaired=True) == 150
    assert AcceptedBet(25, True).dynamic_requirement(15, 1, repaired=True) == 230
    assert AcceptedBet(25, True).dynamic_requirement(3, 1, repaired=True) == 155 + 80


def test_better_ai_off_restores_vanilla_wagers():
    from gwentsim.betting import effective_betting_settings
    settings, _ = normalize_betting_settings(dict(GwaiMaxBet='4', GwaiStakesStronger='true'))
    assert effective_betting_settings(settings, True) == settings
    off = effective_betting_settings(settings, False)
    assert off.max_bet == 10 and not off.stronger_opponent


def test_ws_wagers_follow_the_main_switch():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'mod/settings'
    betting = (root / 'modGwentAISettings/content/scripts/local/gwai_betting.ws').read_text()
    for name in ('GwaiSettingsMaxBet', 'GwaiSettingsStakesStronger'):
        body = betting[betting.index('function %s(' % name):]
        body = body[:body.index('\n}')]
        assert 'if (!GwaiSettingsEnabled())' in body
    locks = (root / 'modGwentAISettings/content/scripts/local/gwai_settings.ws').read_text()
    assert "NameToFlashUInt('GwaiMaxBet')" in locks and "NameToFlashUInt('GwaiStakesStronger')" in locks
