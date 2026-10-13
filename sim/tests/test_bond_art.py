"""Card art per copy family: one picture per copy, visual only and only while the mod is On."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

import pytest
from v8_as_test import close_brace, strip_types, script_file
from v8_runtime_patch import (ALTERNATE_ART, BOND_ART, DECK_BUILDER_CLASSES, FAMILY_ART, NATIVE_CLASSES,
                              deck_builder_patch, derive_families, family_tables, parse_cards, patch)

NATIVE = ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'
DECK_BUILDER = ROOT / 'game/vanilla/as_deck_builder/scripts/red/game/witcher3/menus/gwint'
SETTINGS = ROOT / 'mod/settings/modGwentAISettings/content/scripts/local/gwai_settings.ws'
CARDS = ROOT / 'game/vanilla/xml/content0/gameplay/items/def_gwint_cards_final.xml'
# Decoded card textures (local only, never committed): one <picture>.png per texture.
TEXTURES = Path(os.environ.get('GWAI_CARD_TEXTURES', Path.home() / 'Downloads/gwent-artes-cartas/todas'))
# Every copy of each Tight Bond group and the picture it shows with the mod On.
GROUPS = {
    'Poor Fucking Infantry': {125: 'nor_poor_infantry', 126: 'nor_poor_infantry_1', 127: 'nor_poor_infantry_2'},
    'Crinfrid Reavers': {130: 'nor_crinfrid', 131: 'nor_crinfrid_1', 132: 'nor_crinfrid_2'},
    'Catapult': {140: 'nor_catapult', 141: 'nor_catapult_1'},
    'Impera Brigade': {245: 'nil_impera_brigade', 246: 'nil_impera_brigade_1', 247: 'nil_impera_brigade_2', 248: 'nil_impera_brigade_3'},
    'Nausicaa Cavalry Rider': {250: 'nil_nauzicaa', 251: 'nil_nauzicaa_1', 252: 'nil_nauzicaa_2'},
}
FAMILY_OF = {index: name for name, (members, _) in FAMILY_ART.items() for index, _ in members}
STOCK = {index: stock for members, _ in FAMILY_ART.values() for index, stock in members}
INFANTRY = FAMILY_ART['poor_infantry'][1]
KAEDWEN = FAMILY_ART['kaedweni_siege'][1]
STRIPES = FAMILY_ART['blue_stripes'][1]


def card_text():
    if not CARDS.exists():
        pytest.skip('local game card definitions not extracted')
    return CARDS.read_text(encoding='utf-8', errors='replace')


def stock_cards():
    text = card_text()
    cards = {}
    for match in re.finditer(r'<card\b(.*?)>', text, re.S):
        attrs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', match.group(1)))
        if attrs.get('index', '').isdigit():
            cards[int(attrs['index'])] = attrs
    return cards


def shown(index, picture):
    old, new = BOND_ART.get(index, (None, None))
    return new if picture == old else picture


def test_bond_table_matches_stock_definitions_and_gives_every_copy_its_own_picture():
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
        # The family lists the same pictures, in card index order.
        assert FAMILY_ART[FAMILY_OF[min(copies)]][1][:len(copies)] == tuple(copies[i] for i in sorted(copies)), name
    # Only the copies whose picture changes are in the table.
    expected = {i: p for copies in GROUPS.values() for i, p in copies.items() if cards[i]['picture'] != p}
    assert {i: new for i, (_, new) in BOND_ART.items()} == expected


def texture_names(cards):
    if TEXTURES.is_dir():
        return sorted(p.stem for p in TEXTURES.glob('*.png'))
    # Without the decoded list: the pictures the card definitions and BOND_ART name, plus the
    # verified alternates.
    return sorted({p for _, p, _ in cards.values()} | {new for _, new in BOND_ART.values()} | set(ALTERNATE_ART))


def test_family_table_is_derived_from_the_card_definitions():
    cards = parse_cards(card_text())
    assert derive_families(cards, texture_names(cards)) == FAMILY_ART
    attrs = stock_cards()
    used = {a['picture'] for a in attrs.values()}
    for name, (members, pictures) in FAMILY_ART.items():
        # One title, power and faction; non-hero units only.
        assert len({(attrs[i]['title'], attrs[i]['power'], attrs[i]['faction_index']) for i, _ in members}) == 1, name
        assert attrs[members[0][0]]['title'] == 'gwint_name_' + name
        for index, stock in members:
            assert attrs[index]['picture'] == stock
            assert 'TYPE_CREATURE' in cards[index][2] and 'TYPE_HERO' not in cards[index][2]
        assert [i for i, _ in members] == sorted(i for i, _ in members)
        assert len(pictures) >= 2 and len(set(pictures)) == len(pictures), name
        # Member pictures first, in index order, then unused alternates.
        member_pictures = []
        for index, stock in members:
            if shown(index, stock) not in member_pictures:
                member_pictures.append(shown(index, stock))
        assert list(pictures[:len(member_pictures)]) == member_pictures
        assert not set(pictures[len(member_pictures):]) & used
    # Every Tight Bond copy is in a family; heroes (Geralt, Ciri) are not.
    assert set(FAMILY_OF) >= {i for copies in GROUPS.values() for i in copies}
    assert not {7, 26, 10, 27} & set(FAMILY_OF)
    assert set(ALTERNATE_ART) == {p for _, ps in FAMILY_ART.values() for p in ps} - used - {new for _, new in BOND_ART.values()}
    if TEXTURES.is_dir():
        assert {p for _, ps in FAMILY_ART.values() for p in ps} <= set(texture_names(cards))


def test_families_the_owner_reported():
    assert FAMILY_ART['poor_infantry'] == (((125, 'nor_poor_infantry'), (126, 'nor_poor_infantry'), (127, 'nor_poor_infantry')),
                                           ('nor_poor_infantry', 'nor_poor_infantry_1', 'nor_poor_infantry_2'))
    assert KAEDWEN == ('nor_kaedwen_siege', 'nor_kaedwen_siege_1', 'nor_kaedwen_siege_2')
    assert STRIPES == ('nor_blue_stripes', 'nor_blue_stripes_1', 'nor_blue_stripes_2')
    assert FAMILY_ART['siege_tower'][1] == ('nor_siege_tower', 'nor_siege_tower_1')


def patched_slot():
    return patch('CardSlot', (NATIVE / 'CardSlot.as').read_text())


def test_card_slot_loads_the_family_picture_and_patches_once():
    assert 'CardSlot' in NATIVE_CLASSES
    source = patched_slot()
    assert 'loadIcon("icons/gwint/" + gwaiBondPicture(cardTemplate,this._instanceId) + ".png");' in source
    assert 'cardTemplate.imageLoc + ".png"' not in source
    family_of, families = family_tables()
    assert 'GWAI_FAMILY_OF:Object = %s;' % family_of in source
    assert 'GWAI_FAMILIES:Array = %s;' % families in source
    with pytest.raises(ValueError):
        patch('CardSlot', source)


def node(script):
    result = subprocess.run(['node', script_file(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def body(source, name):
    match = re.search(r'function ' + name + r'\([^)]*\)[^{]*\{', source)
    return strip_types(source[match.end():close_brace(source, match.end()) - 1]).replace(' as Array', '')


def tables(source):
    found = re.findall(r'(GWAI_FAMILY_OF):Object = (\{.*?\});', source) + re.findall(r'(GWAI_FAMILIES):Array = (\[.*?\]);', source)
    assert len(found) == 2
    return ''.join('var %s=%s;' % m for m in found)


ON = {'enabled': True, 'difficulty': 2, 'autoplay': False}
OFF = {'enabled': False, 'difficulty': 2, 'autoplay': False}


def match_script():
    """Patched CardManager copy ordinals and CardSlot pictures as JS, over fake decks and instances."""
    slot = patched_slot()
    manager = patch('CardManager', (NATIVE / 'CardManager.as').read_text())
    script = tables(slot) + 'function int(v){return v|0;}var flow=null;'
    script += 'var GwintGameFlowController={getInstance:()=>flow};'
    script += 'var CardSlot={gwaiFamilyMembers:function(index){%s}};' % body(slot, 'gwaiFamilyMembers')
    script += 'var m={_cardInstances:{},_gwaiCopy:{},playerDeckDefinitions:[{cardIndices:[]},{cardIndices:[]}]};var next=0;'
    script += 'var CardManager={getInstance:()=>m};'
    script += 'm.gwaiAssignCopy=function(card){%s};m.gwaiCopyOrdinal=function(instanceId){%s};' % (
        re.sub(r'for each\((\w+) in ([\w.]+)\)', r'for(\1 of Object.values(\2))', body(manager, 'gwaiAssignCopy')),
        body(manager, 'gwaiCopyOrdinal'))
    script += 'var pick=function(cardTemplate,instanceId){%s};' % body(slot, 'gwaiBondPicture')
    script += 'var stock=%s;' % json.dumps(STOCK)
    script += 'function spawn(t,p){var c={instanceId:++next,templateId:t,owningPlayer:p||0};m._cardInstances[c.instanceId]=c;m.gwaiAssignCopy(c);return c.instanceId;}'
    script += 'function drop(id){delete m._cardInstances[id];delete m._gwaiCopy[id];}'
    script += 'function deck(p,cards){m.playerDeckDefinitions[p].cardIndices=cards.slice();}'
    script += 'function art(id,settings){flow=settings===undefined?null:{gwaiSettingsSnapshot:()=>settings};var c=m._cardInstances[id];'
    script += 'return pick({index:c.templateId,imageLoc:stock[c.templateId]||"x"+c.templateId},id);}'
    return script


def run_match(code):
    return node(match_script() + 'var ON=%s,OFF=%s;' % (json.dumps(ON), json.dumps(OFF)) + code)


def test_match_wiring_patches_once():
    source = patch('CardManager', (NATIVE / 'CardManager.as').read_text())
    assert 'this._cardInstances[newInstance.instanceId] = newInstance;\n         this.gwaiAssignCopy(newInstance);' in source
    assert 'delete this._cardInstances[cardInstance.instanceId];\n         delete this._gwaiCopy[cardInstance.instanceId];' in source
    assert 'CardSlot.gwaiFamilyMembers(card.templateId)' in source


def test_match_two_copies_of_one_index_get_two_pictures():
    # The owner's Poor Fucking Infantry x2, both index 125.
    out = run_match('deck(0,[125,125,10]);var a=spawn(125),b=spawn(125);console.log(JSON.stringify([art(a,ON),art(b,ON)]));')
    assert out == [INFANTRY[0], INFANTRY[1]]


def test_match_three_copies_of_kaedweni_siege_index_150():
    out = run_match('deck(0,[150,150,150]);var ids=[spawn(150),spawn(150),spawn(150)];'
                    'console.log(JSON.stringify(ids.map(id=>art(id,ON))));')
    assert out == list(KAEDWEN)


def test_match_mixed_indices_order_by_index_then_copy():
    # 125, 125 and 126 drawn in any order: the 125s take 0 and 1, the 126 takes 2.
    out = run_match('deck(0,[126,125,125]);var c=spawn(126),a=spawn(125),b=spawn(125);'
                    'console.log(JSON.stringify([art(a,ON),art(b,ON),art(c,ON),m.gwaiCopyOrdinal(c)]));')
    assert out == [INFANTRY[0], INFANTRY[1], INFANTRY[2], 2]
    # A lone 126 starts the family: no other copy, no duplicate to avoid.
    out = run_match('deck(0,[126]);var c=spawn(126);console.log(JSON.stringify([art(c,ON)]));')
    assert out == [INFANTRY[0]]


def test_match_cycles_only_when_pictures_run_out():
    out = run_match('deck(0,[160,160,160,160]);var ids=[spawn(160),spawn(160),spawn(160),spawn(160)];'
                    'console.log(JSON.stringify(ids.map(id=>art(id,ON))));')
    assert out == [STRIPES[0], STRIPES[1], STRIPES[2], STRIPES[0]]
    out = run_match('deck(0,[150,150,150,151]);var ids=[spawn(151),spawn(150),spawn(150),spawn(150)];'
                    'console.log(JSON.stringify(ids.map(id=>[m.gwaiCopyOrdinal(id),art(id,ON)])));')
    assert out == [[3, KAEDWEN[0]], [0, KAEDWEN[0]], [1, KAEDWEN[1]], [2, KAEDWEN[2]]]


def test_match_ordinals_are_per_owner_and_reuse_freed_slots():
    code = 'deck(0,[125,125,126]);deck(1,[125,126]);'
    code += 'var a=spawn(125,0),n1=spawn(126,1),b=spawn(125,0),n2=spawn(125,1),x=spawn(10,0);'
    code += 'var out=[a,b,n1,n2,x].map(id=>m.gwaiCopyOrdinal(id));'
    # The first 125 goes back to the deck (exchange) and comes back: it takes the free ordinal.
    code += 'drop(a);var a2=spawn(125,0);out.push(m.gwaiCopyOrdinal(a2));'
    # Exchange while the old copy is still alive (the new card spawns first): the new copy takes
    # an ordinal past the family's deck total, so it never repeats the 126's picture.
    code += 'drop(a2);drop(b);deck(0,[125,126]);var p=spawn(125,0),q=spawn(125,0);drop(p);var r=spawn(126,0);'
    code += 'out.push(m.gwaiCopyOrdinal(p),m.gwaiCopyOrdinal(q),m.gwaiCopyOrdinal(r));console.log(JSON.stringify(out));'
    assert run_match(code) == [0, 1, 1, 0, -1, 0, -1, 2, 1]


def test_match_stock_art_when_off_or_unsafe():
    code = 'deck(0,[125,125]);var a=spawn(125),b=spawn(125);'
    code += 'var out=[art(b,OFF),art(b,undefined),art(b,null)];'
    # Template-only slot, no ordinal recorded, another mod's picture, a card outside the families.
    code += 'flow={gwaiSettingsSnapshot:()=>ON};out.push(pick({index:125,imageLoc:"nor_poor_infantry"},-1));'
    code += 'out.push(pick({index:125,imageLoc:"nor_poor_infantry"},999));'
    code += 'out.push(pick({index:125,imageLoc:"other_mod_art"},b));'
    code += 'var h=spawn(7);out.push(art(h,ON),m.gwaiCopyOrdinal(h));console.log(JSON.stringify(out));'
    assert run_match(code) == ['nor_poor_infantry'] * 5 + ['other_mod_art', 'x7', -1]


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
    family_of, families = family_tables()
    assert 'GWAI_FAMILY_OF:Object = %s;' % family_of in slot and 'GWAI_FAMILIES:Array = %s;' % families in slot
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
    script = 'function int(v){return v|0;}' + tables(slot)
    script += 'var gwaiDeckArt=false,templates={};'
    script += 'var CardManager={getInstance:()=>({getCardTemplate:i=>templates[i]||null})};'
    script += 'var CardSlot={gwaiOwnedCopies:{}};'
    for name in ('gwaiFamilyMembers', 'gwaiCopyPictures', 'gwaiDeckPicture'):
        params = strip_types(re.search(r'function ' + name + r'\(([^)]*)\)', slot).group(1), True)
        script += 'CardSlot.%s=function(%s){%s};' % (name, params, body(slot, name))
    return script


def template_script(indices):
    pictures = {i: STOCK.get(i, 'x%d' % i) for i in indices}
    return 'var pics=%s;for(var i in pics)templates[i]={index:+i,imageLoc:pics[i],factionIdx:1,power:5,isType:()=>true};' % json.dumps(pictures)


def run_deck_picture(cases):
    """Each case: art switch (or None when the switch never arrived), index, picture, optional tile data."""
    script = deck_slot_script() + 'var out=[];'
    script += 'for(var c of %s){gwaiDeckArt=c[0]===null?false:c[0];' % json.dumps(cases)
    script += 'out.push(CardSlot.gwaiDeckPicture({index:c[1],imageLoc:c[2]},c.length>3?c[3]:null));}'
    script += 'console.log(JSON.stringify(out));'
    return node(script)


@pytest.mark.parametrize('index', sorted(FAMILY_OF))
def test_deck_builder_tiles_take_their_family_art(index):
    old, pictures = STOCK[index], FAMILY_ART[FAMILY_OF[index]][1]
    cases = [[True, index, old, dict(cardID=index, numCopies=1, gwaiCopy=0, gwaiArt=a)] for a in range(len(pictures) + 1)]
    expected = list(pictures) + [pictures[0]]                    # a further copy cycles
    stock = [
        [False, index, old, dict(cardID=index, numCopies=1, gwaiCopy=0, gwaiArt=1)],     # Off
        [None, index, old, dict(cardID=index, numCopies=1, gwaiCopy=0, gwaiArt=1)],      # switch never sent
        [True, index, old, dict(cardID=index, numCopies=3)],                              # grouped tile
        [True, index, old, None],                                                         # no tile data (zoom, leader)
        [True, index, old, dict(cardID=999, numCopies=1, gwaiCopy=1, gwaiArt=1)],         # stale data of another card
        [True, index, 'other_mod_art', dict(cardID=index, numCopies=1, gwaiCopy=1, gwaiArt=1)],
    ]
    assert run_deck_picture(cases + stock) == expected + [old] * 5 + ['other_mod_art']


def test_deck_builder_leaves_other_cards_alone():
    cases = [[True, i, p, dict(cardID=i, numCopies=1, gwaiCopy=0, gwaiArt=1)] for i, p in [(7, 'neu_geralt'), (1001, 'leader'), (1, 'x')]]
    assert run_deck_picture(cases) == [c[2] for c in cases]


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
function tiles(m){return m.mcCardSlotList.r.map(t=>[t.data.cardID,t.data.numCopies,t.data.gwaiArt===undefined?null:t.data.gwaiArt,t.data.gwaiCopy===undefined?null:t.data.gwaiCopy]);}
"""
    return script


