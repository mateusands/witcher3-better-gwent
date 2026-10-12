// NPC decks option (Original / Adaptive / Strong), Better AI On only.
// GetCurrentAIDeck returns a copy of the NPC deck for one match; with Adaptive or Strong the
// copy gets the cards chosen by sim/gwentsim/npc_balance.py (table in gwai_npc_decks_data.ws).
// No card, deck definition or save data is changed. The tutorial match keeps its native deck.

// 0 Original, 1 Adaptive, 2 Strong. Original while Better AI is Off.
function GwaiSettingsNpcDecks() : int
{
    var raw : string = theGame.GetInGameConfigWrapper().GetRawConfigValueByStr("GwentAI", "GwaiNpcDecks");
    if (!GwaiSettingsEnabled())
    {
        return 0;
    }
    if (raw == "1" || raw == "2")
    {
        return StringToInt(raw, 0);
    }
    return 0;
}

// The game's player-deck strength measure (unit power plus fixed bonuses by first effect),
// as in npc_balance.deck_strength.
function GwaiDeckStrength(cards : array<name>) : int
{
    var manager : CR4GwintManager = theGame.GetGwintManager();
    var card : SCardDefinition;
    var total, i, effect : int;
    for (i = 0; i < cards.Size(); i += 1)
    {
        if (!manager.GetGwentCard(cards[i], card))
        {
            continue;
        }
        if ((card.typeFlags & 8) == 8)
        {
            total += card.power;
        }
        if (card.effectFlags.Size() > 0)
        {
            effect = (int)card.effectFlags[0];
            if (effect == 23 || effect == 24 || effect == 25 || effect == 30) { total += 2; }
            else if (effect == 26) { total += 4; }
            else if (effect == 27) { total += 5; }
            else if (effect == 29 || effect == 7) { total += 6; }
            else if (effect == 31) { total += 3; }
            else if (effect == 32 || effect == 33 || effect == 35) { total += 4; }
            else if (effect == 34) { total += 6; }
        }
    }
    return total;
}

// Applies "-index"/"+index" changes (or a full list) to a list of card indices.
function GwaiNpcDeckApply(out cards : array<int>, list : string) : void
{
    var token, rest : string;
    var more : bool = StrLen(list) > 0;
    while (more)
    {
        more = StrSplitFirst(list, ",", token, rest);
        if (!more)
        {
            token = list;
        }
        if (StrLeft(token, 1) == "-")
        {
            cards.Remove(StringToInt(StrMid(token, 1, StrLen(token) - 1), -1));
        }
        else if (StrLeft(token, 1) == "+")
        {
            cards.PushBack(StringToInt(StrMid(token, 1, StrLen(token) - 1), -1));
        }
        else
        {
            cards.PushBack(StringToInt(token, -1));
        }
        list = rest;
    }
}

// Adaptive hero variants (heroes that fit the NPC's faction) are separated by "#"; the game
// draws one per match. A missing variant falls back to the last one.
function GwaiNpcDeckPick(choices : string, pick : int) : string
{
    var first, rest : string;
    while (pick > 0 && StrSplitFirst(choices, "#", first, rest))
    {
        choices = rest;
        pick -= 1;
    }
    if (StrSplitFirst(choices, "#", first, rest))
    {
        return first;
    }
    return choices;
}

// Adaptive: the first step whose strength reaches the target, else the last step.
function GwaiNpcDeckAdaptive(adaptive : string, target : float) : array<int>
{
    var cards : array<int>;
    var step, rest, strength, list : string;
    var more : bool = StrLen(adaptive) > 0;
    while (more)
    {
        more = StrSplitFirst(adaptive, "|", step, rest);
        if (!more)
        {
            step = adaptive;
        }
        StrSplitFirst(step, ":", strength, list);
        GwaiNpcDeckApply(cards, list);
        if ((float)StringToInt(strength, 0) >= target)
        {
            break;
        }
        adaptive = rest;
    }
    return cards;
}

function GwaiNpcDeckTarget() : float
{
    var factor : float = 1.0;
    var difficulty : int = GwaiSettingsDifficulty();
    var player : SDeckDefinition;
    if (difficulty == 0) { factor = 0.85; }
    if (difficulty == 2) { factor = 1.1; }
    // The 5.01 compiler reads struct fields only from a variable, not from a call's result.
    player = theGame.GetGwintManager().GetCurrentPlayerDeck();
    return (float)GwaiDeckStrength(player.cards) * factor;
}

// Native difficulty (1-3) of the deck variant the game picked: its own field, or else the
// variant with the same cards.
function GwaiNpcDeckVariant(deck : SDeckDefinition) : int
{
    var other : SDeckDefinition;
    var variant, i : int;
    var same : bool;
    if (deck.difficulty >= 1 && deck.difficulty <= 3)
    {
        return deck.difficulty;
    }
    for (variant = 1; variant <= 3; variant += 1)
    {
        if (!theGame.GetGwintManager().GetDeck(deck.deckName, variant, other) || other.cards.Size() != deck.cards.Size())
        {
            continue;
        }
        same = true;
        for (i = 0; i < deck.cards.Size(); i += 1)
        {
            if (other.cards[i] != deck.cards[i])
            {
                same = false;
                break;
            }
        }
        if (same)
        {
            return variant;
        }
    }
    return 0;
}

@wrapMethod(CR4GwintManager)
function GetCurrentAIDeck() : SDeckDefinition
{
    var deck : SDeckDefinition;
    var mode : int;
    var strong, adaptive : string;
    var indices : array<int>;
    var chosen : array<name>;
    var card : SCardDefinition;
    var i : int;

    deck = wrappedMethod();
    mode = GwaiSettingsNpcDecks();
    if (mode == 0 || !GetHasDoneTutorial() || deck.deckName == 'tutorialDeck')
    {
        return deck;
    }
    if (!GwaiNpcDeckTable(NameToString(deck.deckName) + ":" + IntToString(GwaiNpcDeckVariant(deck)), strong, adaptive))
    {
        LogChannel('GwentAI', "NPC decks: no table entry for " + NameToString(deck.deckName));
        return deck;
    }
    if (mode == 2)
    {
        GwaiNpcDeckApply(indices, strong);
    }
    else
    {
        indices = GwaiNpcDeckAdaptive(GwaiNpcDeckPick(adaptive, RandRange(3)), GwaiNpcDeckTarget());
    }
    for (i = 0; i < indices.Size(); i += 1)
    {
        if (!GetGwentCardByIndex(indices[i], card))
        {
            LogChannel('GwentAI', "NPC decks: card index not found " + IntToString(indices[i]));
            return deck;
        }
        chosen.PushBack(card.cardName);
    }
    deck.cards = chosen;
    // The chosen deck replaces the extra NPC cards: they are looked up by deck name.
    deck.deckName = 'gwai_npc_deck';
    return deck;
}
