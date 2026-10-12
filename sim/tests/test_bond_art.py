"""Tight Bond art: one picture per copy, visual only and only while the mod is On."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

import pytest
from v8_as_test import close_brace, strip_types, script_file
from v8_runtime_patch import BOND_ART, COPY_ART, DECK_BUILDER_CLASSES, NATIVE_CLASSES, deck_builder_patch, patch

NATIVE = ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'
DECK_BUILDER = ROOT / 'game/vanilla/as_deck_builder/scripts/red/game/witcher3/menus/gwint'
SETTINGS = ROOT / 'mod/settings/modGwentAISettings/content/scripts/local/gwai_settings.ws'
CARDS = ROOT / 'game/vanilla/xml/content0/gameplay/items/def_gwint_cards_final.xml'
# Every copy of each Tight Bond group and the picture it shows with the mod On.
GROUPS = {
    'Poor Fucking Infantry': {125: 'nor_poor_infantry', 126: 'nor_poor_infantry_1', 127: 'nor_poor_infantry_2'},
    'Crinfrid Reavers': {130: 'nor_crinfrid', 131: 'nor_crinfrid_1', 132: 'nor_crinfrid_2'},
    'Catapult': {140: 'nor_catapult', 141: 'nor_catapult_1'},
    'Impera Brigade': {245: 'nil_impera_brigade', 246: 'nil_impera_brigade_1', 247: 'nil_impera_brigade_2', 248: 'nil_impera_brigade_3'},
    'Nausicaa Cavalry Rider': {250: 'nil_nauzicaa', 251: 'nil_nauzicaa_1', 252: 'nil_nauzicaa_2'},
}


def stock_cards():
    if not CARDS.exists():
        pytest.skip('local game card definitions not extracted')
    text = CARDS.read_text(encoding='utf-8', errors='replace')
    cards = {}
    for match in re.finditer(r'<card\b(.*?)>', text, re.S):
        attrs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', match.group(1)))
        if attrs.get('index', '').isdigit():
            cards[int(attrs['index'])] = attrs
    return cards


def shown(index, picture):
    old, new = BOND_ART.get(index, (None, None))
    return new if picture == old else picture


def test_table_matches_stock_definitions_and_gives_every_copy_its_own_picture():
    cards = stock_cards()
    for index, (old, _) in BOND_ART.items():
        assert cards[index]['picture'] == old, index
    for name, copies in GROUPS.items():
        stock = [cards[index] for index in copies]
        # Same card: one title, power and picture in the stock definitions.
        assert len({(c['title'], c['power'], c['picture']) for c in stock}) == 1, name
        pictures = {index: shown(index, cards[index]['picture']) for index in copies}
        assert pictures == copies, name
        assert len(set(pictures.values())) == len(copies), name
    # Only the copies whose picture changes are in the table.
    expected = {i: p for copies in GROUPS.values() for i, p in copies.items() if cards[i]['picture'] != p}
    assert {i: new for i, (_, new) in BOND_ART.items()} == expected


def test_shared_index_cards_match_stock_definitions():
    cards = stock_cards()
    # Blue Stripes Commando and Siege Tower: one definition, several owned copies; no cards added.
    assert COPY_ART == {160: ('nor_blue_stripes', ('nor_blue_stripes', 'nor_blue_stripes_1', 'nor_blue_stripes_2')),
                        170: ('nor_siege_tower', ('nor_siege_tower', 'nor_siege_tower_1'))}
    for index, (old, pictures) in COPY_ART.items():
        assert index not in BOND_ART
        assert cards[index]['picture'] == old == pictures[0]
        assert len(set(pictures)) == len(pictures)


def patched_slot():
    return patch('CardSlot', (NATIVE / 'CardSlot.as').read_text())


def test_card_slot_loads_the_remapped_picture_and_patches_once():
    assert 'CardSlot' in NATIVE_CLASSES
    source = patched_slot()
    assert 'loadIcon("icons/gwint/" + gwaiBondPicture(cardTemplate,this._instanceId) + ".png");' in source
    assert 'cardTemplate.imageLoc + ".png"' not in source
    for old, new in BOND_ART.values():
        assert '"%s","%s"' % (old, new) in source
    for old, pictures in COPY_ART.values():
        assert '"%s",[%s]' % (old, ','.join('"%s"' % p for p in pictures)) in source
    with pytest.raises(ValueError):
        patch('CardSlot', source)


def node(script):
    result = subprocess.run(['node', script_file(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def body(source, name):
    match = re.search(r'function ' + name + r'\([^)]*\)[^{]*\{', source)
    return strip_types(source[match.end():close_brace(source, match.end()) - 1]).replace(' as Array', '')


def run_picture(cases):
    """Each case: index, picture, optional settings, optional instance (-1 = template only) and copy."""
    source = patched_slot()
    tables = ''.join('var %s=%s;' % m for m in re.findall(r'(GWAI_\w+_ART):Object = (\{.*?\});', source))
    script = tables + 'var flow=null,copies={};function int(v){return v|0;}'
    script += 'var GwintGameFlowController={getInstance:()=>flow};'
    script += 'var CardManager={getInstance:()=>({gwaiCopyOrdinal:id=>id in copies?copies[id]:-1})};'
    script += 'var pick=function(cardTemplate,instanceId){%s};var out=[];' % body(source, 'gwaiBondPicture')
    script += 'for(var c of %s){flow=c.settings===undefined?null:{gwaiSettingsSnapshot:()=>c.settings};' % json.dumps(cases)
    script += 'copies={};if(c.copy!==undefined)copies[c.instance]=c.copy;'
    script += 'out.push(pick({index:c.index,imageLoc:c.picture},c.instance===undefined?7:c.instance));}console.log(JSON.stringify(out));'
    return node(script)


ON = {'enabled': True, 'difficulty': 2, 'autoplay': False}
OFF = {'enabled': False, 'difficulty': 2, 'autoplay': False}


@pytest.mark.parametrize('index', sorted(BOND_ART))
def test_picture_changes_only_when_the_mod_is_on(index):
    old, new = BOND_ART[index]
    on, off = ON, OFF
    cases = [
        dict(index=index, picture=old, settings=on),
        dict(index=index, picture=old, settings=off),     # main switch Off: stock art
        dict(index=index, picture=old, settings=None),    # no match packet yet
        dict(index=index, picture=old),                   # no game flow
        dict(index=index, picture='other_mod_art', settings=on),   # another mod's picture wins
    ]
    assert run_picture(cases) == [new, old, old, old, 'other_mod_art']


def test_other_cards_are_untouched():
    on = {'enabled': True, 'difficulty': 2, 'autoplay': True}
    cases = [dict(index=i, picture=p, settings=on) for i, p in
             [(125, 'nor_poor_infantry'), (141, 'nor_catapult_1'), (252, 'nil_nauzicaa_2'), (160, 'nor_blue_stripes'), (1, 'x')]]
    assert run_picture(cases) == [c['picture'] for c in cases]


@pytest.mark.parametrize('index', sorted(COPY_ART))
def test_copies_of_one_index_take_their_art_by_copy_slot(index):
    old, pictures = COPY_ART[index]
    cases = [dict(index=index, picture=old, settings=ON, instance=40 + c, copy=c) for c in range(4)]
    expected = [pictures[c % len(pictures)] for c in range(4)]   # further copies cycle
    assert run_picture(cases) == expected
    assert len(set(expected[:len(pictures)])) == len(pictures)
    stock = [
        dict(index=index, picture=old, settings=OFF, instance=41, copy=1),      # main switch Off
        dict(index=index, picture=old, instance=41, copy=1),                    # no game flow
        dict(index=index, picture=old, settings=None, instance=41, copy=1),     # no match packet yet
        dict(index=index, picture=old, settings=ON, instance=-1),               # template only
        dict(index=index, picture=old, settings=ON, instance=41),               # no copy slot recorded
        dict(index=index, picture='other_mod_art', settings=ON, instance=41, copy=1),
    ]
    assert run_picture(stock) == [old] * 5 + ['other_mod_art']


def test_copy_slots_are_per_owner_and_card_and_last_the_instance_life():
    source = patch('CardManager', (NATIVE / 'CardManager.as').read_text())
    assert 'this._cardInstances[newInstance.instanceId] = newInstance;\n         this.gwaiAssignCopy(newInstance);' in source
    assert 'delete this._cardInstances[cardInstance.instanceId];\n         delete this._gwaiCopy[cardInstance.instanceId];' in source
    script = 'function int(v){return v|0;}var m={_cardInstances:{},_gwaiCopy:{}};var next=0;'
    script += 'm.gwaiAssignCopy=function(card){%s};m.gwaiCopyOrdinal=function(instanceId){%s};' % (
        re.sub(r'for each\((\w+) in ([\w.]+)\)', r'for(\1 of Object.values(\2))', body(source, 'gwaiAssignCopy')),
        body(source, 'gwaiCopyOrdinal'))
    script += 'function spawn(t,p){var c={instanceId:++next,templateId:t,owningPlayer:p};m._cardInstances[c.instanceId]=c;m.gwaiAssignCopy(c);return c.instanceId;}'
    script += 'function drop(id){delete m._cardInstances[id];delete m._gwaiCopy[id];}'
    # Player 0 draws three Blue Stripes, the NPC two, plus other cards in between.
    script += 'var a=spawn(160,0),x=spawn(170,0),b=spawn(160,0),n1=spawn(160,1),c=spawn(160,0),n2=spawn(160,1),y=spawn(170,0);'
    script += 'var out=[a,b,c,n1,n2,x,y].map(id=>m.gwaiCopyOrdinal(id));'
    # The second copy goes back to the deck (exchange) and is drawn again: it takes the free slot.
    script += 'drop(b);out.push(m.gwaiCopyOrdinal(b));var b2=spawn(160,0);out.push(m.gwaiCopyOrdinal(b2));'
    script += 'out.push(m.gwaiCopyOrdinal(a),m.gwaiCopyOrdinal(c),m.gwaiCopyOrdinal(999));console.log(JSON.stringify(out));'
    assert node(script) == [0, 1, 2, 0, 1, 0, 1, -1, 1, 0, 2, -1]


# Deck builder (pause menu > Gwent decks): its own SWF and its own CardSlot.

def deck_source(name):
    path = DECK_BUILDER / (name + '.as')
    if not path.exists():
        pytest.skip('local deck builder scripts not exported (game/vanilla/as_deck_builder)')
    return path.read_text()


def test_deck_builder_patches_apply_once_and_register_the_switch_before_the_decks():
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    assert 'this.gwaiPicture = gwaiDeckPicture(param1,this.gwaiTileData());\n            loadIcon("icons/gwint/" + this.gwaiPicture + ".png");' in slot
    assert 'param1.imageLoc + ".png"' not in slot
    for old, new in BOND_ART.values():
        assert '"%s","%s"' % (old, new) in slot
    menu = deck_builder_patch('DeckBuilderMenu', deck_source('DeckBuilderMenu'))
    config = menu[menu.index('override protected function configUI()'):]
    assert config.index('"gwai.deck.bondart",[this.gwaiUpdateDeckArt]') < config.index('"gwint.deckbuilder.decks"')
    assert config.index('dispatchEvent(new GameEvent(GameEvent.CALL,"OnConfigUI"));') < config.index('"gwai.deck.bondart"')
    for name in DECK_BUILDER_CLASSES:
        with pytest.raises(ValueError):
            deck_builder_patch(name, deck_builder_patch(name, deck_source(name)))


def test_deck_builder_script_sends_the_switch_before_the_deck_data():
    source = SETTINGS.read_text()
    match = re.search(r'@wrapMethod\(CR4DeckBuilderMenu\)\s*function SendDeckInformation\(\) : void\s*\{(.*?)\n\}', source, re.S)
    assert match
    hook = match.group(1)
    assert hook.index('GwaiSettingsInitialize();') < hook.index('SetFlashBool("gwai.deck.bondart", GwaiSettingsEnabled());') < hook.index('wrappedMethod();')
    assert hook.count('wrappedMethod();') == 1


def deck_slot_script():
    """CardSlot statics of the patched deck builder as JS (tables, switch, owned copies, pictures)."""
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    script = 'function int(v){return v|0;}'
    script += ''.join('var %s=%s;' % m for m in re.findall(r'(GWAI_\w+_ART):Object = (\{.*?\});', slot))
    script += 'var gwaiDeckArt=false,templates={};'
    script += 'var CardManager={getInstance:()=>({getCardTemplate:i=>templates[i]||null})};'
    script += 'var CardSlot={gwaiOwnedCopies:{}};'
    for name in ('gwaiCopyPictures', 'gwaiDeckPicture'):
        params = strip_types(re.search(r'function ' + name + r'\(([^)]*)\)', slot).group(1), True)
        script += 'CardSlot.%s=function(%s){%s};' % (name, params, body(slot, name))
    return script


def run_deck_picture(cases):
    """Each case: art switch (or None when the switch never arrived), index, picture, optional tile data."""
    script = deck_slot_script() + 'var out=[];'
    script += 'for(var c of %s){gwaiDeckArt=c[0]===null?false:c[0];' % json.dumps(cases)
    script += 'out.push(CardSlot.gwaiDeckPicture({index:c[1],imageLoc:c[2]},c.length>3?c[3]:null));}'
    script += 'console.log(JSON.stringify(out));'
    return node(script)


@pytest.mark.parametrize('index', sorted(BOND_ART))
def test_deck_builder_picture_changes_only_when_the_mod_is_on(index):
    old, new = BOND_ART[index]
    cases = [[True, index, old], [False, index, old], [None, index, old], [True, index, 'other_mod_art']]
    assert run_deck_picture(cases) == [new, old, old, 'other_mod_art']


def test_deck_builder_leaves_other_cards_alone():
    cases = [[True, i, p] for i, p in [(125, 'nor_poor_infantry'), (141, 'nor_catapult_1'), (252, 'nil_nauzicaa_2'),
                                       (160, 'nor_blue_stripes'), (170, 'nor_siege_tower'), (1001, 'leader')]]
    assert run_deck_picture(cases) == [c[2] for c in cases]


# Deck builder: Blue Stripes Commando and Siege Tower, one tile per copy while the mod is On.

@pytest.mark.parametrize('index', sorted(COPY_ART))
def test_deck_builder_copy_tiles_take_their_art_by_copy(index):
    old, pictures = COPY_ART[index]
    cases = [[True, index, old, dict(cardID=index, numCopies=1, gwaiCopy=0, gwaiArt=a)] for a in range(len(pictures) + 1)]
    expected = list(pictures) + [pictures[0]]                    # a further copy cycles
    stock = [
        [False, index, old, dict(cardID=index, numCopies=1, gwaiCopy=0, gwaiArt=1)],     # Off
        [True, index, old, dict(cardID=index, numCopies=3)],                              # grouped tile
        [True, index, old, None],                                                         # no tile data (zoom, leader)
        [True, index, old, dict(cardID=999, numCopies=1, gwaiCopy=1, gwaiArt=1)],         # stale data of another card
        [True, index, 'other_mod_art', dict(cardID=index, numCopies=1, gwaiCopy=1, gwaiArt=1)],
    ]
    assert run_deck_picture(cases + stock) == expected + [old] * 4 + ['other_mod_art']


def test_deck_builder_split_patches_apply_once():
    module = deck_builder_patch('GwintDeckCTabModule', deck_source('GwintDeckCTabModule'))
    assert 'return this.gwaiSplitCopies(_loc2_);' in module
    assert 'if(CardSlot.gwaiCopyPictures(param1) != null)\n         {\n            _loc6_ = this.gwaiSetCopies(param1,param2);' in module
    assert module.count('int(param1.gwaiCopy) - int(param2.gwaiCopy)') == 2      # both sorters
    menu = deck_builder_patch('DeckBuilderMenu', deck_source('DeckBuilderMenu'))
    assert 'this.mcCollectionHolder.gwaiCopyFromTop = true;' in menu
    update = menu[menu.index('protected function updateCollectionDeck()'):]
    assert update.index('CardSlot.gwaiOwnedCopies = {};') < update.index('CardSlot.gwaiOwnedCopies[_loc3_.cardID] = int(CardSlot.gwaiOwnedCopies[_loc3_.cardID]) + int(_loc3_.numCopies);')
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    # A reused tile with the same card index but another copy reloads its picture.
    assert 'gwaiDeckPicture(gwaiTemplate,data) != this.gwaiPicture)\n            {\n               this.updateCardData();' in slot


def module_script():
    """The patched GwintDeckCTabModule list code as JS over a fake tile list and two GwintDecks."""
    module = deck_builder_patch('GwintDeckCTabModule', deck_source('GwintDeckCTabModule'))
    script = deck_slot_script()
    script += """
