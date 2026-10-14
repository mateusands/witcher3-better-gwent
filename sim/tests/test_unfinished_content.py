"""Content the game left unfinished, completed by Better Gwent (no card or rule changes).

Spec (owner, 13 October 2026). Everything stays removable at any time: the sounds live in Better
Gwent's copy of the Gwent screen; the glossary entries are the game's own entries (unlocking one
only marks a game entry as read, like playing the base game does).
- Agile sound (dropped, 14 October 2026): the game's unused agile event plays a sound of 0.083 s
  (gui.bnk, 2,319 bytes), too short to hear; in game agile units went silent. Agile units keep
  the game's row sound (1.3 s and 1.7 s), as in vanilla.
- Skellige sound: the Skellige faction ability calls a sound that does not exist in any sound
  bank, so it is silent. Better Gwent plays the game's revive sound (the ability brings units
  back from the discard pile), which every installation has.
- Glossary, special ability entry: the game asks for it under a misspelled alias that points to a
  missing file, so it never unlocks. Better Gwent unlocks the game's real file when a match starts.
- Glossary, leader cards entry: ready in the game, never unlocked. Better Gwent unlocks it when the
  deck builder opens, next to the game's other deck builder entries.
The glossary unlocks run only while Better Gwent is On.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

from v8_runtime_patch import NATIVE_CLASSES, patch  # noqa: E402

NATIVE = ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'
LOCAL = ROOT / 'mod/settings/modGwentAISettings/content/scripts/local'


def native(name):
    return (NATIVE / (name + '.as')).read_text()


def agile_branch(source):
    start = source.index('if(templateRef.isType(CardTemplate.CardType_RangedMelee))')
    return source[start:source.index('return this._placeRangedFXClassRef;', start)]


def test_agile_units_keep_the_row_sound():
    # Given the game's effect manager, where an agile unit plays the sound of its row,
    # then Better Gwent leaves the effect manager as the game ships it: no 0.083 s agile sound
    assert 'CardFXManager' not in NATIVE_CLASSES
    assert 'gui_gwint_close_combat' in agile_branch(native('CardFXManager'))


def test_skellige_ability_plays_an_existing_sound():
    vanilla = native('GwintGameFlowController')
    assert vanilla.count('playSound("gui_gwint_skellige_ability")') == 2
    patched = patch('GwintGameFlowController', vanilla)
    assert 'gui_gwint_skellige_ability' not in patched
    block = patched[patched.index('gwint_skel_ability_player_triggered'):]
    block = block[:block.index('OnAISkelAbilityShown') + 200]
    assert block.count('playSound("gui_gwint_resurrect")') == 2


def glossary_source():
    return (LOCAL / 'gwai_glossary.ws').read_text()


def wrapper(source, cls, name):
    match = re.search(r'@wrapMethod\(' + cls + r'\)\s*function\s+' + name + r'\s*\(\s*\)\s*\{', source)
    assert match, (cls, name)
    start, depth, end = match.end(), 1, match.end()
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end - 1]


def test_glossary_unlocks_the_special_ability_entry_from_its_real_file():
    body = wrapper(glossary_source(), 'CR4GwintGameMenu', 'EnableJournalTutorialEnries')
    assert body.count('wrappedMethod()') == 1 and 'GwaiSettingsEnabled()' in body
    assert 'unitcardspecialabilitynew.journal' in body          # the real file, singular "card"
    assert 'LoadResource(path, true)' in glossary_source()           # loaded by depot path


def test_deck_builder_unlocks_the_leader_cards_entry():
    body = wrapper(glossary_source(), 'CR4DeckBuilderMenu', 'EnableJournalTutorialEnries')
    assert body.count('wrappedMethod()') == 1 and 'GwaiSettingsEnabled()' in body
    assert "ActivateJournalEntry('leadercardsMERGED')" in body


def test_package_ships_the_glossary_script():
    assert 'gwai_glossary.ws' in (ROOT / 'tools/build_v8_package.py').read_text()
