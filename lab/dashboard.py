#!/usr/bin/env python3
"""Dashboard images for the README: KPI tiles and comparison charts as static SVG.

    python3 lab/dashboard.py DB [DB ...] [--records game/records] [--evaluations game/evaluations]

Reads Lab databases (give each database once), writes docs/img/<chart>-light.svg and
<chart>-dark.svg; the README picks the variant matching the reader's GitHub theme.
Re-run whenever new results arrive. Colours: blue/orange categorical pair validated for
colour-vision deficiency in both themes; every value is also written as text.
"""
import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import report  # noqa: E402

FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
THEMES = {
    'light': dict(surface='#ffffff', border='#d0d7de', ink='#1f2328', ink2='#59636e',
                  grid='#e6e8eb', ref='#8c959f', s1='#2a78d6', s2='#eb6834', s3='#1baf7a'),
    'dark': dict(surface='#161b22', border='#30363d', ink='#f0f6fc', ink2='#9198a1',
                 grid='#262c36', ref='#6e7681', s1='#3987e5', s2='#d95926', s3='#199e70'),
}
WIDTH = 880
PROFILES = ['easy', 'medium', 'hard', 'expert']
# The mod's levels since 0.9.0: profile "medium" is shown as Normal; Expert is simulator-only.
LEVEL_NAMES = {'easy': 'Easy', 'medium': 'Normal', 'hard': 'Hard', 'expert': 'Expert'}
STYLE_LABELS = [('early', 'Early-game decks'), ('random', 'Random decks'), ('recorded', 'My real decks'),
                ('power', 'Power decks'), ('synergy', 'Synergy decks'), ('all', 'All player decks')]


# ---- data -------------------------------------------------------------------

def score(won, winner):
    return 1.0 if won else 0.5 if winner not in (0, 1) else 0.0


def collect(dbs):
    levels = defaultdict(lambda: [0.0, 0])          # profile -> [Better AI score, games]
    styles = defaultdict(lambda: [0.0, 0.0, 0])     # style -> [Better AI, native, games]
    rounds = defaultdict(int)
    style_of = None
    for path in dbs:
        db = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        for kind, params, payload, result in db.execute(
                "SELECT j.kind, j.params, t.payload, t.result FROM tasks t JOIN jobs j ON j.id=t.job_id "
                "WHERE t.status='done'"):
            params, p, r = json.loads(params), json.loads(payload), json.loads(result)
            if kind in report.HUNTS:
                for f in r.get('findings', []):
                    rounds[f['round']] += 1
                continue
            if kind != 'benchmark' or params.get('policy') != 'response-v8' or params.get('weights') \
                    or params.get('npc_decks'):
                continue                             # tuning, A/B variants and deck modes are not the shipped AI
            if p['source'] == 'pool':
                for s in r['seats']:
                    levels[p['profile']][0] += score(s['won'], s['winner'])
                    levels[p['profile']][1] += 1
            elif p['source'] == 'player':
                if style_of is None:
                    style_of = player_styles()
                s = r['seats'][0]
                for key in (style_of[p['pair']], 'all'):
                    styles[key][0] += score(s['won'], s['winner'])
                    styles[key][1] += score(r['baselineWinner'] == s['seat'], r['baselineWinner'])
                    styles[key][2] += 1
    return levels, styles, rounds


def player_styles():
    sys.path.insert(0, str(ROOT / 'sim'))
    from evaluate_pool import player_setup
    out = []
    for _, deck in player_setup():
        parts = deck.name.split('/')
        out.append(parts[1] if parts[0] == 'player' else 'recorded')
    return out


# ---- svg helpers --------------------------------------------------------------

def esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def text(x, y, value, fill, size=13, weight=400, anchor='start'):
    return ('<text x="%.1f" y="%.1f" fill="%s" font-size="%d" font-weight="%d" text-anchor="%s">%s</text>'
            % (x, y, fill, size, weight, anchor, esc(value)))


def bar(x0, y, x1, h, fill, r=4):
    """Horizontal bar anchored at x0, rounded only at its data end."""
    if x1 - x0 < r:
        return '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (x0, y, max(0, x1 - x0), h, fill)
    return ('<path d="M%.1f,%.1f H%.1f A%d,%d 0 0 1 %.1f,%.1f V%.1f A%d,%d 0 0 1 %.1f,%.1f H%.1f Z" fill="%s"/>'
            % (x0, y, x1 - r, r, r, x1, y + r, y + h - r, r, r, x1 - r, y + h, x0, fill))