function List(){this.r=[];this.data=[];}
List.prototype.getRenderersLength=function(){return this.r.length;};
List.prototype.getRendererAt=function(i){return this.r[i];};
List.prototype.addRenderer=function(d){this.r.push({cardIndex:d.cardID,data:d,setData:function(x){this.data=x;this.cardIndex=x.cardID;}});this.data.push(d);};
List.prototype.removeRenderer=function(t){this.r.splice(this.r.indexOf(t),1);this.data.splice(this.data.indexOf(t.data),1);};
List.prototype.validateNow=function(){};
var CardTemplate={CardType_Creature:1};
var mcTabList={selectedIndex:0},_lastMoveWasMouse=true,closed=0;function close(){closed++;}
function Deck(cards){this.cardIndices=cards.slice();this.onCardChangedCallback=null;}
Deck.prototype.count=function(i){return this.cardIndices.filter(c=>c==i).length;};
Deck.prototype.dbAddCard=function(i){this.cardIndices.push(i);if(this.onCardChangedCallback)this.onCardChangedCallback(i,this.count(i));};
Deck.prototype.dbRemoveCard=function(i){var k=this.cardIndices.indexOf(i);if(k>=0)this.cardIndices.splice(k,1);if(this.onCardChangedCallback)this.onCardChangedCallback(i,this.count(i));};
function Module(top){this.mcCardSlotList=new List();this.gwaiCopyFromTop=top;this.targetDeck=null;}
Module.prototype.IsCardInCurrentTab=function(){return true;};
"""
    for name in ('fillDataWithCallback', 'deckbuilderCardSorter', 'gwaiCopyEntry', 'gwaiSplitCopies', 'gwaiSetCopies', 'onCardChangedCallback'):
        params = strip_types(re.search(r'function ' + name + r'\(([^)]*)\)', module).group(1), True)
        code = re.sub(r' as \w+', '', body(module, name))
        script += 'Module.prototype.%s=function(%s){%s};\n' % (name, params, code)
    # Fill as updateSubData does (All tab): build, sort, show.
    script += """
