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
from v8_runtime_patch import BOND_ART, COPY_ART, NATIVE_CLASSES, patch

NATIVE = ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint'
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
