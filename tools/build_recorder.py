#!/usr/bin/env python3
# Builds the match recorder: the game's gwint_game.redswf with recording hooks added
# (tools/recorder_as/*), packed as mod/recorder/modGwentAIRecorder/content/blob0.bundle +
# metadata.store. Every Math.random() in the rule classes becomes
# CardManager.gwaiRnd("<file><n>"), so the simulator can replay the exact values.
import argparse, os, re, subprocess, sys, tempfile, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import redswf  # noqa: E402

ROOT = os.path.join(HERE, '..')
SRC = os.path.join(ROOT, 'game', 'vanilla', 'swf', 'gwint_game.redswf')
OUT_DIR = os.path.join(ROOT, 'mod', 'recorder', 'modGwentAIRecorder', 'content')
RES_PATH = 'gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf'
FFDEC = os.path.join(HERE, 'ffdec', 'ffdec-cli.jar')
PKG = 'red.game.witcher3.menus.gwint'
PKG_DIR = os.path.join('red', 'game', 'witcher3', 'menus', 'gwint')

# Call-site tags for the random values (stable: n-th occurrence in the file).
RANDOM_TAGS = {
    'CardManager': 'CM', 'CardInstance': 'CI', 'CardLeaderInstance': 'CL', 'GwintDeck': 'DK',
    'GwintGameFlowController': 'FL', 'AIPlayerController': 'AI',
}


def ffdec(*args):
    r = subprocess.run(['java', '-jar', FFDEC] + list(args), capture_output=True, text=True)
    if r.returncode != 0 or 'error' in (r.stdout + r.stderr).lower():
        sys.exit('ffdec failed:\n' + (r.stdout + r.stderr)[-4000:])


def once(code, old, new):
    assert code.count(old) == 1, 'edit not found exactly once: ' + old[:80]
    return code.replace(old, new)


def once_re(code, pattern, repl):
    new, n = re.subn(pattern, repl, code, flags=re.S)
    assert n == 1, 'regex edit matched %d times: %s' % (n, pattern[:80])
    return new


def tag_randoms(code, tag):
    count = [0]

    def sub(_):
        count[0] += 1
        return 'CardManager.gwaiRnd("%s%d")' % (tag, count[0])
    code = re.sub(r'Math\.random\(\)', sub, code)
    return code, count[0]


