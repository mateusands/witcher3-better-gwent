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
    # g132-g134: played with the NPC decks option on Adaptive (e.g. ScoiaHard:3 step 251, built by the first
    # in-game table, before muster groups were kept whole): not a native deck.
    NPC_DECK_OPTION={'g132.json','g133.json','g134.json'}
    # g135-g147: decks built before heroes were made unique (Geralt + Geralt GOG) and before the
    # three-level targets (85/100/110%).
    NPC_DECK_OPTION|={'g%d.json'%g for g in range(135,148)}
    from gwentsim.npc_balance import apply_mode
    from blunder_hunter import card_names
    names=card_names()
    for path in corpus:
        if path.name in MOD_THRESHOLD_BUG|NPC_DECK_OPTION:continue
        match=load_match(path);recorded=match.decks[1]
        # From g130 on, the installed mod repairs the extra-card requirements (Better Gwent On).
        if any(shape(native.build(name,difficulty,repaired=repaired))==shape(recorded)
               for name in native.npc_names() for difficulty in (1,2,3) for repaired in (False,True)):continue
        # Otherwise the NPC decks option (Adaptive/Strong) built it: the simulator's deck for the
        # recorded player deck at one of the four levels, in the current shape or the 0.9.0 one
        # (8 specials, 24 Strong units, Triss allowed; installed until the lean decks, 12 October 2026).
        player=match.decks[0].card_indices
        # Adaptive draws one of the hero variants per match (since 12 October 2026); g152-g157 still
        # allowed Triss in the Adaptive fallback (balanced:triss).
        assert any(sorted(apply_mode(match.templates,native.build(name,difficulty,repaired=True),names,mode,player,level,variant).card_indices)
                   ==sorted(recorded.card_indices)
                   for name in native.npc_names() for difficulty in (1,2,3)
                   for mode in ('balanced','strong','balanced:v090','strong:v090','balanced:allheroes','balanced:strictheroes','balanced:triss')
                   for level in (0,1,2,3) for variant in range(3)),path.name


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
