// Original Better Gwent AI betting additions, researched from vanilla 5.01 only.
// Standard pure-gold Gwent wagers only. No replacement game files or reward tables.
function GwaiSettingsMaxBet() : int
{
    var raw : string;
    // Better AI Off means the original game, wagers included: the stored choice is kept
    // for when the mod is turned On again, but the vanilla maximum applies.
    if (!GwaiSettingsEnabled())
    {
        return 10;
    }
    raw = theGame.GetInGameConfigWrapper().GetRawConfigValueByStr("GwentAI", "GwaiMaxBet");
    // Menu OPTIONS store the option index 0-4 (ids follow the vanilla 0..n convention).
    // Older drafts stored the stake itself; both forms are accepted.
    if (raw == "1" || raw == "25") { return 25; }
    if (raw == "2" || raw == "50") { return 50; }
    if (raw == "3" || raw == "100") { return 100; }
    if (raw == "4" || raw == "150") { return 150; }
    return 10;
}

function GwaiSettingsStakesStronger() : bool
{
    var raw : string;
    if (!GwaiSettingsEnabled())
    {
        return false;
    }
    raw = theGame.GetInGameConfigWrapper().GetRawConfigValueByStr("GwentAI", "GwaiStakesStronger");
    return raw == "true" || raw == "1";
}

@addField(CR4HudModuleDialog) var gwaiStandardBetOpen : bool;
@addField(CR4HudModuleDialog) var gwaiBetMaximum : int;
@addField(CR4HudModuleDialog) var gwaiBetStronger : bool;
@addField(CR4HudModuleDialog) var gwaiBetToken : int;
@addField(BettingSliderData) var gwaiBetConfigured : bool;
@addField(BettingSliderData) var gwaiExtendedStandardBet : bool;
@addField(BettingSliderData) var gwaiOpeningToken : int;

@addMethod(CR4HudModuleDialog)
public function GwaiIsStandardGoldBet(rewardName : name) : bool
{
    var gwaiGoldReward : SReward;
    if (!isGwentMode || rewardName != 'generic_gwint_reward')
    {
        return false;
    }
    theGame.GetReward(rewardName, gwaiGoldReward);
    return gwaiGoldReward.gold == 10 && gwaiGoldReward.experience == 0 && gwaiGoldReward.items.Size() == 0 && gwaiGoldReward.achievement == 0 && gwaiGoldReward.level == 0;
}

@wrapMethod(CR4HudModuleDialog)
function OpenBetPopup(rewardName : name, overrideCurrent : int)
{
    GwaiSettingsInitialize();
    theGame.GetGwintManager().GwaiClearStakeContext();
    gwaiBetToken += 1;
    gwaiStandardBetOpen = GwaiIsStandardGoldBet(rewardName);
    gwaiBetMaximum = GwaiSettingsMaxBet();
    gwaiBetStronger = GwaiSettingsStakesStronger();
    wrappedMethod(rewardName, overrideCurrent);
}

@addMethod(CR4HudModuleDialog)
public function GwaiConfigureBetData(data : BettingSliderData) : void
{
    if (data.gwaiBetConfigured)
    {
        return;
    }
    data.gwaiBetConfigured = true;
    data.gwaiOpeningToken = gwaiBetToken;
    data.gwaiExtendedStandardBet = gwaiStandardBetOpen && isBet && GwaiIsStandardGoldBet(currentRewardName);
    if (data.gwaiExtendedStandardBet)
    {
        data.maxValue = Min(gwaiBetMaximum, thePlayer.GetMoney());
        // Native popup already computed its starting value from reward/percentage.
        data.currentValue = Max(1, Min(data.currentValue, data.maxValue));
    }
}

@wrapMethod(BettingSliderData)
function GetGFxData(parentFlashValueStorage : CScriptedFlashValueStorage) : CScriptedFlashObject
{
    if (dialogueRef)
    {
        dialogueRef.GwaiConfigureBetData(this);
    }
    return wrappedMethod(parentFlashValueStorage);
}

@addMethod(CR4HudModuleDialog)
public function GwaiCanAcceptStandardBet(value : int, token : int) : bool
{
    return token == gwaiBetToken && gwaiStandardBetOpen && isBet && GwaiIsStandardGoldBet(currentRewardName) && value >= 1 && value <= gwaiBetMaximum && value <= thePlayer.GetMoney();
}

@wrapMethod(BettingSliderData)
function OnUserFeedback(KeyCode : string) : void
{
    if (gwaiExtendedStandardBet && KeyCode == "enter-gamepad_A")
    {
        if (!dialogueRef || !dialogueRef.GwaiCanAcceptStandardBet(currentValue, gwaiOpeningToken))
        {
            return;
        }
    }
    wrappedMethod(KeyCode);
}