def card(height, t, body, title=None, subtitle=None):
    head = ''
    if title:
        head += text(20, 32, title, t['ink'], 16, 600)
    if subtitle:
        head += text(20, 52, subtitle, t['ink2'], 12)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
            'font-family="%s" role="img" aria-label="%s">'
            '<rect x="0.5" y="0.5" width="%d" height="%d" rx="10" fill="%s" stroke="%s"/>%s%s</svg>\n'
            % (WIDTH, height, WIDTH, height, FONT, esc(title or 'Key figures'), WIDTH - 1, height - 1,
               t['surface'], t['border'], head, body))


def legend(t, items, y=64):
    """items: (kind, colour, label); kind 'box' (a bar colour) or 'dash' (a reference line)."""
    out, x = [], 20
    for kind, colour, label in items:
        if kind == 'dash':
            out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.5" stroke-dasharray="4 3"/>'
                       % (x, y + 6, x + 14, y + 6, colour))
        else:
            out.append('<rect x="%d" y="%d" width="12" height="12" rx="3" fill="%s"/>' % (x, y, colour))
        out.append(text(x + 20, y + 11, label, t['ink'], 12))
        x += 20 + 7 * len(label) + 28
    return ''.join(out)


def percent_axis(t, x0, x1, top, bottom):
    out = []
    for v in (0, 25, 50, 75, 100):
        x = x0 + (x1 - x0) * v / 100
        dash = ' stroke-dasharray="4 3"' if v == 50 else ''
        colour = t['ref'] if v == 50 else t['grid']
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1"%s/>'
                   % (x, top, x, bottom, colour, dash))
        out.append(text(x, bottom + 16, '%d%% · native AI' % v if v == 50 else '%d%%' % v, t['ink2'], 11, anchor='middle'))
    return ''.join(out)


# ---- charts -------------------------------------------------------------------

def kpis(t, tiles):
    w = (WIDTH - 40 - 16 * (len(tiles) - 1)) / len(tiles)
    body = []
    for i, (value, label, note) in enumerate(tiles):
        x = 20 + i * (w + 16)
        body.append('<rect x="%.1f" y="18" width="%.1f" height="96" rx="8" fill="none" stroke="%s"/>'
                    % (x, w, t['border']))
        body.append(text(x + 14, 58, value, t['ink'], 26, 700))
        body.append(text(x + 14, 82, label, t['ink'], 12, 600))
        body.append(text(x + 14, 100, note, t['ink2'], 11))
    return card(132, t, ''.join(body))


def ladder_levels(levels_db, ladder_db):
    """Easy / Normal / Hard as shipped: Easy profile 512 nodes, Medium search with 768 nodes,
    Medium search with 2,048 nodes; same pool matchups and seeds for all three."""
    out = defaultdict(lambda: [0.0, 0])
    for path, pick in ((levels_db, {('easy', ''): 'easy', ('medium', ''): 'hard'}),
                       (ladder_db, {('medium', 'nodes768'): 'medium'})):
        db = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        for params, payload, result in db.execute(
                "SELECT j.params, t.payload, t.result FROM tasks t JOIN jobs j ON j.id=t.job_id "
                "WHERE t.status='done' AND j.kind='benchmark'"):
            params, p, r = json.loads(params), json.loads(payload), json.loads(result)
            level = pick.get((params['profile'], params['policy'].partition(':')[2]))
            if p.get('source') != 'pool' or level is None:
                continue
            for s in r['seats']:
                out[level][0] += score(s['won'], s['winner'])
                out[level][1] += 1
    return out


def levels_chart(t, levels):
    rows = [(LEVEL_NAMES[p], levels[p]) for p in PROFILES if levels[p][1]]
    x0, x1, top = 110, WIDTH - 150, 92
    h, gap = 22, 14
    bottom = top + len(rows) * (h + gap) - gap + 8
    body = [percent_axis(t, x0, x1, top - 8, bottom),
            legend(t, (('box', t['s1'], 'Better AI score share'), ('dash', t['ref'], '50%: as strong as the native AI')))]
    for i, (name, (won, games)) in enumerate(rows):
        y = top + i * (h + gap)
        pct = 100 * won / games
        body.append(text(20, y + 15, name, t['ink'], 13, 600))
        body.append(bar(x0, y, x0 + (x1 - x0) * pct / 100, h, t['s1']))
        body.append(text(x0 + (x1 - x0) * pct / 100 + 8, y + 15, '%.1f%%' % pct, t['ink'], 13, 600))
        body.append(text(WIDTH - 20, y + 15, '%s games' % format(games, ','), t['ink2'], 11, anchor='end'))
    return card(bottom + 40, t, ''.join(body), 'Better AI against the native AI, by difficulty',
                'Score share in the same matchups with the same luck (win 1, draw 0.5). '
                '110 NPC deck matchups, every faction and leader, both seats.')


