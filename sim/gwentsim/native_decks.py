"""Local vanilla XML adapter; no game definitions are bundled or altered here."""
from dataclasses import replace
from pathlib import Path
import xml.etree.ElementTree as ET

from .data import DeckDefinition
from .betting import AcceptedBet


class NativeDecks:
    def __init__(self, directory, templates):
        base = Path(directory)
        self.templates = templates
        self.dropped_names = set()
        self.indices = {}
        for filename in ('def_gwint_cards_final.xml', 'def_gwint_battle_king_cards.xml'):
            for card in ET.parse(base / filename).findall('.//card'):
                self.indices[card.attrib['name']] = int(card.attrib['index'])
        self.collections = {c.attrib['name']: c for c in ET.parse(base / 'def_gwint_decks.xml').findall('.//deck_collection')}

    def build(self, name, difficulty, player=1, bet=None, repaired=False):
        bet = bet or AcceptedBet(10, False)
        selected = bet.native_difficulty(difficulty)
        collection = self.collections[name]
        variant = next((d for d in collection.findall('deck') if int(d.attrib['difficulty']) == selected), None)
        if variant is None:
            return self.build('NilfEasy', difficulty, player, bet, repaired)
        dynamic = collection.findall('./dynamicCards/card')
        base_cards = variant.findall('card')
        for c in [*base_cards, *dynamic]:
            if c.attrib['name'] not in self.indices:
                self.dropped_names.add(c.attrib['name'])
        # Vanilla GetGwentCard rejects these names; recorded decks confirm they
        # are omitted, not repaired by inventing case/item-name aliases.
        base_cards = [c for c in base_cards if c.attrib['name'] in self.indices]
        dynamic = [c for c in dynamic if c.attrib['name'] in self.indices]
        def index(value):
            result = self.indices[value]
            if result not in self.templates:
                raise ValueError('recorded template unavailable: %s' % value)
            return result
        special = variant.attrib.get('specialCard', '')
        result = DeckDefinition(player, name, index(variant.attrib['leaderCard']), index(special) if special else -1,
            [index(c.attrib['name']) for c in base_cards],
            [bet.dynamic_requirement(int(c.attrib['difficulty']), difficulty, repaired) for c in dynamic],
            [index(c.attrib['name']) for c in dynamic])
        return result

    def npc_names(self):
        # Starter/player collections include deliberately empty locked faction decks.
        return [name for name in self.collections if name not in ('North', 'Nilf', 'scotial', 'nml', 'ske') and
                all(c.findall('card') for c in self.collections[name].findall('deck'))]
