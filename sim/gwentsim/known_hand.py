"""Opponent hand cards that everyone has seen: a card that went back to a hand from the board
or a graveyard (Decoy, for example) is public, so the AI may count on it.

Mirrors the game-side CardManager patch (tools/v8_runtime_patch.py): only the instance ids of
cards that moved from a public list (graveyard, rows, weather) into a hand are kept, and only
those are looked up in the opponent's hand. Nothing else about hidden cards is read.
"""
from .gwint import card_manager as _cm

PUBLIC_LISTS = (2, 3, 4, 5, 6, 7, 8, 9)   # graveyard, siege/ranged/melee rows and modifiers, weather
HAND = 1


def install():
    cls = _cm.CardManager
    if getattr(cls, '_gwai_known_installed', False):
        return
    original = cls.addCardInstanceToList

    def addCardInstanceToList(self, cardInstance, newListID, playerID):
        old = cardInstance.inList
        original(self, cardInstance, newListID, playerID)
        known = self.__dict__.setdefault('_gwai_known', set())
        if newListID == HAND and old in PUBLIC_LISTS:
            known.add(cardInstance.instanceId)
        else:
            known.discard(cardInstance.instanceId)
    cls.addCardInstanceToList = addCardInstanceToList
    cls._gwai_known_installed = True


def known_templates(cm, player):
    """Sorted templates of the publicly known cards in `player`'s hand."""
    known = cm.__dict__.get('_gwai_known', set())
    return tuple(sorted(c.templateId for c in cm.getCardInstanceList(HAND, player) if c.instanceId in known))


install()
