"""Execute draft WS arithmetic through a restricted JS adapter, not the engine.

Checks the actual wrapper bodies across all native/mod settings. Game controller
dispatch and WitcherScript compilation remain separate acceptance requirements.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
from gwentsim.options import Difficulty, normalize_settings

BASE = [145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 205, 215, 220, 225, 230]


def body(source, name):
    start = source.index('{', source.index('function ' + name + '('))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    result = source[start + 1:end - 1]
    return re.sub(r'var (\w+) : int;', r'var \1 = 0;', result)


@pytest.fixture(scope='module')
def cases():
    source = (ROOT / 'mod/settings/modGwentAISettings/content/scripts/local/gwai_betting.ws').read_text()
    generate, requirement = body(source, 'GenerateDifficultyData'), body(source, 'GetDifficulty')
    script = '''
    const BASE = %s;
    const Min = Math.min, Max = Math.max;
    Array.prototype.Clear = function() { this.length = 0; };
    Array.prototype.Resize = function(n) { this.length = n; this.fill(0); };
    Array.prototype.Size = function() { return this.length; };
    let enabled, modLevel, nativeLevel, difficulty, difficultybalance, gwaiStakeStageForMatch;
    function GwaiSettingsEnabled() { return enabled; }
    function GwaiSettingsDifficulty() { return modLevel; }
    function wrappedMethod(index) {
        if (index === undefined) {
            difficulty = nativeLevel;
            difficultybalance = BASE.map(v => v + (nativeLevel === 1 ? 80 : nativeLevel === 3 ? -80 : 0));
            return;
        }
        return difficultybalance.length < index + 1 ? difficultybalance[index - 1] : 0;
    }
    function generate() { %s }
    function requirement(diffIndex) { %s }
    let result = [];
    for (enabled of [false, true]) for (modLevel of [0,1,2,3])
    for (nativeLevel of [0,1,2,3]) for (gwaiStakeStageForMatch of [0,1,2,3]) {
        generate();
        result.push({enabled, modLevel, nativeLevel, stage:gwaiStakeStageForMatch,
            difficulty, values:Array.from({length:15}, (_,i) => requirement(i+1)),
            invalid:[requirement(-1),requirement(0),requirement(16)]});
    }
    process.stdout.write(JSON.stringify(result));
    ''' % (json.dumps(BASE), generate, requirement)
    completed = subprocess.run(['node', _js_file(script)], text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def test_enabled_applies_intended_requirements_and_ignores_native_difficulty(cases):
    # Better AI selects the deck variant by its own level and repairs the vanilla inverted
    # check: every level uses its requirement against the player's deck strength.
    for case in cases:
        if not case['enabled'] or case['stage']:
            continue
        deck_variant = min(case['modLevel'] + 1, 3)
        offset = {1:80, 2:0, 3:-80}[deck_variant]
        assert case['difficulty'] == deck_variant
        assert case['values'] == [v + offset for v in BASE]


def test_enabled_highest_stakes_gives_every_extra_card(cases):
    for case in cases:
        if case['enabled'] and case['stage'] == 3:
            assert case['values'] == [0] * 15


def test_enabled_guards_one_based_array_bounds(cases):
    assert all(case['invalid'] == [0, 0, 0] for case in cases if case['enabled'])


@pytest.mark.parametrize('level', range(4))
def test_actual_flash_deck_gate_at_every_threshold(cases, level):
    # Execute the repository vanilla Flash gate against corrected WS outputs.
    # This is source execution through JS, not a live Flash/WS integration test.
    sys.path.insert(0, str(ROOT / 'tools'))
    from v8_as_test import close_brace, strip_types
    source = (ROOT / 'game/vanilla/as/scripts/red/game/witcher3/menus/gwint/GwintDeck.as').read_text()
    start = source.index('{', source.index('function adjustDeckToDifficulty(')) + 1
    gate = strip_types(source[start:close_brace(source, start) - 1])
    script = 'const CardManager={log:()=>{}};var gate=function(otherDeckStr,listToAddTo){' + gate + '};var out=[];'
    expected = []
    for case in cases:
        if not case['enabled'] or case['stage'] or case['modLevel'] != level:
            continue
        for index, threshold in enumerate(case['values'], 1):
            for strength in (threshold - 1, threshold, threshold + 1):
                script += ('var deck={dynamicCardRequirements:[%d],dynamicCards:[%d]};'
                           'var added=[];gate.call(deck,%d,added);out.push(added);') % (threshold, index, strength)
                expected.append([index] if strength >= threshold else [])
    script += 'console.log(JSON.stringify(out));'
    result = subprocess.run(['node', _js_file(script)], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == expected


def test_off_preserves_native_behavior_without_ai_override(cases):
    for case in cases:
        if case['enabled'] or case['stage']:
            continue
        offset = {1:80, 3:-80}.get(case['nativeLevel'], 0)
        assert case['difficulty'] == case['nativeLevel']
        assert case['values'] == [0] * 14 + [230 + offset]


def test_explicit_stakes_option_survives_without_native_dependency(cases):
    for case in cases:
        if not case['enabled'] or not case['stage']:
            continue
        variant = max(min(case['modLevel'] + 1, 3), 2)
        if case['stage'] >= 2:
            variant = 3
        assert case['difficulty'] == variant
        assert case['values'][-1] == (0 if case['stage'] >= 3 else 150 if variant == 3 else 230)
        matches = [c for c in cases if c['enabled'] and c['modLevel'] == case['modLevel'] and c['stage'] == case['stage']]
        assert all(c['values'] == case['values'] and c['difficulty'] == variant for c in matches)


@pytest.mark.parametrize('difficulty', list(Difficulty))
@pytest.mark.parametrize('native', ['0', '1', '2', '3'])
def test_both_side_profile_contract_ignores_native(difficulty, native):
    raw = dict(GwaiEnabled='true', GwaiDifficulty=str(int(difficulty)),
               GwaiAutoPlay='true', gwent_difficulty=native)
    options, writes = normalize_settings(raw)
    assert not writes
    assert options.requested_profile.difficulty == difficulty
    assert options.requested_player_profile is options.requested_profile
    assert raw['gwent_difficulty'] == native
    raw['GwaiEnabled'] = 'false'
    inactive, writes = normalize_settings(raw)
    assert not writes
    assert inactive.requested_profile is None and inactive.requested_player_profile is None


def _js_file(script):
    """Temporary file holding `script` (node -e hits the argument size limit)."""
    import hashlib, tempfile
    path = Path(tempfile.gettempdir()) / ('gwai-ws-%s.js' % hashlib.sha256(script.encode()).hexdigest()[:20])
    if not path.exists():
        path.write_text(script)
    return str(path)