@wrapMethod(CR4HudModuleDialog)
function DialogueSliderDataPopupResult(value : float, optional isItemReward : bool)
{
    var stake : int;
    var capture : bool;
    var stronger : bool;
    var forwarded : float;
    stake = RoundF(value);
    capture = gwaiStandardBetOpen && isBet && GwaiCanAcceptStandardBet(stake, gwaiBetToken);
    stronger = gwaiBetStronger;
    forwarded = value;
    if (gwaiStandardBetOpen && isBet)
    {
        if (!capture)
        {
            return;
        }
        // Integer stake keeps the native 2x multiplier consistent with money removed.
        forwarded = (float)stake;
    }
    // The 5.01 compiler accepts exactly one wrappedMethod call per wrapper.
    wrappedMethod(forwarded, isItemReward);
    if (capture)
    {
        theGame.GetGwintManager().GwaiCaptureStake(stake, stronger);
        gwaiStandardBetOpen = false;
    }
}

@addField(CR4GwintManager) var gwaiStakeForMatch : int;
@addField(CR4GwintManager) var gwaiStakeStageForMatch : int;

@addMethod(CR4GwintManager)
public function GwaiClearStakeContext() : void
{
    gwaiStakeForMatch = 0;
    gwaiStakeStageForMatch = 0;
}

@addMethod(CR4GwintManager)
public function GwaiCaptureStake(stake : int, stronger : bool) : void
{
    GwaiClearStakeContext();
    gwaiStakeForMatch = stake;
    if (stronger && stake > 10)
    {
        gwaiStakeStageForMatch = 1;
        if (stake >= 50)
        {
            gwaiStakeStageForMatch = 2;
        }
        if (stake >= 100)
        {
            gwaiStakeStageForMatch = 3;
        }
    }
}

@wrapMethod(CR4GwintManager)
function GenerateDifficultyData()
{
    var modDifficulty : int;
    var balanceOffset : int;
    wrappedMethod();
    if (GwaiSettingsEnabled())
    {
        // Vanilla has three deck variants: Easy, Normal and Hard use variants 1, 2 and 3.
        modDifficulty = GwaiSettingsDifficulty();
        difficulty = Min(modDifficulty + 1, 3);
        balanceOffset = 0;
        if (difficulty == 1)
        {
            balanceOffset = 80;
        }
        if (difficulty == 3)
        {
            balanceOffset = -80;
        }
        // Replace all effective values, regardless of the saved vanilla fact.
        difficultybalance.Clear();
        difficultybalance.Resize(15);
        difficultybalance[0] = 145 + balanceOffset;
        difficultybalance[1] = 150 + balanceOffset;
        difficultybalance[2] = 155 + balanceOffset;
        difficultybalance[3] = 160 + balanceOffset;
        difficultybalance[4] = 165 + balanceOffset;
        difficultybalance[5] = 170 + balanceOffset;
        difficultybalance[6] = 175 + balanceOffset;
        difficultybalance[7] = 180 + balanceOffset;
        difficultybalance[8] = 185 + balanceOffset;
        difficultybalance[9] = 190 + balanceOffset;
        difficultybalance[10] = 205 + balanceOffset;
        difficultybalance[11] = 215 + balanceOffset;
        difficultybalance[12] = 220 + balanceOffset;
        difficultybalance[13] = 225 + balanceOffset;
        difficultybalance[14] = 230 + balanceOffset;
    }
    if (gwaiStakeStageForMatch > 0)
    {
        // Select existing vanilla variants only; never write gwent_difficulty facts.
        difficulty = Max(difficulty, 2);
        if (gwaiStakeStageForMatch >= 2)
        {
            difficulty = 3;
        }
        difficultybalance[14] = 230;
        if (difficulty == 3)
        {
            difficultybalance[14] = 150;
        }
    }
}

@wrapMethod(CR4GwintManager)
function GetDifficulty(diffIndex : int) : int
{
    if (GwaiSettingsEnabled())
    {
        // diffIndex is one-based. Guard both ends before touching the array.
        if (diffIndex < 1 || diffIndex > difficultybalance.Size())
        {
            return 0;
        }
        // Highest stronger-stakes stage: every existing extra card enters.
        if (gwaiStakeStageForMatch >= 3)
        {
            return 0;
        }
        // Vanilla inverts its size check, so levels 1-14 always return 0 and NPC extra
        // cards ignore the player's deck. With Better AI On the intended rule applies at
        // every level: an extra card enters only when the player's deck strength reaches
        // its requirement, so an early, weak player deck faces a matching NPC deck.
        return difficultybalance[diffIndex - 1];
    }
    if (gwaiStakeStageForMatch >= 3 && diffIndex == 15)
    {
        return 0;
    }
    // With Better AI Off, preserve vanilla and the independent betting option.
    return wrappedMethod(diffIndex);
}

@wrapMethod(CR4GwintGameMenu)
function OnClosingMenu()
{
    m_flashValueStorage.SetFlashBool("gwai.match.stop", true);
    theGame.GetGuiManager().ForceProcessFlashStorage();
    wrappedMethod();
    theGame.GetGwintManager().GwaiClearStakeContext();
}