def run_deck_builder(owned, deck_cards, moves, art=True):
    """Open the deck builder, then move cards ('in' = collection -> deck, 'out' = deck -> collection).

    Returns the tiles of both lists after each step and the tiles a fresh reopen draws at the end."""
    script = module_script()
    script += 'gwaiDeckArt=%s;' % ('true' if art else 'false')
    script += template_script(set(owned) | {10, 11})
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


def arts(tiles, indices):
    indices = {indices} if isinstance(indices, int) else set(indices)
    return sorted(t[2] for t in tiles if t[0] in indices)


def check_moves(owned, deck_cards, moves, families):
    """Every step: one tile per copy, counts per index as the deck's, and per family the deck holds
    ordinals 0..d-1 (by card index, then copy) and the collection the rest of 0..owned-1."""
    result = run_deck_builder(owned, deck_cards, moves)
    deck = {i: deck_cards.count(i) for i in owned}
    for step, (deck_tiles, collection_tiles) in enumerate(result['steps']):
        if step:
            direction, index = moves[step - 1]
            deck[index] += 1 if direction == 'in' else -1
        for members in families:
            for index in members:
                if index not in owned:
                    continue
                assert len(arts(deck_tiles, index)) == deck[index], (step, index)
                assert len(arts(collection_tiles, index)) == owned[index] - deck[index], (step, index)
                assert all(t[1] == 1 for t in deck_tiles + collection_tiles if t[0] == index)
            d = sum(deck.get(i, 0) for i in members)
            total = sum(owned.get(i, 0) for i in members)
            ordered = [t[2] for t in sorted((t for t in deck_tiles if t[0] in members), key=lambda t: (t[0], t[3]))]
            assert ordered == list(range(d)), (step, members)
            assert sorted(arts(deck_tiles, members) + arts(collection_tiles, members)) == list(range(total)), (step, members)
    assert sorted(result['deck']) == sorted(i for i, n in deck.items() for _ in range(n))
    # Leaving and reopening draws the same tiles (order within a card aside).
    final = result['steps'][-1]
    for now, reopened in zip(final, result['reopen']):
        assert sorted(map(tuple, now)) == sorted(map(tuple, reopened))
    return result


