#!/usr/bin/env python3
# Cross-checks the recorded matches (game/records/gNNN.json, made by tools/rec_read.py):
#  - per match summary (decks, leaders, turns, winner, random calls per tag);
#  - random call sites: tag -> line in the decompiled AS3 file;
#  - replays the deck shuffle with the recorded random values and compares with the "deal" snapshot;
#  - card templates identical across matches;
#  - XML (def_gwint_cards_final.xml, def_gwint_battle_king_cards.xml) -> template mapping of
#    faction / type flags / effect flags / summon flags;
#  - dynamic card requirements vs def_gwint_decks.xml difficulties (GetDifficulty bug);
#  - snapshot consistency (unique instances, score/round result agreement).
# Usage: python3 tools/rec_analyze.py
import collections, glob, json, os, re, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
REC = os.path.join(ROOT, 'game', 'records')
AS = os.path.join(ROOT, 'game', 'vanilla', 'as', 'scripts', 'red', 'game', 'witcher3', 'menus', 'gwint')
XML = os.path.join(ROOT, 'game', 'vanilla', 'xml', 'content0', 'gameplay', 'items')
TAG_FILES = {'CM': 'CardManager', 'CI': 'CardInstance', 'CL': 'CardLeaderInstance', 'DK': 'GwintDeck',
             'FL': 'GwintGameFlowController', 'AI': 'AIPlayerController'}
FACTIONS = {'F_NEUTRAL': 0, 'F_NO_MANS_LAND': 1, 'F_NILFGAARD': 2, 'F_NORTHERN_KINGDOM': 3,
            'F_SCOIATAEL': 4, 'F_SKELLIGE': 5}
FACTION_NAMES = {v: k for k, v in FACTIONS.items()}
CARD_LISTS = ('hand', 'grave', 'siege', 'ranged', 'melee', 'siegeMod', 'rangedMod', 'meleeMod', 'leader')

problems = []


def problem(msg):
    problems.append(msg)
    print('  !! ' + msg)


def random_sites():
    """tag -> 'File.as:line' (n-th Math.random() occurrence, as numbered by build_recorder.py)."""
    sites = {}
    for prefix, cls in TAG_FILES.items():
        n = 0
        for ln, line in enumerate(open(os.path.join(AS, cls + '.as'), encoding='utf-8'), 1):
            for _ in re.finditer(r'Math\.random\(\)', line):
                n += 1
                sites['%s%d' % (prefix, n)] = '%s.as:%d' % (cls, ln)
    return sites


def load_matches():
    return [json.load(open(p)) for p in sorted(glob.glob(os.path.join(REC, 'g[0-9][0-9][0-9].json')))]


def xml_cards():
    cards = {}
    for fn in ('def_gwint_cards_final.xml', 'def_gwint_battle_king_cards.xml'):
        root = ET.parse(os.path.join(XML, fn)).getroot()
        for c in root.iter('card'):
            def flags(tag):
                e = c.find(tag)
                return None if e is None else [f.get('name') for f in e.findall('flag')]
            idx = int(c.get('index'))
            assert idx not in cards, idx
            cards[idx] = {'name': c.get('name'), 'power': int(c.get('power')), 'faction': c.get('faction_index'),
                          'type': flags('type_flags'), 'effect': flags('effect_flags'),
                          'summon': flags('summonFlags'), 'file': fn}
    return cards