def styles_chart(t, styles):
    rows = [(label, styles[key]) for key, label in STYLE_LABELS if styles[key][2]]
    x0, x1, top = 150, WIDTH - 110, 92
    h, inner, gap = 16, 3, 18
    group = 2 * h + inner
    bottom = top + len(rows) * (group + gap) - gap + 8
    body = [percent_axis(t, x0, x1, top - 8, bottom)]
    # legend
    body.append('<rect x="20" y="64" width="12" height="12" rx="3" fill="%s"/>' % t['s1'])
    body.append(text(38, 75, 'NPC played by Better AI', t['ink'], 12))
    body.append('<rect x="210" y="64" width="12" height="12" rx="3" fill="%s"/>' % t['s2'])
    body.append(text(228, 75, 'NPC played by the native AI', t['ink'], 12))
    for i, (label, (better, native, games)) in enumerate(rows):
        y = top + i * (group + gap)
        body.append(text(20, y + h + 6, label, t['ink'], 13, 600))
        body.append(text(20, y + h + 21, '%s games' % format(games, ','), t['ink2'], 11))
        for j, (value, colour) in enumerate(((better, t['s1']), (native, t['s2']))):
            pct = 100 * value / games
            yy = y + j * (h + inner)
            body.append(bar(x0, yy, x0 + (x1 - x0) * pct / 100, h, colour))
            body.append(text(x0 + (x1 - x0) * pct / 100 + 8, yy + 12, '%.1f%%' % pct, t['ink'], 12, 600))
    return card(bottom + 40, t, ''.join(body), 'NPC decks against player-style decks (8,192-node search)',
                'Win share of the NPC side; the player side is played by Better AI as a strong stand-in '
                'for a human. Same decks and luck.')


def rounds_chart(t, rounds):
    rows = [('Round %d' % r, rounds[r]) for r in sorted(rounds)]
    total = sum(n for _, n in rows) or 1
    x0, x1, top = 110, WIDTH - 150, 92
    h, gap = 20, 12
    peak = max(n for _, n in rows) if rows else 1
    body = [legend(t, (('box', t['s1'], 'Costly decisions in that round (share of all found)'),))]
    for i, (name, n) in enumerate(rows):
        y = top + i * (h + gap)
        body.append(text(20, y + 14, name, t['ink'], 13, 600))
        body.append(bar(x0, y, x0 + (x1 - x0) * n / peak, h, t['s1']))
        body.append(text(x0 + (x1 - x0) * n / peak + 8, y + 14, '%d (%.0f%%)' % (n, 100 * n / total), t['ink'], 12, 600))
    bottom = top + len(rows) * (h + gap)
    return card(bottom + 20, t, ''.join(body), 'Costly decisions found by the blunder hunter, by round',
                'A decision counts only when another move wins more often on the same later luck. '
                'Most mistakes happen in round 1.')


def requirement_curve(strengths):
    """Extra NPC cards that enter, summed over every native NPC deck, by player deck strength:
    vanilla (inverted check) and Better Gwent On per deck variant (Easy 1, Normal 2, Hard 3)."""
    sys.path.insert(0, str(ROOT / 'sim'))
    from evaluate_pool import setup, XML
    from gwentsim.native_decks import NativeDecks
    templates = setup()['match'].templates
    native = NativeDecks(XML, templates)
    decks = {}
    for name in native.npc_names():
        for variant in (1, 2, 3):
            try:
                decks[name, variant] = (native.build(name, variant).dynamic_card_requirements,
                                        native.build(name, variant, repaired=True).dynamic_card_requirements)
            except Exception:
                pass
    total = sum(len(v[0]) for (n, var), v in decks.items() if var == 3)
    curves = {'vanilla': [], 1: [], 2: [], 3: []}
    for st in strengths:
        curves['vanilla'].append(sum(st >= q for (n, var), (van, _) in decks.items() if var == 3 for q in van))
        for variant in (1, 2, 3):
            curves[variant].append(sum(st >= q for (n, var), (_, rep) in decks.items() if var == variant for q in rep))
    return curves, total