def edit_classes(files, nl, autoplay_mulligan=True):
    # Tag the game's own random calls first, so the recorder's Math.random() stays untouched.
    for cls, tag in RANDOM_TAGS.items():
        files[cls], n = tag_randoms(files[cls], tag)
        print('  %-24s %2d random call sites' % (cls, n))

    block = open(os.path.join(HERE, 'recorder_as', 'CardManager.block.txt')).read()
    block = block.replace('\r\n', '\n').replace('\n', nl)

    c = files['CardManager']
    c = once_re(c, r'(package red\.game\.witcher3\.menus\.gwint\s*\{)', r'\1' + nl.replace('\\', '\\\\') + '   import red.core.events.GameEvent;')
    c = once(c, '      public function CardManager()', block + '      public function CardManager()')
    c = once(c, 'this._cardTemplates[cardTemplate.index] = cardTemplate;',
             'this._cardTemplates[cardTemplate.index] = cardTemplate;' + nl +
             '            gwaiRec("T" + cardTemplate.index + ":" + cardTemplate.power + ":" + cardTemplate.factionIdx + ":" + '
             'cardTemplate.typeArray + ":" + gwaiArr(cardTemplate.effectFlags) + ":" + gwaiArr(cardTemplate.summonFlags));')
    files['CardManager'] = c

    m = files['GwintGameMenu']
    m = once(m, '_cardManager.playerDeckDefinitions[CardManager.PLAYER_1] = gwintDeck;',
             '_cardManager.playerDeckDefinitions[CardManager.PLAYER_1] = gwintDeck;' + nl + '            CardManager.gwaiDeck(0,gwintDeck);')
    m = once(m, '_cardManager.playerDeckDefinitions[CardManager.PLAYER_2] = gwintDeck;',
             '_cardManager.playerDeckDefinitions[CardManager.PLAYER_2] = gwintDeck;' + nl + '            CardManager.gwaiDeck(1,gwintDeck);')
    # V record: ","-separated, because the values are Numbers (0.5) and "." would be ambiguous.
    m = once(m, '_cardManager.cardValues = cardValues as GwintCardValues;',
             '_cardManager.cardValues = cardValues as GwintCardValues;' + nl +
             '         CardManager.gwaiRec("V" + [_cardManager.cardValues.weatherCardValue,_cardManager.cardValues.hornCardValue,'
             '_cardManager.cardValues.drawCardValue,_cardManager.cardValues.scorchCardValue,_cardManager.cardValues.summonClonesCardValue,'
             '_cardManager.cardValues.unsummonCardValue,_cardManager.cardValues.improveNeighboursCardValue,_cardManager.cardValues.nurseCardValue].join(","));')
    m = once_re(m, r'(public function tryQuitGame\(\) : void\s*\{)', r'\1' + nl.replace('\\', '\\\\') + '         CardManager.gwaiEnd("quit");')
    files['GwintGameMenu'] = m

    f = files['GwintGameFlowController']
    f = once(f, 'this.cardManager.shuffleAndDrawCards();',
             'this.cardManager.shuffleAndDrawCards();' + nl +
             '         CardManager.gwaiRec("F" + this.currentPlayer);' + nl +
             '         this.cardManager.gwaiSnap("deal");')
    if autoplay_mulligan:
        f = once(f, 'GwintGameMenu.mSingleton.playSound("gui_gwint_draw_2");' + nl + '      }',
                 'GwintGameMenu.mSingleton.playSound("gui_gwint_draw_2");' + nl +
                 '         if(this.playerControllers[CardManager.PLAYER_1] is AIPlayerController)' + nl +
                 '         {' + nl + '            this.handleDeclineMulligan();' + nl + '         }' + nl + '      }')
    f = once(f, 'this.stateMachine.ChangeState("RoundStart");' + nl + '            this.mcChoiceDialog.hideDialog();',
             'this.stateMachine.ChangeState("RoundStart");' + nl + '            this.mcChoiceDialog.hideDialog();' + nl +
             '            this.cardManager.gwaiSnap("go");')
    f = once_re(f, r'(this\.cardManager\.recalculateScores\(\);)(\s*\}\s*protected function state_begin_ChangingPlayer)',
                r'\1' + nl.replace('\\', '\\\\') + '         this.cardManager.gwaiSnap("t" + this.currentRound + "." + this.currentPlayer);' + r'\2')
    f = once(f, 'this.cardManager.updatePlayerLives();',
             'this.cardManager.updatePlayerLives();' + nl + '         this.cardManager.gwaiSnap("rr" + this.currentRound);')
    f = once(f, 'this.cardManager.clearBoard(true);',
             'this.cardManager.clearBoard(true);' + nl + '         this.cardManager.gwaiSnap("clr" + this.currentRound);')
    f = once_re(f, r'(protected function state_begin_ShowingFinalResult\(\) : void\s*\{)',
                r'\1' + nl.replace('\\', '\\\\') + '         this.cardManager.gwaiSnap("fin");' + nl.replace('\\', '\\\\') + '         CardManager.gwaiEnd("final");')
    files['GwintGameFlowController'] = f

    # Player actions (needed to replay matches played by a human):
    # H = every play applied by either side, P = human pass, C = answers to choice dialogs.
    b = files['BasePlayerController']
    b = once_re(b, r'(protected function state_begin_ApplyingCard\(\) : void\s*\{)',
                r'\1' + nl + '         CardManager.gwaiPlay(this.playerID,this._decidedCardTransaction);')
    files['BasePlayerController'] = b
    h = files['HumanPlayerController']
    h = once(h, 'currentRoundStatus = BasePlayerController.ROUND_PLAYER_STATUS_DONE;' + nl + '            _turnOver = true;',
             'currentRoundStatus = BasePlayerController.ROUND_PLAYER_STATUS_DONE;' + nl + '            _turnOver = true;' + nl +
             '            CardManager.gwaiRec("P" + playerID);')
    files['HumanPlayerController'] = h
    choices = [
        ('GwintGameFlowController', 'handleAcceptMulligan', r'instanceId:int', '"mulligan:" + instanceId'),
        ('GwintGameFlowController', 'handleDeclineMulligan', r'', '"nomulligan"'),
        ('CardInstance', 'handleNurseChoice', r'instanceId:int', '"nurse:" + instanceId'),
        ('CardLeaderInstance', 'handleHandShowClose', r'instanceId:int = -1', '"handshow:" + instanceId'),
        ('CardLeaderInstance', 'handleResurrectChoice', r'instanceId:int = -1', '"resurrect:" + instanceId'),
        ('CardLeaderInstance', 'handleCardDrawChoice_Weather', r'templateID:int = -1', '"weather:" + templateID'),
        ('CardLeaderInstance', 'handleBinChoice', r'instanceId:int = -1', '"bin:" + instanceId'),
        ('CardLeaderInstance', 'handlePickChoice', r'templateID:int = -1', '"pick:" + templateID'),
        ('GwintGameMenu', 'setFirstTurn', r'playerFirst:Boolean', '"coin:" + playerFirst'),
    ]
    for cls, fn, args, expr in choices:
        files[cls] = once_re(files[cls], r'(function ' + fn + r'\(' + re.escape(args) + r'\) : void\s*\{)',
                             r'\1' + nl + '         CardManager.gwaiRec("C" + ' + expr + ');')

    a = files['AIPlayerController']
    a = once_re(a, r'(protected function state_update_ChooseMove\(\) : void\s*\{)',
                r'\1' + nl.replace('\\', '\\\\') + '         CardManager.gwaiTx(playerID,this.attitude,_decidedCardTransaction);')
    files['AIPlayerController'] = a