def summary(m, sites):
    ev = m['events']
    tpl = m['templates']
    print('\n== g%03d  (%d chunks, %d chars, %s)' % (m['game'], m['sent'], m['chars'], m['reason']))
    for p in ('0', '1'):
        d = m['decks'][p]
        king = tpl[str(d['king'])]
        n_dyn = len(d['dynamicCards'])
        print('  P%s deck: king %d (faction %d %s), %d cards, special %d, dynamic %s req %s' % (
            p, d['king'], king['faction'], FACTION_NAMES[king['faction']], len(d['cards']), d['specialCard'],
            d['dynamicCards'], d['dynamicReq']))
    snaps = [e for e in ev if e['k'] == 'S']
    turns = [s for s in snaps if s['tag'].startswith('t')]
    acts = [e for e in ev if e['k'] == 'A']
    fin = [s for s in snaps if s['tag'] == 'fin']
    first = [e['first'] for e in ev if e['k'] == 'F']
    rr = fin[-1]['roundResults'] if fin else None
    wins = [0, 0]
    for r in rr or []:
        if r and r['winner'] in (0, 1):
            wins[r['winner']] += 1
    winner = 0 if wins[0] > wins[1] else 1 if wins[1] > wins[0] else -1
    rcount = collections.Counter(e['tag'] for e in ev if e['k'] == 'R')
    print('  first player %s; turn snapshots %d; AI decisions (A) %d (passes %d); rounds %s; wins %s -> winner P%d' % (
        first, len(turns), len(acts), sum(1 for a in acts if a['tx'] is None),
        ' '.join('%d/%d(w%d)' % (r['scores'][0], r['scores'][1], r['winner']) if r else '-' for r in rr), wins, winner))
    print('  random calls: %d  %s' % (sum(rcount.values()), ' '.join('%s=%d' % (t, rcount[t]) for t in sorted(rcount, key=lambda t: (t[:2], int(t[2:]))))))
    for t in rcount:
        if t not in sites:
            problem('g%03d: random tag %s has no call site' % (m['game'], t))
    return {'game': m['game'], 'turns': len(turns), 'acts': len(acts), 'winner': winner, 'wins': wins,
            'rr': rr, 'random': dict(rcount), 'first': first}


def faction_of_deck(m, p):
    return m['templates'][str(m['decks'][p]['king'])]['faction']


def replay_shuffle(m):
    """GwintDeck.shuffleDeck + adjustDeckToDifficulty + CardManager.shuffleAndDrawCards (no tutorial,
    no 11th card leader), using the recorded DK1 values. Compares with the 'deal' snapshot."""
    tpl = m['templates']
    ev = m['events']
    rnd = [e for e in ev if e['k'] == 'R']
    pos = 0
    # Leading calls before the shuffle (coin toss).
    while rnd[pos]['tag'] != 'DK1':
        pos += 1

    def strength(cards):
        s = 0
        for c in cards:
            t = tpl[str(c)]
            if t['type'] & 8:
                s += t['power']
            first = t['effects'][0] if t['effects'] else 0
            s += {23: 2, 24: 2, 25: 2, 30: 2, 26: 4, 27: 5, 29: 6, 7: 6, 31: 3, 32: 4, 33: 4, 34: 6, 35: 4}.get(first, 0)
        return s
    strengths = [strength(m['decks'][p]['cards']) for p in ('0', '1')]
    decks = []
    for p in (0, 1):
        d = m['decks'][str(p)]
        other = strengths[1 - p]
        orig = list(d['cards'])
        if d['dynamicReq'] and len(d['dynamicReq']) == len(d['dynamicCards']):
            for req, card in zip(d['dynamicReq'], d['dynamicCards']):
                if other >= req:
                    orig.append(card)
        out = []
        while orig:
            r = rnd[pos]
            if r['tag'] != 'DK1':
                problem('g%03d: shuffle expected DK1, got %s' % (m['game'], r['tag']))
                return strengths
            pos += 1
            v = r['u32'] / 4294967295.0
            import math
            i = min(int(math.floor(v * len(orig))), len(orig) - 1)
            out.append(orig.pop(i))
        if d['specialCard'] != -1:
            out.append(d['specialCard'])
        decks.append(out)
    if any(r['tag'] == 'DK1' for r in rnd[pos:pos + 1]):
        problem('g%03d: more DK1 calls than cards' % m['game'])
    deal = next(e for e in ev if e['k'] == 'S' and e['tag'] == 'deal')
    ok = True
    for p in (0, 1):
        d = decks[p]
        # CardManager.shuffleAndDrawCards: 11 cards if the leader's first effect is 11th_card.
        ntake = 11 if tpl[str(m['decks'][str(p)]['king'])]['effects'][:1] == [8] else 10
        hand = [d.pop() for _ in range(ntake)]
        snap = deal['players'][p]
        if d != snap['deck']:
            ok = False
            problem('g%03d P%d: replayed deck differs from deal snapshot' % (m['game'], p))
        got_hand = [c[0] for c in snap['hand']]
        if sorted(hand) != sorted(got_hand):
            ok = False
            problem('g%03d P%d: replayed hand %s != snapshot %s' % (m['game'], p, sorted(hand), sorted(got_hand)))
        elif p == 1 and hand != got_hand:
            print('  note: P2 hand order differs from draw order (%s vs %s)' % (hand, got_hand))
    print('  shuffle replay vs deal snapshot: %s (deck strengths P0=%d P1=%d)' % ('OK' if ok else 'MISMATCH', *strengths))
    return strengths


