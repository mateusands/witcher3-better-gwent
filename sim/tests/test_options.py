"""Persistent choices, fallback behavior and per-match configuration isolation."""
import json
import struct
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
sys.path.insert(0, str(ROOT / 'tools'))
from gwentsim.options import Difficulty, normalize_settings
from build_settings import build, key_hash
from metastore import rcint


def test_defaults_and_idempotent_initialization():
    raw = {'gwent_difficulty': '1', 'OtherOption': 'keep'}
    options, writes = normalize_settings(raw)
    assert options.difficulty is Difficulty.HARD and not options.enabled
    assert options.requested_profile is None
    assert writes == {'GwaiEnabled': 'false', 'GwaiDifficulty': '2', 'GwaiAutoPlay': 'false'}
    raw.update(writes)
    assert raw['gwent_difficulty'] == '1' and raw['OtherOption'] == 'keep'
    assert normalize_settings(raw)[1] == {}


def test_switch_preserves_every_saved_difficulty():
    for difficulty in Difficulty:
        raw = {'GwaiEnabled': 'true', 'GwaiDifficulty': str(int(difficulty)), 'GwaiAutoPlay': 'false'}
        active, writes = normalize_settings(raw)
        assert not writes
        assert active.requested_profile.difficulty == difficulty
        raw['GwaiEnabled'] = 'false'
        inactive, writes = normalize_settings(raw)
        assert not writes and inactive.requested_profile is None
        assert inactive.difficulty == difficulty and not inactive.difficulty_control_enabled
        raw['GwaiEnabled'] = 'true'
        assert normalize_settings(raw)[0] == active


def test_invalid_difficulty_falls_back_without_disabling_mod():
    for invalid in (None, '', '-1', '4', 'easy', '2.0', '02'):
        options, writes = normalize_settings({'GwaiEnabled': 'true', 'GwaiDifficulty': invalid, 'GwaiAutoPlay': 'false'})
        assert options.enabled and options.difficulty is Difficulty.HARD
        assert writes == {'GwaiDifficulty': '2'}


def test_match_snapshot_survives_later_menu_changes():
    raw = {'GwaiEnabled': 'true', 'GwaiDifficulty': '2', 'GwaiAutoPlay': 'true'}
    current, _ = normalize_settings(raw)
    raw.update(GwaiEnabled='false', GwaiDifficulty='3', GwaiAutoPlay='false')
    next_match, _ = normalize_settings(raw)
    assert current.enabled and current.difficulty is Difficulty.HARD
    assert current.autoplay_active and current.requested_player_profile is current.requested_profile
    assert not next_match.enabled and next_match.difficulty is Difficulty.EXPERT
    assert not next_match.autoplay_active and next_match.requested_player_profile is None
    try:
        current.enabled = False
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError('active match settings are mutable')


def test_menu_labels_resolve_through_compiled_key_hash_table():
    labels = json.loads((ROOT / 'mod/settings/menu/labels.en.json').read_text())
    binary = build(labels)
    assert binary[:10] == b'RTSW' + struct.pack('<IH', 164, 0)
    count, pos = rcint(binary, 10)
    table = {}
    for i in range(count):
        sid, offset, length = struct.unpack_from('<III', binary, pos + i * 12)
        table[sid] = (offset, length)
    pos += count * 12
    count, pos = rcint(binary, pos)
    hashes = [struct.unpack_from('<II', binary, pos + i * 8) for i in range(count)]
    assert hashes == sorted(hashes)
    pos += count * 8
    length, pos = rcint(binary, pos)
    blob = binary[pos:pos + length]
    resolved = {}
    for key, text in labels.items():
        sid = dict(hashes)[key_hash(key)]
        offset, size = table[sid]
        resolved[key] = blob[offset:offset + size].decode('ascii')
        assert resolved[key] == text
    xml = ET.parse(ROOT / 'mod/settings/menu/modGwentAI.xml')
    for var in xml.findall('.//Var'):
        assert 'option_' + var.attrib['displayName'] in resolved
    for option in xml.findall('.//Option'):
        assert 'preset_value_' + option.attrib['displayName'] in resolved
    assert [int(e.attrib['value']) for e in xml.findall('.//Var[@id="GwaiDifficulty"]//Entry')] == [int(d) for d in Difficulty]


def test_autoplay_uses_selected_profile_on_both_sides_and_survives_main_switch():
    for difficulty in Difficulty:
        raw = {'GwaiEnabled': 'true', 'GwaiDifficulty': str(int(difficulty)), 'GwaiAutoPlay': 'true'}
        active, writes = normalize_settings(raw)
        assert not writes and active.autoplay_active and active.autoplay_control_enabled
        assert active.requested_player_profile is active.requested_profile
        assert active.requested_player_profile.difficulty == difficulty
        raw['GwaiEnabled'] = 'false'
        inactive, writes = normalize_settings(raw)
        assert not writes and inactive.autoplay
        assert not inactive.autoplay_active and not inactive.autoplay_control_enabled
        assert inactive.requested_player_profile is None
        raw['GwaiEnabled'] = 'true'
        assert normalize_settings(raw)[0] == active


def test_autoplay_defaults_off_and_normalizes_aliases():
    for raw_value in (None, '', 'false', '0', 'invalid', 'true', '1'):
        raw = {'GwaiEnabled': 'true', 'GwaiDifficulty': '2'}
        if raw_value is not None:
            raw['GwaiAutoPlay'] = raw_value
        options, writes = normalize_settings(raw)
        expected = raw_value in ('true', '1')
        assert options.autoplay is expected and options.autoplay_active is expected
        assert (options.requested_player_profile is not None) is expected
        raw.update(writes)
        assert raw['GwaiAutoPlay'] == ('true' if expected else 'false')
        assert not normalize_settings(raw)[1]