def requirements_chart(t, strengths, curves, total):
    x0, x1, top, bottom = 70, WIDTH - 150, 84, 300
    xs = lambda st: x0 + (x1 - x0) * (st - strengths[0]) / (strengths[-1] - strengths[0])
    ys = lambda n: bottom - (bottom - top) * n / total
    body = []
    for v in [v for v in range(0, total, 50)] + [total]:
        body.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>' % (x0, ys(v), x1, ys(v), t['grid']))
        body.append(text(x0 - 8, ys(v) + 4, v, t['ink2'], 11, anchor='end'))
    for st in strengths[::2]:
        body.append(text(xs(st), bottom + 18, st, t['ink2'], 11, anchor='middle'))
    body.append(text((x0 + x1) / 2, bottom + 36, "Strength of the player's deck", t['ink2'], 11, anchor='middle'))
    body.append(text(20, top - 14, 'Extra NPC cards (of %d)' % total, t['ink2'], 11))
    series = [(1, 'Easy', t['s3']), (2, 'Normal', t['s2']), (3, 'Hard', t['s1'])]
    labels = [(curves['vanilla'][-1], 'Vanilla (bug)', t['ink2'])]
    for variant, name, colour in series:
        pts = ' '.join('%.1f,%.1f' % (xs(st), ys(n)) for st, n in zip(strengths, curves[variant]))
        body.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round"/>' % (pts, colour))
        for st, n in zip(strengths, curves[variant]):
            body.append('<circle cx="%.1f" cy="%.1f" r="4" fill="%s" stroke="%s" stroke-width="2"/>' % (xs(st), ys(n), colour, t['surface']))
        labels.append((curves[variant][-1], name, colour))
    # vanilla drawn last so its dashed line stays visible where the curves meet at the top
    van = ' '.join('%.1f,%.1f' % (xs(st), ys(n)) for st, n in zip(strengths, curves['vanilla']))
    body.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2" stroke-dasharray="6 4"/>' % (van, t['ink2']))
    # direct labels at the line ends, nudged apart so they never overlap
    placed = []
    for value, name, colour in sorted(labels, key=lambda item: -item[0]):
        y = ys(value) + 4
        while any(abs(y - other) < 15 for other in placed):
            y += 15
        placed.append(y)
        body.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="2"/>' % (x1 + 8, y - 4, x1 + 18, y - 4, colour))
        body.append(text(x1 + 22, y, name, t['ink'], 12, 600))
    return card(bottom + 52, t, ''.join(body), "NPC extra cards by the strength of the player's deck",
                'Vanilla gives almost every extra card at any strength; with Better Gwent On each card needs '
                'its intended requirement. All native NPC decks.')


LAYOUT = [('mod/settings/', 'Options menu and WitcherScript wrappers for settings, wagers and deck difficulty'),
          ('mod/v8/as3/', 'The V8 AI in ActionScript, compiled into the Gwent interface at build time'),
          ('mod/recorder/', 'Script sources of diagnostic builds (match recorder; also probe/, feasibility/)'),
          ('tools/', 'Build pipeline, patchers that insert the mod hooks, format helpers, recorder readers'),
          ('sim/', 'Python reference of the V8 policy, evaluation scripts and tests'),
          ('sim/gwentsim/', 'Policy, search, belief, position and player-deck models'),
          ('lab/', 'Gwent AI Lab: crash-safe job runner, web panel, reports and these charts'),
          ('docs/', 'Testing, research, development and repository scope')]