def snapshot_checks(m):
    n = 0
    for e in m['events']:
        if e['k'] != 'S':
            continue
        seen = set()
        for pl in e['players']:
            for l in CARD_LISTS:
                for c in pl.get(l, []):
                    if c is None:
                        continue
                    key = c[1]
                    if key in seen:
                        problem('g%03d snapshot %s: instance %s twice' % (m['game'], e['tag'], c))
                    seen.add(key)
        for c in e['weather']:
            if c[1] in seen:
                problem('g%03d snapshot %s: weather instance %s twice' % (m['game'], e['tag'], c))
            seen.add(c[1])
        if e['tag'].startswith('rr'):
            k = int(e['tag'][2:])
            r = e['roundResults'][k]
            sc = [pl['score'] for pl in e['players']]
            if r is None or r['scores'] != sc:
                problem('g%03d %s: round result %s != scores %s' % (m['game'], e['tag'], r, sc))
        n += 1
    print('  %d snapshots checked (unique instance ids, rr scores)' % n)


def compare_templates(matches):
    base = matches[0]['templates']
    same = all(m['templates'] == base for m in matches[1:])
    print('\n== templates: %d per match, identical across all matches: %s' % (len(base), same))
    if not same:
        for m in matches[1:]:
            diff = [k for k in set(base) | set(m['templates']) if base.get(k) != m['templates'].get(k)]
            problem('g%03d templates differ from g000: %s' % (m['game'], sorted(diff)[:10]))
    return base