Module.prototype.show=function(deck){this.targetDeck=deck;deck.onCardChangedCallback=this.onCardChangedCallback.bind(this);
  var d=this.fillDataWithCallback(null);d.sort(this.deckbuilderCardSorter.bind(this));
  this.mcCardSlotList=new List();for(var x of d)this.mcCardSlotList.addRenderer(x);};
function tiles(m){return m.mcCardSlotList.r.map(t=>[t.data.cardID,t.data.numCopies,t.data.gwaiArt===undefined?null:t.data.gwaiArt]);}
"""
    return script


def run_deck_builder(owned, deck_cards, moves, art=True):
    """Open the deck builder, then move cards ('in' = collection -> deck, 'out' = deck -> collection).

    Returns the tiles of both lists after each step and the tiles a fresh reopen draws at the end."""
    script = module_script()
    script += 'gwaiDeckArt=%s;' % ('true' if art else 'false')
    script += 'for(var i of [160,170,10,11])templates[i]={index:i,imageLoc:{160:"nor_blue_stripes",170:"nor_siege_tower"}[i]||"x"+i,factionIdx:1,power:5,isType:()=>true};'
    script += 'var owned=%s,moves=%s,deckCards=%s;' % (json.dumps(owned), json.dumps(moves), json.dumps(deck_cards))
    script += """