def table_card(t, title, rows, first=250):
    top, h = 70, 30
    body = []
    for i, (left, right) in enumerate(rows):
        y = top + i * h
        if i:
            body.append('<line x1="20" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (y - 10, WIDTH - 20, y - 10, t['grid']))
        body.append('<text x="20" y="%d" fill="%s" font-size="13" font-weight="600" '
                    'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">%s</text>' % (y + 6, t['s1'], esc(left)))
        body.append(text(20 + first, y + 6, right, t['ink'], 13))
    return card(top + len(rows) * h, t, ''.join(body), title)


def grouped_chart(t, title, subtitle, rows, legend=('NPC played by Better AI', 'NPC played by the native AI')):
    """rows: (label, note, pct_a, pct_b). Two bars per row, 0-100% axis with the 50% line."""
    x0, x1, top = 170, WIDTH - 110, 92
    h, inner, gap = 16, 3, 18
    group = 2 * h + inner
    bottom = top + len(rows) * (group + gap) - gap + 8
    body = [percent_axis(t, x0, x1, top - 8, bottom)]
    body.append('<rect x="20" y="64" width="12" height="12" rx="3" fill="%s"/>' % t['s1'])
    body.append(text(38, 75, legend[0], t['ink'], 12))
    body.append('<rect x="230" y="64" width="12" height="12" rx="3" fill="%s"/>' % t['s2'])
    body.append(text(248, 75, legend[1], t['ink'], 12))
    for i, (label, note, a, b) in enumerate(rows):
        y = top + i * (group + gap)
        body.append(text(20, y + h + 6, label, t['ink'], 13, 600))
        body.append(text(20, y + h + 21, note, t['ink2'], 11))
        for j, (pct, colour) in enumerate(((a, t['s1']), (b, t['s2']))):
            yy = y + j * (h + inner)
            body.append(bar(x0, yy, x0 + (x1 - x0) * pct / 100, h, colour))
            body.append(text(x0 + (x1 - x0) * pct / 100 + 8, yy + 12, '%.0f%%' % pct, t['ink'], 12, 600))
    return card(bottom + 40, t, ''.join(body), title, subtitle)


def deck_mode_rows(dbs, style_filter):
    """NPC win share per (difficulty, mode) from player-deck benchmarks of the shipped AI."""
    import sqlite3
    sys.path.insert(0, str(ROOT / 'sim'))
    styles = player_styles()
    agg = defaultdict(lambda: [0.0, 0.0, 0])
    for path in dbs:
        db = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        for params, payload, result, _name in db.execute(
                "SELECT j.params, t.payload, t.result, j.name FROM tasks t JOIN jobs j ON j.id=t.job_id "
                "WHERE t.status='done' AND j.kind='benchmark' AND j.status != 'superseded'"):
            params, p, r = json.loads(params), json.loads(payload), json.loads(result)
            policy, _, flags = params.get('policy', '').partition(':')
            # The shipped AI, alone or in the fair scene (player-/base- switches only).
            if p.get('source') != 'player' or policy != 'response-v8' or params.get('weights') or any(
                    not f.startswith(('player-', 'base-')) for f in flags.split('+') if f):
                continue
            if ':' in (params.get('npc_decks') or ''):
                continue                              # deck-mode experiments (spies4, decoy3)
            if style_filter and styles[p['pair']] != style_filter:
                continue
            s = r['seats'][0]
            a = agg[params['profile'], params.get('npc_decks') or 'original']
            a[0] += score(s['won'], s['winner'])
            a[1] += score(r['baselineWinner'] == s['seat'], r['baselineWinner'])
            a[2] += 1
    return agg


INTENSITY = {'light': ('#cde2fb', '#86b6ef', '#3987e5', '#1c5cab'),
             'dark': ('#184f95', '#256abf', '#3987e5', '#86b6ef')}
PRESETS = [('The original game', 'Mod Off', 'The game exactly as shipped.', 1),
           ('A smarter opponent', 'Hard · Original decks', 'Same NPC decks, better decisions.', 2),
           ('A fair fight', 'Normal or Hard · Adaptive', "The NPC's deck follows yours all game.", 3),
           ('Maximum challenge', 'Hard · Strong · stakes On', 'The strongest NPC the rules allow.', 4)]


def challenge_card(t, theme):
    """Static infographic: the two difficulty dials and four combinations from light to heavy."""
    ramp = INTENSITY[theme]
    body = []
    dials = [('AI difficulty', 'how well the NPC thinks', ['Easy', 'Normal', 'Hard']),
             ('NPC decks', 'which cards the NPC plays: few extras, balanced to yours, best', ['Original', 'Adaptive', 'Strong'])]
    col = (WIDTH - 56) / 2
    for i, (name, note, steps) in enumerate(dials):
        x = 20 + i * (col + 16)
        body.append('<rect x="%.1f" y="70" width="%.1f" height="92" rx="8" fill="none" stroke="%s"/>' % (x, col, t['border']))
        body.append(text(x + 14, 94, 'Dial %d · %s' % (i + 1, name), t['ink'], 14, 700))
        body.append(text(x + 14, 112, note, t['ink2'], 12))
        pill = (col - 28 - 8 * (len(steps) - 1)) / len(steps)
        for j, step in enumerate(steps):
            px = x + 14 + j * (pill + 8)
            shade = ramp[min(3, j + (4 - len(steps)))]
            fg = '#ffffff' if (theme == 'light' and j + (4 - len(steps)) >= 2) or (theme == 'dark' and j + (4 - len(steps)) <= 1) else t['ink']
            if theme == 'dark' and j + (4 - len(steps)) >= 3:
                fg = '#0d1117'
            body.append('<rect x="%.1f" y="124" width="%.1f" height="26" rx="13" fill="%s"/>' % (px, pill, shade))
            body.append(text(px + pill / 2, 141, step, fg, 12, 600, anchor='middle'))
    body.append(text(20, 196, 'Combinations, from light to heavy', t['ink'], 14, 700))
    w = (WIDTH - 40 - 3 * 12) / 4
    for i, (title, setting, note, level) in enumerate(PRESETS):
        x = 20 + i * (w + 12)
        body.append('<rect x="%.1f" y="210" width="%.1f" height="128" rx="8" fill="none" stroke="%s"/>' % (x, w, t['border']))
        for k in range(4):
            body.append('<rect x="%.1f" y="224" width="%.1f" height="8" rx="4" fill="%s"/>'
                        % (x + 14 + k * ((w - 28 - 12) / 4 + 4), (w - 28 - 12) / 4, ramp[k] if k < level else t['grid']))
        body.append(text(x + 14, 258, title, t['ink'], 14, 700))
        body.append(text(x + 14, 280, setting, t['s1'], 12, 600))
        words, line, lines = note.split(), '', []
        for word in words:
            if len(line) + len(word) > 26:
                lines.append(line); line = word
            else:
                line = (line + ' ' + word).strip()
        lines.append(line)
        for k, ln in enumerate(lines[:2]):
            body.append(text(x + 14, 302 + k * 16, ln, t['ink2'], 12))
    return card(356, t, ''.join(body), 'Choosing your challenge',
                'Two independent dials; the mod Off leaves the game exactly as shipped.')


def ab_chart(t, rows, title, subtitle, span=3.0):
    """rows: (label, note, change_pct, z), grouped by label. Each test name heads its group; each
    cell (level, decks, games) gets a bar from zero (blue = NPC wins more, orange = less)."""
    import math
    span = max(5.0, 5 * math.ceil(span / 5))           # round axis ticks
    x0, x1, top = 330, WIDTH - 190, 96
    h, row, head = 14, 24, 30
    mid = (x0 + x1) / 2
    scale = (x1 - x0) / 2 / span
    groups = len({r[0] for r in rows})
    bottom = top + len(rows) * row + groups * head
    body = [legend(t, (('box', t['s1'], 'NPC wins more'), ('box', t['s2'], 'NPC wins less'),
                       ('dash', t['ref'], 'no change')), y=66)]
    for v in (-span, -span / 2, 0, span / 2, span):
        x = mid + v * scale
        body.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s"%s/>' % (
            x, top, x, bottom, t['ref'] if v == 0 else t['grid'], ' stroke-dasharray="4 3"' if v == 0 else ''))
        body.append(text(x, bottom + 16, '%+g%%' % v if v else '0', t['ink2'], 11, anchor='middle'))
    y, last = top, None
    for label, note, change, z in rows:
        if label != last:
            body.append(text(20, y + 20, label, t['ink'], 13, 600))
            y += head
            last = label
        body.append(text(32, y + 12, note, t['ink2'], 11))
        end = mid + max(-span, min(span, change)) * scale
        lo, hi = sorted((mid, end))
        body.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" rx="3" fill="%s"/>'
                    % (lo, y + 1, max(1, hi - lo), h, t['s1'] if change >= 0 else t['s2']))
        proven = abs(z) >= 2
        body.append(text(WIDTH - 20, y + 12, '%+.2f%% · z %+.1f · %s' % (change, z, 'proven' if proven else 'not proven'),
                         t['ink'] if proven else t['ink2'], 12, 600 if proven else 400, anchor='end'))
        y += row
    return card(bottom + 34, t, ''.join(body), title, subtitle)