def xml_mapping(tpl):
    cards = xml_cards()
    print('\n== XML vs templates: %d XML cards, %d templates' % (len(cards), len(tpl)))
    only_xml = sorted(set(cards) - set(map(int, tpl)))
    only_tpl = sorted(set(map(int, tpl)) - set(cards))
    if only_xml or only_tpl:
        problem('index sets differ: only XML %s, only templates %s' % (only_xml, only_tpl))
    name_to_idx = {c['name']: i for i, c in cards.items()}
    type_cands, eff_map, notes = {}, collections.defaultdict(collections.Counter), []
    mism = collections.Counter()
    for i, c in sorted(cards.items()):
        t = tpl.get(str(i))
        if t is None:
            continue
        if t['power'] != c['power']:
            mism['power'] += 1
            notes.append('power %d: xml %d tpl %d' % (i, c['power'], t['power']))
        if FACTIONS[c['faction']] != t['faction']:
            mism['faction'] += 1
            notes.append('faction %d: xml %s tpl %d' % (i, c['faction'], t['faction']))
        for f in c['type'] or []:
            type_cands[f] = type_cands.get(f, 0xFFFFFFFF) & t['type']
        xe = c['effect'] or []
        if len(xe) == len(t['effects']):
            for a, b in zip(xe, t['effects']):
                eff_map[a][b] += 1
        else:
            notes.append('effects %d (%s): xml %s tpl %s' % (i, c['name'], xe, t['effects']))
        xs = c['summon']
        exp = None if xs is None else [name_to_idx.get(n, 'UNKNOWN:' + n) for n in xs]
        if (exp or []) != (t['summon'] or []):
            mism['summon'] += 1
            notes.append('summon %d (%s): xml %s -> %s, tpl %s' % (i, c['name'], xs, exp, t['summon']))
    # Isolate each type flag to the bits it alone explains: remove bits shared with every card of
    # another flag is not needed when the flags are single bits; report the AND (candidate bits).
    print('  type flag -> bits (AND over all cards carrying it):')
    tmap = {}
    for f, bits in sorted(type_cands.items(), key=lambda kv: kv[1]):
        print('    %-22s %6d  0x%04x' % (f, bits, bits))
        tmap[f] = bits
    # Verify: OR of mapped bits == typeArray for every card.
    bad_type = []
    for i, c in cards.items():
        t = tpl.get(str(i))
        if t is None:
            continue
        o = 0
        for f in c['type'] or []:
            o |= tmap[f]
        if o != t['type']:
            bad_type.append((i, c['name'], c['type'], t['type'], o))
    print('  typeArray == OR(flag bits) for %d/%d cards' % (len(cards) - len(bad_type), len(cards)))
    for b in bad_type:
        print('    differs: %s' % (b,))
    # Name-based hypothesis: TYPE_X -> CardTemplate.CardType_X. Kings get typeArray = 0 from the
    # script (gwintBaseMenu.ws AddCardsToFlashArray, IsKingCard), so TYPE_KING cannot be measured.
    by_name = {'TYPE_MELEE': 1, 'TYPE_RANGED': 2, 'TYPE_SIEGE': 4, 'TYPE_CREATURE': 8, 'TYPE_WEATHER': 16,
               'TYPE_SPELL': 32, 'TYPE_ROW_MODIFIER': 64, 'TYPE_HERO': 128, 'TYPE_SPY': 256,
               'TYPE_FRIENDLY_EFFECT': 512, 'TYPE_OFFENSIVE_EFFECT': 1024, 'TYPE_GLOBAL_EFFECT': 2048,
               'TYPE_KING': 0}
    ok = 0
    for i, c in cards.items():
        o = 0
        for f in c['type'] or []:
            o |= by_name[f]
        ok += o == tpl[str(i)]['type']
    print('  name hypothesis TYPE_X -> CardType_X (TYPE_KING -> 0 via IsKingCard): %d/%d cards' % (ok, len(cards)))
    if ok != len(cards):
        problem('type name hypothesis fails for %d cards' % (len(cards) - ok))
    print('  effect flag -> int (pairs by position):')
    emap = {}
    for f, cnt in sorted(eff_map.items(), key=lambda kv: kv[1].most_common(1)[0][0]):
        print('    %-28s %s' % (f, dict(cnt)))
        if len(cnt) != 1:
            problem('effect flag %s maps to several ints %s' % (f, dict(cnt)))
        emap[f] = cnt.most_common(1)[0][0]
    print('  mismatches: %s' % dict(mism))
    for n in notes:
        print('    ' + n)
    return tmap, emap, cards, bad_type, notes