def test_deck_builder_shows_one_tile_per_copy_and_moves_keep_counts_and_art_consistent():
    owned = {160: 3, 170: 2, 10: 2}
    moves = [('out', 160), ('out', 160), ('in', 160), ('out', 170), ('out', 160), ('out', 160), ('in', 160), ('in', 160),
             ('in', 160), ('in', 170), ('out', 10), ('in', 10)]
    result = check_moves(owned, [160, 160, 160, 170, 170, 10], moves, [(160,), (170,)])
    count = 1
    for step, (deck_tiles, _) in enumerate(result['steps']):
        if step and moves[step - 1][1] == 10:
            count += 1 if moves[step - 1][0] == 'in' else -1
        # Other cards keep the stock grouped tile.
        assert [t for t in deck_tiles if t[0] == 10] == ([[10, count, None, None]] if count else [])


def test_deck_builder_splits_two_copies_of_index_125():
    result = check_moves({125: 2}, [], [('in', 125), ('in', 125), ('out', 125), ('out', 125)], [(125, 126, 127)])
    deck_tiles, collection_tiles = result['steps'][0]
    assert [t[:2] for t in collection_tiles] == [[125, 1], [125, 1]] and arts(collection_tiles, 125) == [0, 1]
    deck_tiles, collection_tiles = result['steps'][2]
    assert arts(deck_tiles, 125) == [0, 1] and collection_tiles == []