def ab_rows(dbs):
    """Paired A/B tests: every benchmark whose policy carries a variant ("response-v8:x") or whose
    npc_decks carries flags ("balanced:decoy3") against the plain job with the same source,
    level and deck mode, on the same matchups and luck. Returns {(label, level, decks): (change %, z, n)}."""
    import sqlite3
    groups = defaultdict(dict)
    for path in dbs:
        db = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        for params, payload, result in db.execute(
                "SELECT j.params, t.payload, t.result FROM tasks t JOIN jobs j ON j.id=t.job_id "
                "WHERE t.status='done' AND j.kind='benchmark' AND j.status != 'superseded'"):
            params, p, r = json.loads(params), json.loads(payload), json.loads(result)
            if p.get('source') != 'player' or params.get('weights'):
                continue
            policy, _, variant = params.get('policy', 'response-v8').partition(':')
            decks, _, flags = (params.get('npc_decks') or 'original').partition(':')
            s = r['seats'][0]
            label = '+'.join(f for f in (variant, flags) if f)   # policy and deck-mode switches
            groups[label, params['profile'], decks][p['pair'], p['seed'], p['swap']] = score(s['won'], s['winner'])
    out = {}
    for (label, level, decks), runs in groups.items():
        # Flags starting with "player-" or "base-" set the scene (both arms); the others are tested.
        context = '+'.join(f for f in label.split('+') if f.startswith(('player-', 'base-')))
        if label == context:
            continue
        base = groups.get((context, level, decks), {})
        keys = sorted(set(runs) & set(base))
        if not label or len(keys) < 30:
            continue
        diffs = [runs[k] - base[k] for k in keys]
        mean = sum(diffs) / len(diffs)
        sd = (sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1)) ** 0.5 or 1e-9
        out[label, level, decks] = (100 * mean, mean / (sd / len(diffs) ** 0.5), len(diffs))
    return out


