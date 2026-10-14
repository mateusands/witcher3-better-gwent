#!/usr/bin/env python3
# Reads the match records written by the recorder mod ([GwaiRec] in dx12user.settings),
# checks their integrity, parses every record and saves one JSON per match:
#   game/records/gNNN.json   (+ a raw copy of the settings file in game/records/)
#
# Usage: python3 tools/rec_read.py [settings_file]
# Exit code 1 if any match fails an integrity check (the bad match is still reported, but no
# JSON is written for it: missing data is never guessed around).
import json, os, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.expanduser('~/.local/share/Steam/steamapps/compatdata/292030/pfx/drive_c/users/'
                              'steamuser/Documents/The Witcher 3/dx12user.settings')
OUT = os.path.join(HERE, '..', 'game', 'records')
CHUNK = 850
SECTION = 'GwaiRec'

# Snapshot list ids (CardManager.CARD_LIST_LOC_*) -> names.
LISTS = {'1': 'hand', '2': 'grave', '3': 'siege', '4': 'ranged', '5': 'melee',
         '6': 'siegeMod', '7': 'rangedMod', '8': 'meleeMod', '10': 'leader'}


# gwintGameMenu.ws SendCardValues(): weather horn draw scorch summonClones unsummon
# improveNeighbours nurse.
SCRIPT_CARD_VALUES = [5, 5, 1, 8, 0.5, 2, 4, 3]


class RecError(Exception):
    pass


def read_section(path, name):
    vals, inside = {}, False
    for line in open(path, encoding='utf-8', errors='strict').read().splitlines():
        if line.startswith('['):
            inside = line.strip() == '[%s]' % name
            continue
        if inside and '=' in line:
            k, v = line.split('=', 1)
            if k in vals:
                raise RecError('duplicate key %s' % k)
            vals[k] = v[1:-1] if len(v) >= 2 and v.startswith('"') and v.endswith('"') else v
    return vals


def ints(s):
    """Dot-joined int list; 'null' -> None, '' -> []."""
    if s == 'null':
        return None
    return [int(x) for x in s.split('.')] if s else []


def inst(s):
    """'tpl.inst' -> [tpl, inst]; '-' / 'none' -> None."""
    if s in ('-', 'none'):
        return None
    t, i = s.split('.')
    return [int(t), int(i)]


def inst_list(s):
    return [inst(x) for x in s.split(',')] if s else []


def num(s):
    f = float(s)
    return int(f) if f.is_integer() and 'e' not in s.lower() and '.' not in s else f


def parse_snapshot(body):
    parts = body.split('|')
    snap = {'tag': parts[0], 'players': []}
    for p in parts[1:]:
        if p.startswith('w='):
            snap['weather'] = inst_list(p[2:])
        elif p.startswith('rr='):
            rr = []
            for x in (p[3:].split(',') if p[3:] else []):
                if x == '-':
                    rr.append(None)
                else:
                    a, b, w = x.split('/')
                    rr.append({'scores': [int(a), int(b)], 'winner': int(w)})
            snap['roundResults'] = rr
        else:
            fields = p.split('~')
            pl = {'player': int(fields[0])}
            for f in fields[1:]:
                k, v = f.split('=', 1)
                if k == 'sc':
                    pl['score'] = int(v)
                elif k == 'ld':
                    pl['leaderState'] = None if v == '-' else {'canBeUsed': v[0] == '1', 'hasBeenUsed': v[1] == '1'}
                elif k == 'd':
                    pl['deck'] = ints(v)
                elif k in LISTS:
                    pl[LISTS[k]] = inst_list(v)
                else:
                    raise RecError('unknown snapshot field %r' % k)
            if pl['player'] != len(snap['players']):
                raise RecError('snapshot player order %r' % body[:60])
            snap['players'].append(pl)
    if len(snap['players']) != 2 or 'weather' not in snap or 'roundResults' not in snap:
        raise RecError('incomplete snapshot %r' % body[:80])
    return snap


