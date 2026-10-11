// Settings integration source. Not installed or compiled in the game yet.
// The switch captures intent only; improved AI dispatch is a separate integration step.
function GwaiSettingsInitialize() : void
{
    var cfg : CInGameConfigWrapper = theGame.GetInGameConfigWrapper();
    var enabled : string = cfg.GetRawConfigValueByStr("GwentAI", "GwaiEnabled");
    var difficulty : string = cfg.GetRawConfigValueByStr("GwentAI", "GwaiDifficulty");
    var autoplay : string = cfg.GetRawConfigValueByStr("GwentAI", "GwaiAutoPlay");
    var maxBet : string = cfg.GetRawConfigValueByStr("GwentAI", "GwaiMaxBet");
    var stakesStronger : string = cfg.GetRawConfigValueByStr("GwentAI", "GwaiStakesStronger");
    var normalized : string;
    var changed : bool;

    // Off is a conservative fallback for missing/invalid switch values.
    normalized = "false";
    if (enabled == "true" || enabled == "1")
    {
        normalized = "true";
    }
    if (enabled != normalized)
    {
        cfg.SetRawConfigValueByStr("GwentAI", "GwaiEnabled", normalized);
        changed = true;
    }
    if (difficulty != "0" && difficulty != "1" && difficulty != "2" && difficulty != "3")
    {
        cfg.SetRawConfigValueByStr("GwentAI", "GwaiDifficulty", "2");
        changed = true;
    }
    normalized = "false";
    if (autoplay == "true" || autoplay == "1")
    {
        normalized = "true";
    }
    if (autoplay != normalized)
    {
        cfg.SetRawConfigValueByStr("GwentAI", "GwaiAutoPlay", normalized);
        changed = true;
    }
    // Option index 0-4 (10/25/50/100/150). Legacy stake values are migrated to their index.
    normalized = maxBet;
    if (maxBet == "10") { normalized = "0"; }
    if (maxBet == "25") { normalized = "1"; }
    if (maxBet == "50") { normalized = "2"; }
    if (maxBet == "100") { normalized = "3"; }
    if (maxBet == "150") { normalized = "4"; }
    if (normalized != "0" && normalized != "1" && normalized != "2" && normalized != "3" && normalized != "4")
    {
        normalized = "0";
    }
    if (maxBet != normalized)
    {
        cfg.SetRawConfigValueByStr("GwentAI", "GwaiMaxBet", normalized);
        changed = true;
    }
    normalized = "false";
    if (stakesStronger == "true" || stakesStronger == "1")
    {
        normalized = "true";
    }
    if (stakesStronger != normalized)
    {
        cfg.SetRawConfigValueByStr("GwentAI", "GwaiStakesStronger", normalized);
        changed = true;
    }
    if (changed)
    {
        theGame.SaveUserSettings();
    }
}

function GwaiSettingsEnabled() : bool
{
    var raw : string = theGame.GetInGameConfigWrapper().GetRawConfigValueByStr("GwentAI", "GwaiEnabled");
    return raw == "true" || raw == "1";
}

function GwaiSettingsDifficulty() : int
{
    var raw : string = theGame.GetInGameConfigWrapper().GetRawConfigValueByStr("GwentAI", "GwaiDifficulty");
    if (raw == "0" || raw == "1" || raw == "2" || raw == "3")
    {
        return StringToInt(raw, 2);
    }
    return 2;
}

// Effective value for a new match; the saved preference survives the main switch.
function GwaiSettingsAutoPlay() : bool
{
    var raw : string = theGame.GetInGameConfigWrapper().GetRawConfigValueByStr("GwentAI", "GwaiAutoPlay");
    return GwaiSettingsEnabled() && (raw == "true" || raw == "1");
}

@wrapMethod(CR4IngameMenu)
function OnConfigUI()
{
    // Initialize before the native menu reads its configuration groups.
    GwaiSettingsInitialize();
    wrappedMethod();
}

@wrapMethod(CR4IngameMenu)
function OnShowOptionSubmenu(actionType : int, menuTag : int, id : string) : void
{
    wrappedMethod(actionType, menuTag, id);
    // Refresh through the native disabled-state channel after submenu opening.
    GwaiSettingsRefreshControlLocks();
}

@addMethod(CR4IngameMenu)
function GwaiSettingsRefreshControlLocks() : void
{
    var dataObject : CScriptedFlashObject;
    var dataArray : CScriptedFlashArray;
    dataArray = m_flashValueStorage.CreateTempFlashArray();
    dataObject = m_flashValueStorage.CreateTempFlashObject();
    dataObject.SetMemberFlashUInt("tag", NameToFlashUInt('GwaiDifficulty'));
    dataObject.SetMemberFlashBool("disabled", !GwaiSettingsEnabled());
    dataArray.PushBackFlashObject(dataObject);
    dataObject = m_flashValueStorage.CreateTempFlashObject();
    dataObject.SetMemberFlashUInt("tag", NameToFlashUInt('GwaiAutoPlay'));
    dataObject.SetMemberFlashBool("disabled", !GwaiSettingsEnabled());
    dataArray.PushBackFlashObject(dataObject);
    // Wager options belong to Better AI too: Off locks them and the game behaves as shipped.
    dataObject = m_flashValueStorage.CreateTempFlashObject();
    dataObject.SetMemberFlashUInt("tag", NameToFlashUInt('GwaiMaxBet'));
    dataObject.SetMemberFlashBool("disabled", !GwaiSettingsEnabled());
    dataArray.PushBackFlashObject(dataObject);
    dataObject = m_flashValueStorage.CreateTempFlashObject();
    dataObject.SetMemberFlashUInt("tag", NameToFlashUInt('GwaiStakesStronger'));
    dataObject.SetMemberFlashBool("disabled", !GwaiSettingsEnabled());
    dataArray.PushBackFlashObject(dataObject);
    m_flashValueStorage.SetFlashArray("options.update_disabled", dataArray);
    theGame.GetGuiManager().ForceProcessFlashStorage();
}

@wrapMethod(CR4IngameMenu)
function OnOptionValueChanged(groupId : int, optionName : name, optionValue : string)
{
    wrappedMethod(groupId, optionName, optionValue);
    if (optionName == 'GwaiEnabled')
    {
        GwaiSettingsRefreshControlLocks();
    }
}

@addField(CR4GwintGameMenu) var gwaiAIEnabledForMatch : bool;
@addField(CR4GwintGameMenu) var gwaiAIDifficultyForMatch : int;
@addField(CR4GwintGameMenu) var gwaiAIAutoPlayForMatch : bool;

@wrapMethod(CR4GwintGameMenu)
function OnConfigUI()
{
    var packet : CScriptedFlashObject;
    GwaiSettingsInitialize();
    gwaiAIEnabledForMatch = GwaiSettingsEnabled();
    gwaiAIDifficultyForMatch = GwaiSettingsDifficulty();
    gwaiAIAutoPlayForMatch = GwaiSettingsAutoPlay();
    wrappedMethod();
    packet = m_flashValueStorage.CreateTempFlashObject();
    packet.SetMemberFlashInt("version", 1);
    packet.SetMemberFlashBool("enabled", gwaiAIEnabledForMatch);
    packet.SetMemberFlashInt("difficulty", gwaiAIDifficultyForMatch);
    packet.SetMemberFlashBool("autoplay", gwaiAIAutoPlayForMatch);
    m_flashValueStorage.SetFlashObject("gwai.match.settings", packet);
    // Native controller replacement and decision execution remain separate hooks.
    // No vanilla difficulty fact is read, replaced or written by this settings layer.
}