def test_deck_builder_splits_three_copies_of_index_150():
    result = check_moves({150: 3}, [150, 150, 150], [('out', 150), ('in', 150), ('out', 150), ('out', 150), ('out', 150)],
                         [(150, 151, 152)])
    deck_tiles, _ = result['steps'][0]
    assert [t[:3] for t in deck_tiles] == [[150, 1, 0], [150, 1, 1], [150, 1, 2]]
    _, collection_tiles = result['steps'][-1]
    assert arts(collection_tiles, 150) == [0, 1, 2]


def test_deck_builder_mixed_family_keeps_every_picture_once():
    owned = {125: 2, 126: 1, 127: 1, 10: 1}
    moves = [('in', 126), ('in', 125), ('in', 127), ('in', 125), ('out', 126), ('out', 125), ('in', 126), ('out', 127),
             ('out', 125), ('out', 126), ('in', 127), ('in', 125)]
    check_moves(owned, [], moves, [(125, 126, 127)])
    check_moves(owned, [125, 126, 10], [('out', 125), ('in', 127), ('in', 125)], [(125, 126, 127)])


def test_deck_builder_with_the_mod_off_keeps_the_stock_grouped_tiles():
    result = run_deck_builder({160: 3, 125: 2}, [160, 160, 125], [('out', 160), ('in', 160), ('in', 160), ('in', 125)], art=False)
    expected_deck = [[[125, 1, None, None], [160, 2, None, None]], [[125, 1, None, None], [160, 1, None, None]],
                     [[125, 1, None, None], [160, 2, None, None]], [[125, 1, None, None], [160, 3, None, None]],
                     [[125, 2, None, None], [160, 3, None, None]]]
    expected_collection = [[[125, 1, None, None], [160, 1, None, None]], [[125, 1, None, None], [160, 2, None, None]],
                           [[125, 1, None, None], [160, 1, None, None]], [[125, 1, None, None]], []]
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


