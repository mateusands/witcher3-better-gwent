"""Medic and leader revive dialog title (tools/v8_runtime_patch.py).

Spec (owner, 13 October 2026): the game's revive dialog (a Medic, or a leader that revives a card)
asks for the text key "gwint_choose_card_to_ressurect", misspelled, so the dialog opens without its
title in every language; the game's text files hold the key spelled "gwint_choose_card_to_resurrect".
Better Gwent's copy of the Gwent screen asks for the correct key. Visual only: the choice, the
revived card and the match are unchanged.

Given the game's CardInstance and CardLeaderInstance code, when Better Gwent patches it, then every
revive dialog asks for the correctly spelled key and none for the misspelled one.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

from v8_runtime_patch import patch  # noqa: E402

NATIVE = ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'
WRONG, RIGHT = '[[gwint_choose_card_to_ressurect]]', '[[gwint_choose_card_to_resurrect]]'


def test_revive_dialogs_ask_for_the_correct_title_key():
    for name in ('CardInstance', 'CardLeaderInstance'):
        vanilla = (NATIVE / (name + '.as')).read_text()
        assert WRONG in vanilla                       # the game's own typo
        patched = patch(name, vanilla)
        assert WRONG not in patched, name
        assert patched.count(RIGHT) == vanilla.count(WRONG), name
