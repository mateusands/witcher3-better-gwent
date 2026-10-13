// Better Gwent: two Gwent glossary entries the game ships but never unlocks.
// - The special ability entry is asked for under a misspelled alias whose path names a file that
//   does not exist, so it never unlocks; its real file is loaded here by its depot path.
// - The leader cards entry is ready but nothing unlocks it; the deck builder unlocks it here, next
//   to the game's own deck builder entries.
// Both are the game's own entries: unlocking one only marks it as read in the glossary, as the base
// game does for the others. Only while Better Gwent is On.

function GwaiActivateJournalPath(path : string)
{
    var resource : CJournalResource;
    var entryBase : CJournalBase;

    resource = (CJournalResource)LoadResource(path, true);
    if (resource)
    {
        entryBase = resource.GetEntry();
        if (entryBase)
        {
            theGame.GetJournalManager().ActivateEntry(entryBase, JS_Active);
        }
    }
}

@wrapMethod(CR4GwintGameMenu)
function EnableJournalTutorialEnries()
{
    wrappedMethod();
    if (GwaiSettingsEnabled())
    {
        GwaiActivateJournalPath("gameplay\journal\tutorial\unitcardspecialabilitynew.journal");
    }
}

@wrapMethod(CR4DeckBuilderMenu)
function EnableJournalTutorialEnries()
{
    wrappedMethod();
    if (GwaiSettingsEnabled())
    {
        theGame.GetTutorialSystem().ActivateJournalEntry('leadercardsMERGED');
    }
}