function open(deckCards){
  CardSlot.gwaiOwnedCopies={};var coll=[];
  for(var id in owned){CardSlot.gwaiOwnedCopies[id]=owned[id];var n=owned[id]-deckCards.filter(c=>c==id).length;for(var k=0;k<n;k++)coll.push(+id);}
  var deck=new Deck(deckCards),collection=new Deck(coll),dm=new Module(false),cm=new Module(true);
  dm.show(deck);cm.show(collection);return {deck,collection,dm,cm};}
var s=open(deckCards),out=[[tiles(s.dm),tiles(s.cm)]];
for(var [dir,id] of moves){
  if(dir=='out'){s.collection.dbAddCard(id);s.deck.dbRemoveCard(id);}     // transferCardFromDeckToCollection
  else{s.collection.dbRemoveCard(id);s.deck.dbAddCard(id);}               // transferCardFromCollectionToDeck
  out.push([tiles(s.dm),tiles(s.cm)]);}
var again=open(s.deck.cardIndices);
console.log(JSON.stringify({steps:out,deck:s.deck.cardIndices,reopen:[tiles(again.dm),tiles(again.cm)],closed:closed}));
"""
    return node(script)


def arts(tiles, index):
    return sorted(t[2] for t in tiles if t[0] == index)


def test_deck_builder_shows_one_tile_per_copy_and_moves_keep_counts_and_art_consistent():
    owned = {160: 3, 170: 2, 10: 2}
    moves = [('out', 160), ('out', 160), ('in', 160), ('out', 170), ('out', 160), ('out', 160), ('in', 160), ('in', 160),
             ('in', 160), ('in', 170), ('out', 10), ('in', 10)]
    result = run_deck_builder(owned, [160, 160, 160, 170, 170, 10], moves)
    deck = {160: 3, 170: 2, 10: 1}
    steps = result['steps']
    for step, (deck_tiles, collection_tiles) in enumerate(steps):
        if step:
            direction, index = moves[step - 1]
            deck[index] += 1 if direction == 'in' else -1
        for index in (160, 170):
            in_deck, in_collection = arts(deck_tiles, index), arts(collection_tiles, index)
            # One tile per copy, every tile a single copy; the counts are the deck's own.
            assert len(in_deck) == deck[index] and len(in_collection) == owned[index] - deck[index], (step, index)
            assert all(t[1] == 1 for t in deck_tiles + collection_tiles if t[0] == index)
            # The deck holds copies 1..d, the collection the rest: every picture once.
            assert in_deck == list(range(deck[index])), (step, index)
            assert sorted(in_deck + in_collection) == list(range(owned[index])), (step, index)
        # Other cards keep the stock grouped tile.
        assert [t for t in deck_tiles if t[0] == 10] == ([[10, deck[10], None]] if deck[10] else [])
    assert sorted(result['deck']) == sorted(i for i, n in deck.items() for _ in range(n))
    # Leaving and reopening draws the same tiles (order within a card aside).
    final = steps[-1]
    for now, reopened in zip(final, result['reopen']):
        assert sorted(map(tuple, now)) == sorted(map(tuple, reopened))


def test_deck_builder_split_tiles_follow_the_owned_count():
    # Fewer copies than pictures: the deck and the collection still never repeat a picture.
    result = run_deck_builder({160: 2, 170: 1}, [160], [('in', 160), ('out', 160), ('out', 160), ('in', 170)])
    deck_tiles, collection_tiles = result['steps'][0]
    assert arts(deck_tiles, 160) == [0] and arts(collection_tiles, 160) == [1] and arts(collection_tiles, 170) == [0]
    deck_tiles, collection_tiles = result['steps'][-1]
    assert arts(deck_tiles, 160) == [] and arts(collection_tiles, 160) == [0, 1]
    assert arts(deck_tiles, 170) == [0] and arts(collection_tiles, 170) == []


def test_deck_builder_with_the_mod_off_keeps_the_stock_grouped_tiles():
    result = run_deck_builder({160: 3, 170: 2}, [160, 160, 170], [('out', 160), ('in', 160), ('in', 160)], art=False)
    expected_deck = [[[160, 2, None], [170, 1, None]], [[160, 1, None], [170, 1, None]],
                     [[160, 2, None], [170, 1, None]], [[160, 3, None], [170, 1, None]]]
    expected_collection = [[[160, 1, None], [170, 1, None]], [[160, 2, None], [170, 1, None]],
                           [[160, 1, None], [170, 1, None]], [[170, 1, None]]]
    assert [sorted(step[0]) for step in result['steps']] == expected_deck
    assert [sorted(step[1]) for step in result['steps']] == expected_collection


# Deck builder zoom (right click): the carousel gets bare card indices, one per tile of the open list.

def test_deck_builder_zoom_patches_apply_once():
    menu = deck_builder_patch('DeckBuilderMenu', deck_source('DeckBuilderMenu'))
    zoom = menu[menu.index('protected function tryZoomCard('):menu.index('protected function closeZoomCB(')]
    # The table is reset after the zoom-mode guard and filled in step with the carousel list.
    assert zoom.index('if(this.isInZoomMode)') < zoom.index('CardSlot.gwaiCarousel = [];') < zoom.index('_loc4_.push(param1.cardIndex);')
    assert '_loc4_.push(_loc6_.cardIndex);\n                     CardSlot.gwaiCarousel.push(_loc6_.data);' in zoom
    assert zoom.index('CardSlot.gwaiCarousel.push(_loc6_.data);') < zoom.index('showDialogCardTemplates(_loc4_')
    assert menu.count('gwaiCarousel') == 2
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    assert slot.count('this.gwaiTileData()') == 1 and 'public static var gwaiCarousel:Array = [];' in slot
    # The leader carousel and the tutorial carousel stay stock: they open without the table.
    leader = menu[menu.index('protected function startChooseModeLeader('):menu.index('protected function leaderChosenCb(')]
    assert 'gwai' not in leader


def run_zoom(owned, deck_cards, art=True):
    """Open the deck builder, then zoom on each list as tryZoomCard does.

    Returns, per list, the tile pictures and the carousel pictures, position by position."""
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    script = module_script()
    script += 'var tileData=new Function("data","STATE_CAROUSEL","gwaiCarousel",%s);' % json.dumps(body(slot, 'gwaiTileData'))
    script += 'gwaiDeckArt=%s;' % ('true' if art else 'false')
    script += 'for(var i of [160,170,10])templates[i]={index:i,imageLoc:{160:"nor_blue_stripes",170:"nor_siege_tower"}[i]||"x"+i,factionIdx:1,power:5,isType:()=>true};'
    script += 'var owned=%s,deckCards=%s;' % (json.dumps(owned), json.dumps(deck_cards))
    script += """