def run_zoom(owned, deck_cards, art=True, moves=()):
    """Open the deck builder, move cards, then zoom on each list as tryZoomCard does.

    Returns, per list, the tile pictures and the carousel pictures, position by position."""
    slot = deck_builder_patch('CardSlot', deck_source('CardSlot'))
    script = module_script()
    script += 'var tileData=new Function("data","STATE_CAROUSEL","gwaiCarousel",%s);' % json.dumps(body(slot, 'gwaiTileData'))
    script += 'gwaiDeckArt=%s;' % ('true' if art else 'false')
    script += template_script(set(owned) | {10})
    script += 'var owned=%s,deckCards=%s,moves=%s;' % (json.dumps(owned), json.dumps(deck_cards), json.dumps(list(moves)))
    script += """
CardSlot.gwaiOwnedCopies={};var coll=[];
for(var id in owned){CardSlot.gwaiOwnedCopies[id]=owned[id];var n=owned[id]-deckCards.filter(c=>c==id).length;for(var k=0;k<n;k++)coll.push(+id);}
var deck=new Deck(deckCards),collection=new Deck(coll),dm=new Module(false),cm=new Module(true);dm.show(deck);cm.show(collection);
for(var [dir,id] of moves){
  if(dir=='out'){collection.dbAddCard(id);deck.dbRemoveCard(id);}
  else{collection.dbRemoveCard(id);deck.dbAddCard(id);}}
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


def nth(shown, indices):
    indices = {indices} if isinstance(indices, int) else set(indices)
    return [p for i, p in shown if i in indices]


def test_deck_builder_zoom_shows_each_copy_as_its_tile():
    tower = FAMILY_ART['siege_tower'][1]
    result = run_zoom({160: 3, 170: 2, 10: 2}, [160, 160, 170, 10])
    deck, collection = result['deck'], result['collection']
    for side in (deck, collection):
        assert side['shown'] == side['tiles']
    # The deck holds copies 1..d in list order, the collection the rest counted down from the owned total.
    assert nth(deck['shown'], 160) == [STRIPES[0], STRIPES[1]]
    assert nth(collection['shown'], 160) == [STRIPES[2]]
    assert nth(deck['shown'], 170) == [tower[0]] and nth(collection['shown'], 170) == [tower[1]]
    assert nth(deck['shown'], 10) == ['x10'] and nth(collection['shown'], 10) == ['x10']
    # The whole deck in the collection: the n-th Blue Stripes is copy owned+1-n.
    result = run_zoom({160: 3, 170: 2}, [])
    assert nth(result['collection']['shown'], 160) == [STRIPES[2], STRIPES[1], STRIPES[0]]
    assert nth(result['collection']['shown'], 170) == [tower[1], tower[0]]


def test_deck_builder_zoom_matches_family_tiles():
    result = run_zoom({125: 2, 126: 1, 150: 3}, [125, 125, 150, 150, 150])
    deck, collection = result['deck'], result['collection']
    for side in (deck, collection):
        assert side['shown'] == side['tiles']
    assert nth(deck['shown'], (125, 126, 127)) == [INFANTRY[0], INFANTRY[1]]
    assert nth(collection['shown'], (125, 126, 127)) == [INFANTRY[2]]
    assert nth(deck['shown'], 150) == list(KAEDWEN)
    # After moves (tiles added at the end, other family tiles renumbered) the zoom still follows.
    result = run_zoom({125: 2, 126: 1}, [126], moves=[('in', 125), ('out', 126), ('in', 125)])
    for side in ('deck', 'collection'):
        assert result[side]['shown'] == result[side]['tiles']
    assert sorted(nth(result['deck']['shown'], (125, 126))) == sorted(INFANTRY[:2])
    assert nth(result['collection']['shown'], (125, 126)) == [INFANTRY[2]]


def test_deck_builder_zoom_cycles_when_copies_outnumber_pictures():
    result = run_zoom({160: 5}, [160, 160, 160, 160])
    assert nth(result['deck']['shown'], 160) == [STRIPES[n % len(STRIPES)] for n in range(4)]
    assert nth(result['collection']['shown'], 160) == [STRIPES[4 % len(STRIPES)]]
    assert result['deck']['shown'] == result['deck']['tiles']


def test_deck_builder_zoom_with_the_mod_off_is_stock():
    result = run_zoom({160: 3, 170: 2, 125: 2}, [160, 160, 170, 125], art=False)
    for side in ('deck', 'collection'):
        assert {p for _, p in result[side]['shown']} <= {'nor_blue_stripes', 'nor_siege_tower', 'nor_poor_infantry'}
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
    # Matching slot; position past the table; a list tile; a tile with its own data; another card.
    assert node(script) == ['nor_blue_stripes_1', 'nor_blue_stripes', 'nor_blue_stripes', 'nor_blue_stripes', 'nor_poor_infantry']