# ---- main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('dbs', nargs='+')
    parser.add_argument('--records', default=str(ROOT / 'game/records'))
    parser.add_argument('--evaluations', default=str(ROOT / 'game/evaluations'))
    parser.add_argument('--out', default=str(ROOT / 'docs/img'))
    parser.add_argument('--levels-ladder', nargs=2, metavar=('LEVELS_DB', 'LADDER_DB'),
                        help="the mod's three levels from the fresh level benchmark and the node ladder")
    parser.add_argument('--ab', nargs='*', default=None, help='databases for the A/B chart (default: --battery)')
    parser.add_argument('--ab-tests', default='', help='comma-separated tests to chart, in this order (default: all)')
    parser.add_argument('--battery', nargs='*', default=None,
                        help='databases for the deck-mode and A/B charts (default: all databases)')
    args = parser.parse_args()
    levels, styles, rounds = collect(args.dbs)
    if args.levels_ladder:
        levels = ladder_levels(*args.levels_ladder)
    totals = [report.lab_totals(p) for p in args.dbs]
    lab_matches = sum(x['matches'] for x in totals)
    cpu_hours = sum(x['cpuSeconds'] for x in totals) / 3600
    earlier = report.evaluation_matches(args.evaluations) if Path(args.evaluations).exists() else 0
    complete = {p.stem for p in Path(args.records).glob('g[0-9]*.json') if re.fullmatch(r'g\d+\.json', p.name)}
    recordings = len(complete)
    # Recordings cut short (match not closed) stay in records/broken; count each match once.
    partial = len({m.group(0) for p in (Path(args.records) / 'broken').glob('g*')
                   for m in [re.match(r'g\d+', p.name)] if m} - complete)
    recorded_note = '%d complete, %d cut short' % (recordings, partial) if partial else 'complete matches'
    findings = sum(rounds.values())
    better, native, games = styles['all']
    edge = 100 * (better - native) / native if native else 0
    tiles = [('{:,}'.format(lab_matches + earlier), 'Simulated matches', 'Lab + earlier evaluations'),
             ('%.0f h' % cpu_hours, 'Lab CPU time', 'one core per task'),
             (str(recordings + partial), 'Recorded matches', recorded_note),
             (str(findings), 'Mistakes found', 'by the blunder hunter'),
             ('%+.0f%%' % edge, 'More NPC wins', 'vs native AI, player decks')]
    totals_tiles = [('{:,}'.format(lab_matches), 'Lab matches', 'Gwent AI Lab'),
                    ('{:,}'.format(earlier), 'Earlier matches', 'V1-V8 evaluations'),
                    ('%.0f h' % cpu_hours, 'Lab CPU time', 'one core per task'),
                    (str(recordings + partial), 'Recorded matches', recorded_note),
                    (str(findings), 'Mistakes found', 'by the blunder hunter')]
    strengths = list(range(80, 321, 20))
    curves, total = requirement_curve(strengths)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for theme, t in THEMES.items():
        (out / ('totals-%s.svg' % theme)).write_text(kpis(t, totals_tiles))
        (out / ('layout-%s.svg' % theme)).write_text(table_card(t, 'Repository layout', LAYOUT))
        (out / ('challenge-%s.svg' % theme)).write_text(challenge_card(t, theme))
        (out / ('requirements-%s.svg' % theme)).write_text(requirements_chart(t, strengths, curves, total))
        (out / ('kpis-%s.svg' % theme)).write_text(kpis(t, tiles))
        (out / ('levels-%s.svg' % theme)).write_text(levels_chart(t, levels))
        if games:
            (out / ('player-decks-%s.svg' % theme)).write_text(styles_chart(t, styles))
        if rounds:
            (out / ('mistakes-%s.svg' % theme)).write_text(rounds_chart(t, rounds))
    names = dict(original='Original', balanced='Adaptive', strong='Strong')
    for key, title, flt in (('deck-modes', 'NPC deck modes against player-style decks', None),
                            ('deck-modes-mine', 'NPC deck modes against my own real decks', 'recorded')):
        agg = deck_mode_rows(args.battery or args.dbs, flt)
        rows = [('%s · %s' % (LEVEL_NAMES[prof], names[mode]), '%s games' % format(agg[prof, mode][2], ','),
                 100 * agg[prof, mode][0] / agg[prof, mode][2], 100 * agg[prof, mode][1] / agg[prof, mode][2])
                for prof in ('easy', 'medium', 'hard', 'expert') for mode in ('original', 'balanced', 'strong') if agg[prof, mode][2]]
        if rows:
            for theme, t in THEMES.items():
                (out / ('%s-%s.svg' % (key, theme))).write_text(grouped_chart(
                    t, title, 'Win share of the NPC side; the player side is played by Better AI. Same decks and '
                    'luck. NPC decks as shipped (test, 12 October 2026).',
                    rows))
            print(key, [(r[0], round(r[2]), round(r[3]), r[1]) for r in rows])
    ab = ab_rows(args.ab or args.battery or args.dbs)
    if ab:
        labels = {'weather-zero': ('Weather that changes nothing', 'counted as a wasted card'),
                  'mulligan': ('NPC exchanges opening cards', 'up to two, evaluated'),
                  'mulligan-structural': ('NPC exchanges muster copies', 'structural only'),
                  'mulligan-leader': ("NPC returns its leader's weather", 'only that card'),
                  'decoy3': ('3 Decoys vs spy factions', 'Nilfgaard / Northern Kingdoms'),
                  'mulligan-combined': ("NPC exchange: leader's weather first", 'then evaluated'),
                  'known-hand': ('NPC remembers cards back in your hand', 'Decoy and similar'),
                  'lead-pass': ('NPC passes a safe lead after a lost round', 'keeps cards for the last round'),
                  'budget-half': ('Half the search nodes', 'less thinking time'),
                  'skellige': ('Skellige cards in the search', 'Mardroeme, Berserkers, Pirate, Kambi'),
                  'mulligan-full': ('Exchange: leader weather, Muster copy, evaluated', ''),
                  'spies4': ('NPC decks with up to 4 spies', 'instead of 3'),
                  'kit4': ('NPC decks with at most 4 special cards', 'instead of 8'),
                  'kit2': ('NPC decks with at most 2 special cards', 'instead of 8'),
                  'units22': ('Strong NPC decks with 22 units', 'instead of 24'),
                  'notriss': ('No Triss in NPC decks', ''),
                  'kit4+units22+notriss': ('Lean NPC decks', '4 specials, 22 units, no Triss'),
                  'scorch-prior': ('NPC expects your Scorch', 'in every other sampled hand'),
                  'reserve35': ('NPC values kept cards more', 'passes a led round sooner'),
                  'scorch-pool': ('NPC imagines Scorch in your hand', 'Scorch was missing from its guesses'),
                  'scorch-pool+scorch-prior': ('NPC expects your Scorch', 'in its guesses, half the hands hold one'),
                  'v090': ('0.9.0 NPC deck shape', '8 specials, 24 Strong units, Triss'),
                  'heroes': ('Faction heroes, varied per match', "2-3 of the faction's, Geralt/Ciri 1 in 4"),
                  'allow-self-harm': ('Old rule: NPC may hurt its own score', 'self-only Scorch, wasted leader'),
                  'strictheroes': ('Adaptive faction heroes without the fallback', 'vs every hero allowed when short'),
                  'lead-pass+known-hand+mulligan-combined+weather-zero+skellige': ('All NPC changes together', '')}
        decks = dict(original='Original decks', balanced='Adaptive decks', strong='Strong decks')
        def tested(label):
            return '+'.join(f for f in label.split('+') if not f.startswith(('player-', 'base-')))
        order = {name: i for i, name in enumerate(args.ab_tests.split(','))} if args.ab_tests else None
        level_order = {'easy': 0, 'medium': 1, 'hard': 2, 'expert': 3}
        items = [kv for kv in ab.items() if order is None or tested(kv[0][0]) in order]
        items.sort(key=lambda kv: (order[tested(kv[0][0])] if order else kv[0][0], level_order.get(kv[0][1], 9), kv[0][2]))
        rows = [(labels.get(tested(k[0]), (tested(k[0]), ''))[0], '%s · %s · %s games' % (
                 LEVEL_NAMES.get(k[1], k[1]), decks[k[2]], format(v[2], ',')), v[0], v[1]) for k, v in items]
        span = max(3.0, max(abs(r[2]) for r in rows) * 1.15)
        for theme, t in THEMES.items():
            (out / ('ab-%s.svg' % theme)).write_text(ab_chart(
                t, rows, 'A/B tests: candidate vs the current AI',
                'Change in NPC win share; same matchups and luck, the player exchanges opening cards too. '
                'Proven: z of 2 or more.', span))
        print('ab', [(r[0], r[1], round(r[2], 2), round(r[3], 2)) for r in rows])
    print('levels', {k: v for k, v in levels.items()}, '\nstyles', dict(styles), '\nrounds', dict(rounds))
    print('tiles', tiles)


if __name__ == '__main__':
    main()