def parse_record(r):
    k, b = r[0], r[1:]
    if k == 'I':
        value = int(b)
        if value < 0:
            raise RecError('negative instance base')
        return {'k': 'I', 'instanceBase': value}
    if k == 'T':
        idx, power, fac, typ, eff, summ = b.split(':')
        return {'k': 'T', 'index': int(idx), 'power': int(power), 'faction': int(fac),
                'type': int(typ), 'effects': ints(eff), 'summon': ints(summ)}
    if k == 'D':
        player, rest = b.split(':', 1)
        name, king, special, cards, req, dyn = rest.rsplit(':', 5)
        return {'k': 'D', 'player': int(player), 'deckName': name, 'king': int(king),
                'specialCard': int(special), 'cards': ints(cards),
                'dynamicReq': ints(req), 'dynamicCards': ints(dyn)}
    if k == 'V':
        names = ['weather', 'horn', 'draw', 'scorch', 'summonClones', 'unsummon',
                 'improveNeighbours', 'nurse']
        if ',' in b:
            # Current recorder format: values joined with ",".
            vals = [num(x) for x in b.split(',')]
            if len(vals) != 8:
                raise RecError('V record needs 8 values: %r' % b)
        else:
            # Legacy format (first 6 recordings): values joined with "." although they can be
            # fractional (0.5 -> "0.5"), so the text is ambiguous. Every split into 8 Numbers is
            # enumerated; the record is accepted only if exactly one candidate equals the
            # constants sent by gwintGameMenu.ws SendCardValues(), otherwise it fails.
            cands = resolve_values(b.split('.'), 8)
            ok = [c for c in cands if c == SCRIPT_CARD_VALUES]
            if len(ok) != 1:
                raise RecError('card values %r do not match the script constants' % b)
            vals = ok[0]
        return {'k': 'V', 'values': dict(zip(names, vals))}
    if k == 'R':
        tag, v = b.split(':')
        u = int(v)
        if not 0 <= u <= 0xFFFFFFFF:
            raise RecError('random out of range %r' % r)
        return {'k': 'R', 'tag': tag, 'u32': u}
    if k == 'F':
        return {'k': 'F', 'first': int(b)}
    if k == 'S':
        d = parse_snapshot(b)
        d['k'] = 'S'
        return d
    if k == 'A':
        f = b.split(':')
        d = {'k': 'A', 'player': int(f[0]), 'attitude': int(f[1])}
        if len(f) == 3 and f[2] == 'none':
            d['tx'] = None
        elif len(f) == 8:
            d['tx'] = {'source': inst(f[2]), 'slot': int(f[3]), 'targetPlayer': int(f[4]),
                       'target': inst(f[5]), 'powerChange': num(f[6]), 'strategic': num(f[7])}
        else:
            raise RecError('bad A record %r' % r)
        return d
    if k == 'H':
        # Any play applied by either side (BasePlayerController.state_begin_ApplyingCard).
        player, rest = b.split(':', 1)
        if rest == 'none':
            return {'k': 'H', 'player': int(player), 'tx': None}
        f = rest.split(':')
        if len(f) != 4:
            raise RecError('bad H record %r' % r)
        return {'k': 'H', 'player': int(player),
                'tx': {'source': inst(f[0]), 'slot': int(f[1]), 'targetPlayer': int(f[2]), 'target': inst(f[3])}}
    if k == 'P':
        # Human pass (HumanPlayerController.skipTurn).
        return {'k': 'P', 'player': int(b)}
    if k == 'C':
        # Answer to a choice dialog: mulligan, nomulligan, nurse, handshow, resurrect, weather,
        # bin, pick (instance id or template id) or coin (true/false).
        name, _, arg = b.partition(':')
        return {'k': 'C', 'choice': name, 'arg': arg}
    if k == 'Y':
        # Scorch diagnostics are stored separately from logical replay events.
        f = b.split(':')
        if len(f) != 10 or f[0] not in ('start', 'end', 'applied'):
            raise RecError('bad FX trace %r' % r)
        values = list(map(int, f[3:]))
        if int(f[1]) <= 0 or any(v < 0 for v in values) or values[2] > values[3]:
            raise RecError('invalid FX trace values %r' % r)
        return dict(k='Y', phase=f[0], fxId=int(f[1]), card=inst(f[2]),
                    **dict(zip(('timeMs', 'frame', 'clipFrame', 'totalFrames', 'depth', 'children', 'activeFX'), values)))
    if k == 'Q':
        # Frame times of the Gwent screen in one window: the NPC thinking, or not (idle).
        f = b.split(':')
        if len(f) != 6 or f[0] not in ('think', 'idle'):
            raise RecError('bad frame window %r' % r)
        frames, total, peak, over33, over50 = map(int, f[1:])
        if min(frames, total, peak, over33, over50) < 0 or peak > total or not over50 <= over33 <= frames:
            raise RecError('invalid frame window %r' % r)
        return dict(k='Q', phase=f[0], frames=frames, totalMs=total, maxMs=peak, over33=over33, over50=over50)
    if k == 'X':
        # The recorder caught an error while building a record (the match itself went on).
        return {'k': 'X', 'where': b}
    if k == 'E':
        return {'k': 'E', 'reason': b}
    raise RecError('unknown record type %r' % r[:40])


def resolve_values(toks, n):
    """All ways to split a dot-joined list of Numbers ('int' or 'int.frac') into n values."""
    sols = []

    def rec(i, acc):
        if i == len(toks):
            if len(acc) == n:
                sols.append(list(acc))
            return
        if len(acc) >= n:
            return
        rec(i + 1, acc + [int(toks[i])])
        if i + 1 < len(toks):
            rec(i + 2, acc + [float(toks[i] + '.' + toks[i + 1])])
    rec(0, [])
    return sols


