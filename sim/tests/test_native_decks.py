"""Local vanilla deck adapter matches actual recorded script output and preserves XML."""
import sys
from pathlib import Path
import hashlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gwentsim.data import load_match
from gwentsim.native_decks import NativeDecks
from gwentsim.betting import AcceptedBet

ROOT=Path(__file__).resolve().parents[2]


def shape(deck):
    return deck.selected_king_index,deck.card_indices,deck.dynamic_cards,deck.dynamic_card_requirements


def test_native_xml_adapter_matches_all_recorded_opponent_definitions():
    sample=load_match(ROOT/'game/records/g113.json')
    native=NativeDecks(ROOT/'game/vanilla/xml/content0/gameplay/items',sample.templates)
    corpus=sorted((ROOT/'game/records').glob('g[0-9][0-9][0-9].json'))
    assert corpus
    # Recorded with the Better AI build whose GetDifficulty returned real level 1-14 thresholds
    # (fewer NPC dynamic cards than vanilla); fixed in gwai_betting.ws on 2026-10-11.
    MOD_THRESHOLD_BUG={'g127.json','g128.json'}
    for path in corpus:
        if path.name in MOD_THRESHOLD_BUG:continue
        recorded=load_match(path).decks[1]
        assert any(shape(native.build(name,difficulty))==shape(recorded)
                   for name in native.npc_names() for difficulty in (1,2,3)),path.name


def test_high_stakes_preserves_defined_cards_and_only_enables_valid_level_fifteen():
    sample=load_match(ROOT/'game/records/g113.json');directory=ROOT/'game/vanilla/xml/content0/gameplay/items'
    xml=directory/'def_gwint_decks.xml';before=hashlib.sha256(xml.read_bytes()).hexdigest()
    native=NativeDecks(directory,sample.templates)
    changed_dynamic=[]
    for name in native.npc_names():
        base=native.build(name,3);high=native.build(name,3,bet=AcceptedBet(150,True))
        assert base.card_indices==high.card_indices and base.selected_king_index==high.selected_king_index
        assert base.dynamic_cards==high.dynamic_cards
        if base.dynamic_card_requirements!=high.dynamic_card_requirements:changed_dynamic.append(name)
    assert changed_dynamic==['NilfNormal','NMLNormal']
    assert 'cirigog' in native.dropped_names  # Do not invent an alias that vanilla rejects.
    assert hashlib.sha256(xml.read_bytes()).hexdigest()==before
