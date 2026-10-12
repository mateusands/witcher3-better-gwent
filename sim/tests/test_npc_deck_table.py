"""The in-game NPC deck table (gwai_npc_decks_data.ws) gives the simulator's decks.

The table is read here the way gwai_npc_decks.ws reads it (one Adaptive hero variant per match,
"#"-separated; first Adaptive step whose strength reaches the target, "-i"/"+i" changes), and the
script's deck-strength bonuses must match npc_balance.STRENGTH_BONUS.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
sys.path.insert(0, str(ROOT / 'tools'))

from build_npc_decks import table  # noqa: E402
from evaluate_pool import XML, setup  # noqa: E402
from blunder_hunter import card_names  # noqa: E402
from gwentsim.native_decks import NativeDecks  # noqa: E402
from gwentsim import npc_balance as nb  # noqa: E402

SCRIPTS = ROOT / 'mod/settings/modGwentAISettings/content/scripts/local'


def apply(cards, body):
    for token in body.split(','):
        if token.startswith('-'):
            cards.remove(int(token[1:]))
        elif token.startswith('+'):
            cards.append(int(token[1:]))
        else:
            cards.append(int(token))
    return cards


def adaptive(steps, target):
    cards = []
    for step in steps.split('|'):
        strength, body = step.split(':', 1)
        apply(cards, body)
        if int(strength) >= target:
            break
    return cards


def pick(choices, n):
    """GwaiNpcDeckPick: the n-th "#"-separated variant, else the last one."""
    parts = choices.split('#')
    return parts[min(n, len(parts) - 1)]


def test_generated_script_is_current():
    text = (SCRIPTS / 'gwai_npc_decks_data.ws').read_text()
    for key, strong, steps in table():
        assert '"%s"' % key in text and strong in text and steps in text


def test_table_matches_simulator_decks():
    match = setup()['match']
    templates, names = match.templates, card_names()
    native = NativeDecks(XML, templates)
    rows = {key: (strong, steps) for key, strong, steps in table()}
    checked = 0
    for name in native.npc_names():
        for variant in sorted({int(d.attrib['difficulty']) for d in native.collections[name].findall('deck')}):
            deck = native.build(name, variant, repaired=True)
            strong, steps = rows['%s:%d' % (name, variant)]
            assert sorted(apply([], strong)) == sorted(nb.apply_mode(templates, deck, names, 'strong').card_indices)
            assert len(steps.split('#')) == nb.HERO_VARIANTS
            for hero_variant in range(nb.HERO_VARIANTS):
                for target in range(100, 380, 7):
                    expected = nb.balanced_deck(templates, deck, names, target, variant=hero_variant)
                    assert sorted(adaptive(pick(steps, hero_variant), target)) == sorted(expected), \
                        (name, variant, hero_variant, target)
                    checked += 1
    assert checked > 15000


def test_script_draws_every_hero_variant():
    text = (SCRIPTS / 'gwai_npc_decks.ws').read_text()
    assert 'GwaiNpcDeckPick(adaptive, RandRange(%d))' % nb.HERO_VARIANTS in text
    assert pick('a#b#c', 0) == 'a' and pick('a#b#c', 2) == 'c' and pick('a', 2) == 'a'


def test_script_strength_bonuses_match_simulator():
    text = (SCRIPTS / 'gwai_npc_decks.ws').read_text()
    body = text[text.index('function GwaiDeckStrength'):text.index('// Applies')]
    found = {}
    for effects, bonus in re.findall(r'if \(([^)]*)\) \{ total \+= (\d+); \}', body):
        for effect in re.findall(r'effect == (\d+)', effects):
            found[int(effect)] = int(bonus)
    assert found == nb.STRENGTH_BONUS
    assert '(card.typeFlags & %d) == %d' % (nb.C.CardType_Creature, nb.C.CardType_Creature) in body


def test_script_difficulty_targets_match_simulator():
    text = (SCRIPTS / 'gwai_npc_decks.ws').read_text()
    factors = dict((int(d), float(f)) for d, f in re.findall(r'if \(difficulty == (\d)\) \{ factor = ([\d.]+); \}', text))
    factors.setdefault(1, 1.0)   # Normal keeps the script's default factor
    # The mod has three levels (Easy, Normal, Hard); the simulator's Expert is Hard's target.
    assert tuple(factors[d] for d in range(3)) == nb.BALANCED_TARGET[:3]
    assert nb.BALANCED_TARGET[3] == nb.BALANCED_TARGET[2]


def test_scripts_read_struct_fields_from_variables():
    # 5.01: "Cannot access struct property ... Parent scope does not come from variable".
    for path in SCRIPTS.glob('gwai_*.ws'):
        text = path.read_text()
        assert not re.search(r'\)\.(cards|deckName|difficulty|leaderCard|specialCard|power|typeFlags|effectFlags)\b', text), path.name


def test_excluded_cards_never_in_npc_decks():
    names = card_names()
    excluded = {i for i, n in names.items() if n in nb.EXCLUDED}
    assert excluded
    for key, strong, steps in table():
        assert not excluded & set(apply([], strong)), key
        for choice in steps.split('#'):
            cards = []
            for step in choice.split('|'):
                apply(cards, step.split(':', 1)[1])
                assert not excluded & set(cards), key
