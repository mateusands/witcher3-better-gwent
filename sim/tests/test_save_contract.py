"""Source-level guardrails for optional, removable mod additions.

These checks prevent specific persistent-state changes. They do not prove game
save/load compatibility; the engine round-trip remains a separate release gate.
"""
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCES=ROOT/'mod/settings/modGwentAISettings/content/scripts/local'


def source_text():
    files=tuple(SOURCES.glob('*.ws'))
    assert files
    return '\n'.join(re.sub(r'//[^\n]*|/\*.*?\*/','',p.read_text(),flags=re.S) for p in files)


def test_mod_does_not_create_saved_quest_card_or_inventory_dependencies():
    text=source_text()
    forbidden=('AddCardToCollection','RemoveCardFromCollection','AddCardToDeck','RemoveCardFromDeck',
        'SetFactionDeck','SetSelectedPlayerDeck','UnlockDeck','SetHasDoneTutorial',
        'SetHasDoneDeckTutorial','FactsAdd','FactsRemove','FactsSet','AddFact','RemoveFact',
        'AddItem','RemoveItem','AddMoney','RemoveMoney','SaveGame')
    for function in forbidden:
        assert not re.search(r'\b'+function+r'\s*\(',text),function
    assert not re.search(r'\bsaved\s+(?:var|function|class)\b',text)


def test_custom_config_writes_stay_within_mod_group_and_preserve_native_preferences():
    text=source_text()
    calls=re.findall(r'\bSetRawConfigValueByStr\s*\(([^;]+)\)',text)
    assert calls
    for arguments in calls:
        assert arguments.lstrip().startswith('"GwentAI",')
    assert not re.search(r'\bSetRewardMultiplier\s*\(',text)
    # Wager payout is delegated to its native handler, not duplicated into the mod.
    assert 'forwarded = (float)stake;' in text and 'wrappedMethod(forwarded, isItemReward)' in text
