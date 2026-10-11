#!/usr/bin/env python3
# Reads the probe results written by the game ([GwaiProbe2] in dx12user.settings), joins the
# chunks and saves them as game/probes/scaleform.json:
#   {"info": "...", "random": [hex, ...], "numbers": [[text, hex], ...],
#    "sort": [{"case": name, "keys": [...], "out": [...]}, ...]}
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.expanduser('~/.local/share/Steam/steamapps/compatdata/292030/pfx/drive_c/users/'
                              'steamuser/Documents/The Witcher 3/dx12user.settings')
OUT = os.path.join(HERE, '..', 'game', 'probes', 'scaleform.json')


def read_section(path, name):
    vals, inside = {}, False
    for line in open(path, encoding='utf-8', errors='replace').read().splitlines():
        if line.startswith('['):
            inside = line.strip() == '[%s]' % name
            continue
        if inside and '=' in line:
            k, v = line.split('=', 1)
            vals[k] = v[1:-1] if v.startswith('"') and v.endswith('"') else v
    return vals


def main():
    raw = read_section(sys.argv[1] if len(sys.argv) > 1 else SETTINGS, 'GwaiProbe2')
    sent, stored = map(int, raw.pop('count').split('/'))
    assert sent == stored == len(raw), 'records lost: count=%d/%d, found %d' % (sent, stored, len(raw))
    parts = {}
    for v in raw.values():
        name, data = v.split('|=|', 1)
        base, idx = name.rsplit('#', 1)
        parts.setdefault(base, {})[int(idx)] = data
    joined = {k: ''.join(p[i] for i in sorted(p)) for k, p in parts.items()}
    res = {'info': joined.pop('info'), 'records': stored}
    res['random'] = joined.pop('random').split(',')
    res['numbers'] = [x.split('~') for x in joined.pop('numbers').split(',')]
    res['sort'] = []
    for name in sorted(joined, key=lambda n: (int(re.search(r'\|n(\d+)', n).group(1)), n)):
        keys, out = joined[name].split('=>')
        res['sort'].append({'case': name, 'keys': [int(x) for x in keys.split(',')],
                            'out': [int(x) for x in out.split(',')]})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, 'w'), indent=1)
    print(res['info'], '|', len(res['sort']), 'sort cases,', len(res['random']), 'random,', len(res['numbers']), 'numbers')


if __name__ == '__main__':
    main()