def load_match(raw, g):
    prefix = 'g%03d_' % g
    problems = []
    end = raw.get(prefix + 'end')
    chunks = {int(k[len(prefix):]): v for k, v in raw.items()
              if k.startswith(prefix) and re.fullmatch(r'\d{4}', k[len(prefix):])}
    info = {'game': g, 'chunksFound': len(chunks)}
    if end is None:
        problems.append('no %send key (match not closed)' % prefix)
    else:
        sent, stored, reason = end.split('/')
        info.update(sent=int(sent), stored=int(stored), reason=reason)
        if not (int(sent) == int(stored) == len(chunks)):
            problems.append('chunk count mismatch: sent=%s stored=%s found=%d' % (sent, stored, len(chunks)))
        if reason != 'final':
            problems.append('reason=%s (match not finished normally)' % reason)
    missing = [i for i in range(max(chunks) + 1 if chunks else 0) if i not in chunks]
    if missing:
        problems.append('missing chunk numbers %s' % missing)
    order = sorted(chunks)
    for i in order[:-1]:
        # gwaiEnd("quit") flushes the buffer even when the quit is cancelled.
        # Such interior short chunks are valid only at an explicit quit-record boundary.
        quit_flush = 0 < len(chunks[i]) < CHUNK and chunks[i].endswith('Equit;')
        if len(chunks[i]) != CHUNK and not quit_flush:
            problems.append('chunk %d has %d chars (expected %d)' % (i, len(chunks[i]), CHUNK))
    if order and not 0 < len(chunks[order[-1]]) <= CHUNK:
        problems.append('last chunk has %d chars' % len(chunks[order[-1]]))
    text = ''.join(chunks[i] for i in order)
    info['chars'] = len(text)
    if not text.endswith(';'):
        problems.append('stream does not end with ";"')
    records = []
    for n, r in enumerate(text.split(';')[:-1]):
        try:
            records.append(parse_record(r))
        except (RecError, ValueError) as e:
            problems.append('record %d unparsable (%s): %r' % (n, e, r[:80]))
    if records and records[-1]['k'] != 'E':
        problems.append('last record is not E')
    if records and end and records[-1].get('reason') != info.get('reason'):
        problems.append('E record reason %r != end key reason %r' % (records[-1].get('reason'), info.get('reason')))
    # A cancelled surrender leaves an "Equit" record mid-stream and the match goes on;
    # only the last E record closes the match.
    if any(r['k'] == 'E' and r.get('reason') != 'quit' for r in records[:-1]):
        problems.append('a final E record appears before the end of the stream')
    return info, records, problems


def structure(info, records):
    out = dict(info)
    out['templates'] = {}
    out['decks'] = {}
    out['events'] = []   # everything after the setup, in order (R, F, S, A, E)
    for r in records:
        if r['k'] == 'T':
            t = dict(r)
            del t['k']
            if str(r['index']) in out['templates']:
                raise RecError('template %d sent twice' % r['index'])
            out['templates'][str(r['index'])] = t
        elif r['k'] == 'I':
            if 'instanceBase' in out or out['events']:
                raise RecError('duplicate or late instance base')
            out['instanceBase'] = r['instanceBase']
        elif r['k'] == 'D':
            d = dict(r)
            del d['k']
            out['decks'][str(r['player'])] = d
        elif r['k'] == 'Y':
            trace = dict(r)
            del trace['k']
            trace['eventIndex'] = len(out['events'])
            out.setdefault('fxTrace', []).append(trace)
        elif r['k'] == 'Q':
            window = dict(r)
            del window['k']
            window['eventIndex'] = len(out['events'])
            out.setdefault('frames', []).append(window)
        elif r['k'] == 'V':
            out['cardValues'] = r['values']
        else:
            out['events'].append(r)
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else SETTINGS
    raw = read_section(path, SECTION)
    os.makedirs(OUT, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(path)))
    shutil.copy2(path, os.path.join(OUT, 'dx12user.settings.%s' % stamp))
    games = int(raw.pop('games'))
    known = set()
    bad = 0
    for g in range(games):
        prefix = 'g%03d_' % g
        known |= {k for k in raw if k.startswith(prefix)}
        info, records, problems = load_match(raw, g)
        if problems:
            bad += 1
            print('g%03d FAIL: %s' % (g, '; '.join(problems)))
            continue
        try:
            data = structure(info, records)
        except RecError as e:
            bad += 1
            print('g%03d FAIL: %s' % (g, e))
            continue
        json.dump(data, open(os.path.join(OUT, 'g%03d.json' % g), 'w'), indent=1)
        kinds = {}
        for r in records:
            kinds[r['k']] = kinds.get(r['k'], 0) + 1
        print('g%03d OK  %d/%d/%d chunks, %d chars, %s, records %s' % (
            g, info['sent'], info['stored'], info['chunksFound'], info['chars'], info['reason'],
            ' '.join('%s=%d' % kv for kv in sorted(kinds.items()))))
    extra = sorted(set(raw) - known)
    if extra:
        bad += 1
        print('unexpected keys in [%s]: %s' % (SECTION, extra[:10]))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
