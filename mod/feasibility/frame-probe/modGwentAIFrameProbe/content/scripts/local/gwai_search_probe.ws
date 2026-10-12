// Original offline feasibility event. Not installed or engine-compiled.
// Reports the dummy AS3 probe in its own user-config group; no save facts.
@addMethod(CR4GwintGameMenu)
event OnGwaiSearchProbe(iterations : int, elapsedMs : int, frames : int, maxBatchMs : int, checksum : int, rate : int)
{
    var cfg : CInGameConfigWrapper = theGame.GetInGameConfigWrapper();
    cfg.SetRawConfigValueByStr("GwaiSearchProbe", "iterations", IntToString(iterations));
    cfg.SetRawConfigValueByStr("GwaiSearchProbe", "elapsedMs", IntToString(elapsedMs));
    cfg.SetRawConfigValueByStr("GwaiSearchProbe", "frames", IntToString(frames));
    cfg.SetRawConfigValueByStr("GwaiSearchProbe", "maxBatchMs", IntToString(maxBatchMs));
    cfg.SetRawConfigValueByStr("GwaiSearchProbe", "checksum", IntToString(checksum));
    cfg.SetRawConfigValueByStr("GwaiSearchProbe", "iterationsPerSecond", IntToString(rate));
    theGame.SaveUserSettings();
    theGame.GetGuiManager().ShowNotification("Better Gwent: frame probe metrics saved.");
}
