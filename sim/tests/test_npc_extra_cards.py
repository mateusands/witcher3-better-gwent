"""Extra NPC cards never duplicate a hero or exceed 3 copies in a mod-built NPC deck.

Spec. Some quests give the NPC extra cards (CR4GwintManager.GetAdditionalCards(), the quest's
prize cards). The vanilla game appends them to whatever GetCurrentAIDeck returns, without any
uniqueness check. With NPC decks set to Adaptive or Strong, the mod replaces the deck cards, so:

  Given a mod-built NPC deck and the quest's extra NPC cards,
  When the mod returns the deck from GetCurrentAIDeck,
  Then every hero of the deck that is also an extra card is left out (heroes are unique; the
       GOG bonus version, geraltGOG or ciriGOG, is the same hero as the base card),
  And for any other card, copies in the deck plus extra copies never exceed 3,
  And the extra cards themselves are untouched (the game still appends them).

Original mode and Better Gwent Off keep the native deck untouched.

The WS code cannot run here, so the rule is checked twice: a Python reference
(npc_balance.without_extra_duplicates) with behaviour tests, and static checks of the WS wrap.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))

from gwentsim import constants as C  # noqa: E402
from gwentsim import npc_balance as nb  # noqa: E402

DECKS_WS = ROOT / 'mod/settings/modGwentAISettings/content/scripts/local/gwai_npc_decks.ws'


class Card:
    def __init__(self, index, hero=False):
        self.index = index
        self.type_array = C.CardType_Hero if hero else 0

    def is_type(self, type_id):
        return (self.type_array & type_id) == type_id


NAMES = {1: 'geralt', 2: 'geraltGOG', 3: 'mysterious_elf', 4: 'ciri', 5: 'ciriGOG',
         10: 'spy_unit', 11: 'horn', 12: 'plain_unit'}
TEMPLATES = {i: Card(i, hero=i < 10) for i in NAMES}


def run(cards, extra):
    return nb.without_extra_duplicates(TEMPLATES, NAMES, cards, extra)


def test_hero_also_given_as_extra_card_is_left_out():
    # Given the g162 case: Avallac'h is in the deck and is the quest's extra card
    # When the extra cards are accounted for
    # Then the deck keeps no Avallac'h (the extra copy is the only one)
    assert run([3, 10, 12, 4], ['mysterious_elf']) == [10, 12, 4]


def test_gog_twin_counts_as_the_same_hero():
    # Given Geralt (GOG) in the deck and the base Geralt as extra, and the reverse for Ciri
    # Then both deck copies are left out
    assert run([2, 12], ['geralt']) == [12]
    assert run([4, 12], ['ciriGOG']) == [12]


def test_non_hero_is_capped_at_three_copies_with_the_extras():
    # Given 3 Horns in the deck and 1 extra Horn
    # Then the deck keeps 2 (the first ones), so 3 in total
    assert run([11, 12, 11, 11], ['horn']) == [11, 12, 11]
    # And with 2 extra copies only 1 is kept
    assert run([11, 11, 11, 12], ['horn', 'horn']) == [11, 12]


def test_nothing_changes_without_overlap():
    # Given extra cards that are not in the deck (or keep every total within the limits)
    # Then the deck is unchanged
    assert run([1, 3, 11, 12], ['ciri', 'spy_unit']) == [1, 3, 11, 12]
    assert run([11, 11, 12], ['horn']) == [11, 11, 12]
    assert run([1, 11], []) == [1, 11]


def wrap_body():
    source = DECKS_WS.read_text()
    match = re.search(r'@wrapMethod\(CR4GwintManager\)\s*function\s+GetCurrentAIDeck\b', source)
    start = source.index('{', match.end())
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def function_body(name):
    source = DECKS_WS.read_text()
    start = source.index('{', source.index('function ' + name + '('))
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def test_ws_wrap_filters_the_mod_deck_against_the_extra_cards():
    body = wrap_body()
    assert 'GetAdditionalCards()' in body
    assert 'deck.cards = GwaiNpcDeckWithoutExtras(chosen, GetAdditionalCards());' in body
    # Only the replaced deck is filtered: Original/Off and a missing table entry return earlier.
    assert body.index('mode == 0') < body.index('GwaiNpcDeckTable(') < body.index('GwaiNpcDeckWithoutExtras(')


def test_ws_filter_applies_the_hero_and_three_copies_rules():
    body = function_body('GwaiNpcDeckWithoutExtras')
    assert 'GwintType_Hero' in body
    assert re.search(r'StrReplaceAll\([^;]*"GOG"', body)
    assert re.search(r'>=\s*3', body)
    # Struct fields only from a variable (5.01 compiler).
    assert not re.search(r'\)\.(typeFlags|cardName)\b', body)