CardSlot.gwaiOwnedCopies={};var coll=[];
for(var id in owned){CardSlot.gwaiOwnedCopies[id]=owned[id];var n=owned[id]-deckCards.filter(c=>c==id).length;for(var k=0;k<n;k++)coll.push(+id);}
var dm=new Module(false),cm=new Module(true);dm.show(new Deck(deckCards));cm.show(new Deck(coll));
function zoom(m){
  var list=[],carousel=[];                                  // tryZoomCard: one entry per tile
  for(var t of m.mcCardSlotList.r){list.push(t.cardIndex);carousel.push(t.data);}
  var tiles=m.mcCardSlotList.r.map(t=>[t.cardIndex,CardSlot.gwaiDeckPicture(templates[t.cardIndex],t.data)]);
  // SlotsListCarousel.populateData: a fresh slot per index, state Carousel, no data of its own.
  var shown=list.map((id,i)=>[id,CardSlot.gwaiDeckPicture(templates[id],tileData.call({_cardState:"Carousel",index:i},null,"Carousel",carousel))]);
  return {tiles,shown};}
console.log(JSON.stringify({deck:zoom(dm),collection:zoom(cm)}));
"""
    return node(script)


def nth(shown, index):
    return [p for i, p in shown if i == index]


def test_deck_builder_zoom_shows_each_copy_as_its_tile():
    old, pictures = COPY_ART[160]
    tower = COPY_ART[170][1]
    result = run_zoom({160: 3, 170: 2, 10: 2}, [160, 160, 170, 10])
    deck, collection = result['deck'], result['collection']
    for side in (deck, collection):
        assert side['shown'] == side['tiles']
    # The deck holds copies 1..d in list order, the collection the rest counted down from the owned total.
    assert nth(deck['shown'], 160) == [pictures[0], pictures[1]]
    assert nth(collection['shown'], 160) == [pictures[2]]
    assert nth(deck['shown'], 170) == [tower[0]] and nth(collection['shown'], 170) == [tower[1]]
    assert nth(deck['shown'], 10) == ['x10'] and nth(collection['shown'], 10) == ['x10']
    # The whole deck in the collection: the n-th Blue Stripes is copy owned+1-n.
    result = run_zoom({160: 3, 170: 2}, [])
    assert nth(result['collection']['shown'], 160) == [pictures[2], pictures[1], pictures[0]]
    assert nth(result['collection']['shown'], 170) == [tower[1], tower[0]]


def test_deck_builder_zoom_cycles_when_copies_outnumber_pictures():
    pictures = COPY_ART[160][1]
    result = run_zoom({160: 5}, [160, 160, 160, 160])
    assert nth(result['deck']['shown'], 160) == [pictures[n % len(pictures)] for n in range(4)]
    assert nth(result['collection']['shown'], 160) == [pictures[4 % len(pictures)]]
    assert result['deck']['shown'] == result['deck']['tiles']


def test_deck_builder_zoom_with_the_mod_off_is_stock():
    result = run_zoom({160: 3, 170: 2}, [160, 160, 170], art=False)
    for side in ('deck', 'collection'):
        assert {p for _, p in result[side]['shown']} <= {'nor_blue_stripes', 'nor_siege_tower'}
        assert result[side]['shown'] == result[side]['tiles']


def test_deck_builder_zoom_table_only_feeds_carousel_slots_of_the_same_card():
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    script = deck_slot_script()
    script += 'var tileData=new Function("data","STATE_CAROUSEL","gwaiCarousel",%s);' % json.dumps(body(slot, 'gwaiTileData'))
    script += 'gwaiDeckArt=true;templates[160]={index:160,imageLoc:"nor_blue_stripes"};templates[126]={index:126,imageLoc:"nor_poor_infantry"};'
    script += 'var table=[{cardID:160,numCopies:1,gwaiCopy:1,gwaiArt:1}];'
    script += 'function pic(id,state,i,data){return CardSlot.gwaiDeckPicture(templates[id],tileData.call({_cardState:state,index:i},data,"Carousel",table));}'
    script += 'console.log(JSON.stringify([pic(160,"Carousel",0,null),pic(160,"Carousel",1,null),pic(160,"Default",0,null),'
    script += 'pic(160,"Carousel",0,{cardID:160,numCopies:2}),pic(126,"Carousel",0,null)]));'
    # Matching slot; position past the table; a list tile; a tile with its own data; a Tight Bond card.
    assert node(script) == ['nor_blue_stripes_1', 'nor_blue_stripes', 'nor_blue_stripes', 'nor_blue_stripes', 'nor_poor_infantry_1']
