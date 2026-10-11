#!/usr/bin/env python3
"""Static 5.01 wrapper declaration checks; NOT a WitcherScript compiler."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECL = re.compile(r'\b(function|event)\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([\w<>]+))?')
ANNOTATION = re.compile(r'@wrapMethod\((\w*)\)\s*(?:(?:public|private|protected|final|latent)\s+)*(function|event)\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([\w<>]+))?')


def mask(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text, flags=re.S)


def signature(kind, arguments, result):
    args = []
    for item in arguments.split(','):
        item = item.strip()
        if item:
            modifiers = [x for x in ('optional', 'out') if re.search(r'\b'+x+r'\b', item)]
            key, typ = item.split(':', 1)
            args.append((tuple(modifiers), re.sub(r'\b(optional|out)\b', '', key).strip().lower(), typ.strip().lower()))
    return kind, args, (result or 'void').lower()


def enclosing_classes(text):
    result = []
    for match in re.finditer(r'\b(?:import\s+)?class\s+(\w+)[^{;]*\{', text):
        start = match.end()-1
        depth, pos = 1, start+1
        while depth and pos < len(text):
            depth += (text[pos] == '{') - (text[pos] == '}');pos += 1
        result.append((start, pos, match.group(1)))
    return result


def inspect(vanilla_root):
    declarations = {}
    for path in Path(vanilla_root).rglob('*.ws'):
        raw = path.read_bytes()
        text = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8-sig', errors='replace')
        clean = mask(text); classes = enclosing_classes(clean)
        for match in DECL.finditer(clean):
            parent = next((name for start,end,name in classes if start < match.start() < end), '')
            key = parent, match.group(2).lower()
            try:
                sig = signature(match.group(1), match.group(3), match.group(4))
            except ValueError:
                continue
            declarations.setdefault(key, []).append((sig, str(path.relative_to(vanilla_root)), text.count('\n',0,match.start())+1))
    checks = []
    for path in (ROOT/'mod/settings/modGwentAISettings/content/scripts/local').glob('*.ws'):
        text = path.read_text();clean = mask(text)
        assert clean.count('{') == clean.count('}'), str(path)
        for match in ANNOTATION.finditer(clean):
            expected = signature(match.group(2),match.group(4),match.group(5))
            found = declarations.get((match.group(1), match.group(3).lower()), [])
            # In WitcherScript 4.0+, @wrapMethod always uses 'function', even when wrapping vanilla 'event' targets.
            same = [item for item in found if item[0] == expected or item[0][1:] == expected[1:]]
            checks.append(dict(source=path.name, hook=match.group(1)+'.'+match.group(3),
                matched=bool(same), vanillaLocations=[dict(file=p,line=n) for _,p,n in same]))
    return dict(status='static_contract_pass' if checks and all(c['matched'] for c in checks) else 'static_contract_fail',
                engineCompiled=False, checks=checks,
                limitation='Signature and brace checks only; no engine type, annotation or runtime validation.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vanilla',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=inspect(args.vanilla)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],len(report['checks']),'hooks; engineCompiled=False')
    for item in report['checks']:
        if not item['matched']:print('UNMATCHED',item['hook'])
    return int(report['status']!='static_contract_pass')


if __name__=='__main__':raise SystemExit(main())