def edit_fx_trace(code, nl):
    """Add observations only; preserve the order of every original statement."""
    code = once(code, '   import flash.events.TimerEvent;',
                '   import flash.events.TimerEvent;' + nl + '   import flash.events.Event;' + nl +
                '   import flash.utils.getTimer;' + nl + '   import flash.utils.getQualifiedClassName;')
    block = open(os.path.join(HERE, 'recorder_as', 'CardFXManager.trace.txt')).read()
    block = block.replace('\r\n', '\n').replace('\n', nl)
    code = once(code, '      protected static var _instance:CardFXManager;',
                block + '      protected static var _instance:CardFXManager;')
    code = once(code, '         this.setupWeatherEffects();',
                '         this.setupWeatherEffects();' + nl +
                '         this.addEventListener(Event.ENTER_FRAME,this.gwaiFrameTick,false,0,true);')
    # spawnFX is the path used by Scorch (not spawnFX_Location or playRowEffect).
    code = once(code, '         ++this.numEffectsPlaying;' + nl + '         return newCardFX;',
                '         ++this.numEffectsPlaying;' + nl +
                '         this.gwaiTraceScorch("start",newCardFX);' + nl + '         return newCardFX;')
    code = once_re(code, r'(protected function finishedFXCallback\(cardFX:CardFX\) : void\s*\{)',
                   r'\1' + nl + '         this.gwaiTraceScorch("end",cardFX);')
    # Log callback return before removal; original statements remain in place.
    code = once(code, '         removeChild(cardFX);',
                '         this.gwaiTraceScorch("applied",cardFX);' + nl + '         removeChild(cardFX);')
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace-fx', action='store_true', help='record Scorch creation/completion frames')
    parser.add_argument('--out-dir', help='override bundle output directory')
    args = parser.parse_args()
    out_dir = args.out_dir or (os.path.join(ROOT, 'mod', 'recorder-fx', 'modGwentAIRecorder', 'content')
                               if args.trace_fx else OUT_DIR)
    red = open(SRC, 'rb').read()
    swf, trailer = redswf.split_redswf(red)
    classes = sorted(set(RANDOM_TAGS) | {'GwintGameMenu', 'BasePlayerController', 'HumanPlayerController'} |
                     ({'CardFXManager'} if args.trace_fx else set()))
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'in.swf')
        out = os.path.join(tmp, 'out.swf')
        open(src, 'wb').write(swf)
        ffdec('-selectclass', ','.join(PKG + '.' + c for c in classes), '-export', 'script', os.path.join(tmp, 'as'), src)
        files = {c: open(os.path.join(tmp, 'as', 'scripts', PKG_DIR, c + '.as'), encoding='utf-8').read() for c in classes}
        nl = '\r\n' if '\r\n' in files['CardManager'] else '\n'
        edit_classes(files, nl)
        if args.trace_fx:
            files['CardFXManager'] = edit_fx_trace(files['CardFXManager'], nl)
        imp = os.path.join(tmp, 'import', PKG_DIR)
        os.makedirs(imp)
        for c, code in files.items():
            open(os.path.join(imp, c + '.as'), 'w', encoding='utf-8').write(code)
        ffdec('-importScript', src, out, os.path.join(tmp, 'import'))
        new_swf = open(out, 'rb').read()
    if new_swf[:3] == b'CWS':
        new_swf = b'FWS' + new_swf[3:8] + zlib.decompress(new_swf[8:])
    new_red = redswf.patch_redswf(red, new_swf, trailer)
    blob, meta = redswf.build_bundle([(RES_PATH, new_red, True)])
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'blob0.bundle'), 'wb').write(blob)
    open(os.path.join(out_dir, 'metadata.store'), 'wb').write(meta)
    print('swf %d -> %d bytes, bundle %d bytes' % (len(swf), len(new_swf), len(blob)))


if __name__ == '__main__':
    main()