def dynamic_check(matches, cards):
    """For the AI deck (P1): find its deck_collection in def_gwint_decks.xml and compare the
    dynamicCards difficulties with the recorded requirements."""
    root = ET.parse(os.path.join(XML, 'def_gwint_decks.xml')).getroot()
    name_to_idx = {c['name']: i for i, c in cards.items()}

    # GetGwentCard() fails for names that are not card definitions (e.g. 'cirigog'); the script
    # then skips the card (gwintBaseMenu.ws CreateDeckDefinitionFlash), so unknown names are dropped.
    unknown = collections.Counter()

    def known(names):
        out = []
        for n in names:
            if n in name_to_idx:
                out.append(name_to_idx[n])
            else:
                unknown[n] += 1
        return out
    colls = []
    for coll in root.iter('deck_collection'):
        decks = [(d.get('difficulty'), d.get('leaderCard'), d.get('specialCard'),
                  sorted(known([c.get('name') for c in d.findall('card')]))) for d in coll.findall('deck')]
        dyn = coll.find('dynamicCards')
        dyn = [] if dyn is None else [(c.get('name'), name_to_idx.get(c.get('name')), int(c.get('difficulty')))
                                      for c in dyn.findall('card')]
        colls.append((coll.get('name'), decks, dyn))
    print('\n== dynamic cards (GetDifficulty bug check)')
    rows = []
    for m in matches:
        for p in ('0', '1'):
            d = m['decks'][p]
            cs = sorted(d['cards'])
            hits = [(n, diff, lead, dyn) for n, decks, dyn in colls for diff, lead, sp, cards_ in decks if cards_ == cs]
            if not hits:
                print('  g%03d P%s: no XML deck with these %d cards (player deck from the Deck Builder?)' % (m['game'], p, len(cs)))
                rows.append((m['game'], int(p), None, None, None, d['dynamicReq'], d['dynamicCards'], None))
                continue
            names = sorted(set((h[0], h[1], h[2]) for h in hits))
            n, diff, lead, dyn = hits[0]
            dyn = [x for x in dyn if x[1] is not None]   # unknown names are skipped by the script
            dyn_idx = [x[1] for x in dyn]
            ok_cards = dyn_idx == d['dynamicCards']
            if not ok_cards:
                problem('g%03d P%s: dynamic cards %s != xml %s' % (m['game'], p, d['dynamicCards'], dyn_idx))
            print('  g%03d P%s: deck %s difficulty=%s leader=%s; xml dynamic %s; recorded req %s cards %s; cards match: %s' % (
                m['game'], p, [x[0] for x in names], [x[1] for x in names], [x[2] for x in names],
                [(x[0], x[2]) for x in dyn], d['dynamicReq'], d['dynamicCards'], ok_cards))
            for (nm, i, df), req in zip(dyn, d['dynamicReq']):
                if df < 15 and req != 0:
                    problem('g%03d: dynamic %s difficulty %d has requirement %d (bug claim says 0)' % (m['game'], nm, df, req))
            rows.append((m['game'], int(p), [x[0] for x in names], [x[1] for x in names], dyn, d['dynamicReq'], d['dynamicCards'], ok_cards))
    print('  names in def_gwint_decks.xml that are not card definitions (dropped): %s' % dict(unknown))
    return rows


def ordering_checks(m):
    """Coarse order checks: FL1 first (coin toss), then all DK1, then F, deal and go."""
    ev = m['events']
    kinds = [e['k'] + (e.get('tag') or '') for e in ev[:3]]
    seq = []
    for e in ev:
        if e['k'] == 'R':
            seq.append(e['tag'])
        elif e['k'] == 'F':
            seq.append('F')
        elif e['k'] == 'S' and e['tag'] in ('deal', 'go'):
            seq.append('S' + e['tag'])
    head = []
    for s in seq:
        if not head or head[-1][0] != s:
            head.append([s, 1])
        else:
            head[-1][1] += 1
    fl = [e for e in ev if e['k'] == 'R' and e['tag'] == 'FL1']
    first = next(e['first'] for e in ev if e['k'] == 'F')
    if fl:
        coin = int(fl[0]['u32'] / 4294967295.0 * 2)   # Math.floor(Math.random() * 2)
        print('  coin toss FL1 u32=%d -> player %d, recorded first player %d: %s' % (
            fl[0]['u32'], coin, first, 'OK' if coin == first else 'MISMATCH'))
        if coin != first:
            problem('g%03d: coin toss mismatch' % m['game'])
    else:
        print('  no coin toss (Scoia\'tael rule), first player %d' % first)
    print('  start sequence: %s' % ' '.join('%sx%d' % (a, b) if b > 1 else a for a, b in head[:6]))


def main():
    sites = random_sites()
    print('== random call sites (tag -> decompiled line)')
    for t in sorted(sites, key=lambda t: (t[:2], int(t[2:]))):
        print('  %-5s %s' % (t, sites[t]))
    matches = load_matches()
    if not matches:
        sys.exit('no records in ' + REC)
    for m in matches:
        summary(m, sites)
        ordering_checks(m)
        replay_shuffle(m)
        snapshot_checks(m)
    tpl = compare_templates(matches)
    tmap, emap, cards, bad_type, notes = xml_mapping(tpl)
    dynamic_check(matches, cards)
    print('\n== %d problems' % len(problems))
    for p in problems:
        print('  ' + p)


if __name__ == '__main__':
    main()
