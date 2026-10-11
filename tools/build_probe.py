#!/usr/bin/env python3
# Builds the stage 2 probe: the game's gwint_game.redswf with probe code added to
# GwintGameMenu (tools/probe_as/GwaiProbe.as.txt), packed as
# mod/probe/modGwentAIProbe/content/blob0.bundle + metadata.store.
# Input is game/vanilla/swf/gwint_game.redswf (run extract_vanilla.py after a game patch).
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import redswf  # noqa: E402

ROOT = os.path.join(HERE, '..')
SRC = os.path.join(ROOT, 'game', 'vanilla', 'swf', 'gwint_game.redswf')
OUT_DIR = os.path.join(ROOT, 'mod', 'probe', 'modGwentAIProbe', 'content')
RES_PATH = 'gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf'
FFDEC = os.path.join(HERE, 'ffdec', 'ffdec-cli.jar')
CLASS = 'red.game.witcher3.menus.gwint.GwintGameMenu'
FILE = os.path.join('red', 'game', 'witcher3', 'menus', 'gwint', 'GwintGameMenu.as')


def ffdec(*args):
    subprocess.run(['java', '-jar', FFDEC] + list(args), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def edit(code, old, new):
    assert code.count(old) == 1, 'ActionScript changed, edit not found: ' + old
    return code.replace(old, new)


def main():
    red = open(SRC, 'rb').read()
    swf, trailer = redswf.split_redswf(red)
    block = open(os.path.join(HERE, 'probe_as', 'GwaiProbe.as.txt')).read()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'in.swf')
        out = os.path.join(tmp, 'out.swf')
        open(src, 'wb').write(swf)
        ffdec('-selectclass', CLASS, '-export', 'script', os.path.join(tmp, 'as'), src)
        code = open(os.path.join(tmp, 'as', 'scripts', FILE), encoding='utf-8').read()
        nl = '\r\n' if '\r\n' in code else '\n'
        block = block.replace('\r\n', '\n').replace('\n', nl)
        code = edit(code, 'import flash.geom.Point;',
                    'import flash.geom.Point;' + nl + '   import flash.system.Capabilities;' + nl + '   import flash.utils.ByteArray;')
        code = edit(code, '      public function setCardValues(cardValues:Object) : void',
                    block + '      public function setCardValues(cardValues:Object) : void')
        code = edit(code, '_cardManager.cardValues = cardValues as GwintCardValues;',
                    '_cardManager.cardValues = cardValues as GwintCardValues;' + nl + '         this.gwaiRunProbes();')
        imp = os.path.join(tmp, 'import')
        os.makedirs(os.path.dirname(os.path.join(imp, FILE)))
        open(os.path.join(imp, FILE), 'w', encoding='utf-8').write(code)
        ffdec('-importScript', src, out, imp)
        new_swf = open(out, 'rb').read()
    if new_swf[:3] == b'CWS':
        import zlib
        new_swf = b'FWS' + new_swf[3:8] + zlib.decompress(new_swf[8:])
    assert new_swf != swf, 'import produced an unchanged SWF'
    new_red = redswf.patch_redswf(red, new_swf, trailer)
    blob, meta = redswf.build_bundle([(RES_PATH, new_red, True)])
    os.makedirs(OUT_DIR, exist_ok=True)
    open(os.path.join(OUT_DIR, 'blob0.bundle'), 'wb').write(blob)
    open(os.path.join(OUT_DIR, 'metadata.store'), 'wb').write(meta)
    print('swf %d -> %d bytes, redswf %d bytes, bundle %d bytes' % (len(swf), len(new_swf), len(new_red), len(blob)))


if __name__ == '__main__':
    main()
