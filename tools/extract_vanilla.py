#!/usr/bin/env python3
# Extracts every vanilla file the Gwent minigame depends on into game/vanilla/:
#   swf/      gwint_game.redswf (+ the plain SWF without the Scaleform trailer)
#   xml/      card, leader and deck definitions (base game and DLC bundles)
#   scripts/  the WitcherScript files that talk to the minigame
# and writes game/vanilla/MANIFEST.txt with sizes and CRC32 of every file, so a game
# update can be detected by re-running this script and diffing the manifest.
import glob, os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bundle  # noqa: E402

GAME = os.path.expanduser('~/.local/share/Steam/steamapps/common/The Witcher 3')
OUT = os.path.join(HERE, '..', 'game', 'vanilla')

SWF_PATHS = {'gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf'}
XML_KEYS = ('gwint', 'gwent')
SCRIPT_KEYS = ('gwint', 'gwent')


def save(rel, data):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(data)
    return path


def redswf_to_swf(red):
    c0 = red.find(b'CFX')
    ln = struct.unpack('<I', red[c0 + 4:c0 + 8])[0]
    full = b'FWS' + red[c0 + 3:c0 + 8] + zlib.decompressobj().decompress(red[c0 + 8:])
    return full[:ln]


def main():
    manifest = []
    bundles = sorted(glob.glob(os.path.join(GAME, 'content', '*', 'bundles', '*.bundle')))
    bundles += sorted(glob.glob(os.path.join(GAME, 'dlc', '*', 'content', 'bundles', '*.bundle')))
    for b in bundles:
        src = os.path.relpath(b, GAME)
        try:
            entries = bundle.toc(b)
        except Exception:
            continue
        for e in entries:
            name = e[0]
            low = name.lower()
            if name in SWF_PATHS:
                data = bundle.extract(b, e)
                save(os.path.join('swf', 'gwint_game.redswf'), data)
                save(os.path.join('swf', 'gwint_game.swf'), redswf_to_swf(data))
                manifest.append((name, src, len(data), zlib.crc32(data)))
            elif low.endswith('.xml') and any(k in low for k in XML_KEYS):
                data = bundle.extract(b, e)
                tag = src.split(os.sep)[1] if src.startswith('dlc') else src.split(os.sep)[1]
                save(os.path.join('xml', tag, name.replace('\\', os.sep)), data)
                manifest.append((name, src, len(data), zlib.crc32(data)))

    sroot = os.path.join(GAME, 'content', 'content0', 'scripts')
    for path in sorted(glob.glob(os.path.join(sroot, '**', '*.ws'), recursive=True)):
        raw = open(path, 'rb').read()
        text = raw.decode('utf-16', 'ignore') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8', 'ignore')
        if any(k in text.lower() for k in SCRIPT_KEYS):
            rel = os.path.relpath(path, sroot)
            dst = os.path.join(OUT, 'scripts', rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(path, dst)
            manifest.append(('scripts\\' + rel.replace(os.sep, '\\'), 'content0/scripts', len(raw), zlib.crc32(raw)))

    with open(os.path.join(OUT, 'MANIFEST.txt'), 'w') as f:
        for name, src, size, crc in sorted(manifest):
            f.write('%08x %9d %-40s %s\n' % (crc, size, src, name))
    print(len(manifest), 'files')


if __name__ == '__main__':
    main()
