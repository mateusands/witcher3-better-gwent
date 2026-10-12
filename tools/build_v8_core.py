#!/usr/bin/env python3
"""Compile original V8 core classes offline, without modifying/installing the game.

This interim artifact includes a decision hook. Autoplay and recorder packaging
remain required before producing the installable Better Gwent AI mod.
"""
import argparse,hashlib,json,re,subprocess,tempfile,shutil
from pathlib import Path
from v8_runtime_patch import NATIVE_CLASSES, DECK_BUILDER_CLASSES, patch, deck_builder_patch
from v8_ai_patch import patch_ai
ROOT=Path(__file__).resolve().parents[1]
PKG='red.game.witcher3.menus.gwint'
CLASSES=['GwaiV8Const','GwaiV8Position','GwaiV8Capture','GwaiV8Reserve','GwaiV8Mulligan','GwaiV8Sequence','GwaiV8Random','GwaiV8Hash','GwaiV8Belief','GwaiV8Response','GwaiV8Policy','GwaiV8Context','GwaiV8Execution','GwaiV8SequenceTask','GwaiV8Runner']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-recorder',action='store_true')
    parser.add_argument('--trace-calls',action='store_true',help='diagnostic build: tag errors with the V8 call chain')
    args=parser.parse_args()
    source=ROOT/'game/vanilla/swf/gwint_game.swf';dest=ROOT/('game/port-v8/combined' if args.with_recorder else 'game/port-v8/core')
    dest.mkdir(parents=True,exist_ok=True);logs=[]
    def ffdec(*args):
        result=subprocess.run(['java','-jar',str(ROOT/'tools/ffdec/ffdec-cli.jar'),*map(str,args)],capture_output=True,text=True)
        logs.append(result.stdout+result.stderr)
        if result.returncode or re.search(r'\b(error|exception)\b',logs[-1],re.I):raise RuntimeError(logs[-1][-7000:])
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    deck_source=ROOT/'game/vanilla/swf/deck_builder.swf'
    inputs={str(source.relative_to(ROOT)):sha(source),str(deck_source.relative_to(ROOT)):sha(deck_source)}
    inputs['tools/v8_runtime_patch.py']=sha(ROOT/'tools/v8_runtime_patch.py')
    inputs['tools/v8_ai_patch.py']=sha(ROOT/'tools/v8_ai_patch.py')
    for name in CLASSES:inputs[f'mod/v8/as3/{name}.as']=sha(ROOT/f'mod/v8/as3/{name}.as')
    report=dict(traceCalls=args.trace_calls,installed=False,decisionHookConnected=False,recorderMerged=False,inputs=inputs,runtimeGameVerified=False)
    try:
        with tempfile.TemporaryDirectory(prefix='gwai-v8-core-') as tmp:
            tmp=Path(tmp);package=Path(PKG.replace('.','/'))
            # Patch existing simple scripts before appending multi-class AI code.
            names=set(NATIVE_CLASSES)
            if args.with_recorder:
                from build_recorder import RANDOM_TAGS,edit_classes
                from v8_recorder_patch import patch_restart
                names.update(RANDOM_TAGS);names.add('HumanPlayerController')
                for p in ['tools/build_recorder.py','tools/v8_recorder_patch.py','tools/recorder_as/CardManager.block.txt','tools/recorder_as/CardManager.restart.txt']:
                    inputs[p]=sha(ROOT/p)
            ffdec('-selectclass',','.join(PKG+'.'+name for name in sorted(names)),'-export','script',tmp/'native-export',source)
            native_dir=tmp/'native-import'/package;native_dir.mkdir(parents=True)
            files={name:(tmp/'native-export/scripts'/package/(name+'.as')).read_text().replace('\r\n','\n') for name in names}
            for name in NATIVE_CLASSES:files[name]=patch(name,files[name])
            if args.with_recorder:
                edit_classes(files,'\n',autoplay_mulligan=False)
                patch_restart(files)
            for name,code in files.items():(native_dir/(name+'.as')).write_text(code)
            native_base=tmp/'native.swf'
            ffdec('-importScript',source,native_base,tmp/'native-import')
            ffdec('-selectclass',PKG+'.AIPlayerController','-export','script',tmp/'export',native_base)
            original=(tmp/'export/scripts'/package/'AIPlayerController.as').read_text()
            original=patch_ai(original)
            # Recorder builds also store V8 diagnostics (fallbacks, errors) as "X" events.
            original=original.replace('/*GWAI_REC_NOTE*/','CardManager.gwaiRec("Xgwai:" + text);' if args.with_recorder else '')
            offset=original.rfind('}')
            def v8_source(name):
                text=(ROOT/f'mod/v8/as3/{name}.as').read_text()
                if args.trace_calls:
                    from v8_trace import instrument
                    text=instrument(text,name)[0]
                return text
            code=original[:offset]+'\n'+'\n'.join(v8_source(name) for name in CLASSES)+'\n'+original[offset:]
            target=tmp/'import'/package/'AIPlayerController.as';target.parent.mkdir(parents=True)
            # Same-script classes cannot be reimported by the bulk importer.
            # Use dynamic Object annotations for self references on first compile.
            # Only type annotations: an object key followed by a static call (hero:GwaiV8Position.isType)
            # must keep the class name, otherwise it compiles to Object.isType (Error #1006 in game).
            target.write_text(re.sub(r':(\s*)GwaiV8Position\b(?!\s*[.(])',r':\1Object',code))
            ffdec('-importScript',native_base,tmp/'registered.swf',tmp/'import')
            shutil.copyfile(tmp/'registered.swf',dest/'gwint_game.swf')
            report['compiledMembers']={}
            for name in CLASSES:
                ffdec('-selectclass',PKG+'.'+name,'-export','script',tmp/name,dest/'gwint_game.swf')
                found=list((tmp/name).rglob(name+'.as'))
                if not found:raise RuntimeError('Compiled class missing: '+name)
                exported=found[0].read_text()
                methods=re.findall(r'public (?:static )?function (\w+)\(', (ROOT/f'mod/v8/as3/{name}.as').read_text())
                for method in methods:
                    if method in ('GwaiV8Unsupported','GwaiV8Budget'):continue
                    if not re.search(r'function\s+'+method+r'\s*\(',exported):
                        raise RuntimeError('Compiled method missing: '+name+'.'+method)
                constants=re.findall(r'public static const (\w+):', (ROOT/f'mod/v8/as3/{name}.as').read_text())
                for constant in constants:
                    if not re.search(r'const\s+'+constant+r'\s*:',exported):
                        raise RuntimeError('Compiled constant missing: '+name+'.'+constant)
                report['compiledMembers'][name]={'methods':methods,'constants':constants}
                audit=dest/'compiled-source'/ (name+'.as');audit.parent.mkdir(exist_ok=True)
                audit.write_text(exported)
            expected_native={'AIPlayerController':['gwaiCancelV8','gwaiShutdownV8','gwaiBeginV8','gwaiAllowedPass','gwaiNativeFallback','gwaiPumpV8','gwaiNote','gwaiPumpV8Step','gwaiNpcMulligan'],
                'BasePlayerController':['gwaiObservedRoundStatus'],
                'CardManager':['gwaiAssignCopy','gwaiCopyOrdinal','gwaiKnownHand','gwaiPublicHandCount','gwaiClearPlan','gwaiStorePlan','gwaiActivePlan','gwaiLeaderTarget','gwaiNurseChoice','gwaiTakePlacement'],
                'GwintGameFlowController':['gwaiRoundIndex','gwaiConfigure','gwaiSettingsReady','gwaiProfileForPlayer','gwaiSettingsSnapshot','gwaiApplyControllers','gwaiStopSearches'],
                'GwintGameMenu':['gwaiConfigureMatch','gwaiStopMatch'],
                'CardInstance':['updateEffectsApplied','onNurseEffectEnded'],
                'CardLeaderInstance':['ApplyLeaderAbility','pickWeather'],
                'CardSlot':['gwaiBondPicture','setupCardWithTemplate']}
            for name,methods in expected_native.items():
                ffdec('-selectclass',PKG+'.'+name,'-export','script',tmp/name,dest/'gwint_game.swf')
                exported=(tmp/name/'scripts'/package/(name+'.as')).read_text()
                for method in methods:
                    if not re.search(r'function\s+(?:get\s+)?'+method+r'\s*\(',exported):
                        raise RuntimeError('Compiled native bridge missing: '+name+'.'+method)
                (dest/'compiled-source'/(name+'.as')).write_text(exported)
                hooks={'AIPlayerController':['gwaiBeginV8','gwaiPumpV8','GwaiV8Execution.prepare','GwaiV8Capture.capture','GwaiV8Runner','GwaiV8Mulligan.chooseWithLeader'],
                    'GwintGameFlowController':['gwaiNpcMulligan'],
                    'CardInstance':['gwaiNurseChoice','gwaiTakePlacement'],
                    'CardLeaderInstance':['gwaiLeaderTarget'],
                    'CardSlot':['gwaiBondPicture(cardTemplate,this._instanceId)','gwaiCopyOrdinal','nil_impera_brigade_3','nor_catapult_1','nor_blue_stripes_2','nor_siege_tower_1'],
                    'CardManager':['gwaiAssignCopy(newInstance)','delete this._gwaiCopy']}.get(name,[])
                for hook in hooks:
                    if hook not in exported:raise RuntimeError('Compiled choice hook missing: '+name+'.'+hook)
            if args.with_recorder:
                for name,tokens in {'CardManager':['gwaiRnd','gwaiSnap','gwaiRec','gwaiRecorderRestart'],
                        'GwintGameFlowController':['gwaiRecorderRestart','gwaiSnap'],
                        'AIPlayerController':['gwaiTx'], 'BasePlayerController':['gwaiPlay'],
                        'GwintGameMenu':['CardManager.gwaiEnd("close")']}.items():
                    exported=(dest/'compiled-source'/(name+'.as')).read_text()
                    for token in tokens:
                        if token not in exported:raise RuntimeError('Compiled recorder hook missing: '+name+'.'+token)
                exported=(dest/'compiled-source'/'AIPlayerController.as').read_text()
                update=exported[exported.index('function state_update_ChooseMove'):exported.index('function state_begin_SendingCard')]
                if update.index('gwaiPumpV8')>update.index('gwaiTx'):raise RuntimeError('Recorder logs unfinished search steps')
                exported=(dest/'compiled-source'/'GwintGameFlowController.as').read_text()
                if exported.index('gwaiSnap("deal")')>exported.index('gwaiNpcMulligan'):raise RuntimeError('Deal snapshot after the NPC exchange')
                report['recorderMerged']=True
            # Deck builder: its own SWF, patched for its card art and copy tiles (same export/patch/import route).
            ffdec('-selectclass',','.join(PKG+'.'+name for name in DECK_BUILDER_CLASSES),'-export','script',tmp/'deck-export',deck_source)
            deck_dir=tmp/'deck-import'/package;deck_dir.mkdir(parents=True)
            for name in DECK_BUILDER_CLASSES:
                code=(tmp/'deck-export/scripts'/package/(name+'.as')).read_text()
                (deck_dir/(name+'.as')).write_text(deck_builder_patch(name,code))
            ffdec('-importScript',deck_source,dest/'deck_builder.swf',tmp/'deck-import')
            deck_hooks={'CardSlot':['gwaiDeckPicture(param1,data)','gwaiDeckArt','gwaiCopyPictures','nil_impera_brigade_3','nor_catapult_1','nor_blue_stripes_2','nor_siege_tower_1'],
                'DeckBuilderMenu':['"gwai.deck.bondart"','gwaiUpdateDeckArt','CardSlot.gwaiDeckArt = ','gwaiCopyFromTop = true','CardSlot.gwaiOwnedCopies['],
                'GwintDeckCTabModule':['gwaiSetCopies(param1,param2)','gwaiSplitCopies(_loc2_)','gwaiCopyEntry','int(param1.gwaiCopy) - int(param2.gwaiCopy)']}
            for name,tokens in deck_hooks.items():
                ffdec('-selectclass',PKG+'.'+name,'-export','script',tmp/('deck-'+name),dest/'deck_builder.swf')
                exported=(tmp/('deck-'+name)/'scripts'/package/(name+'.as')).read_text()
                for token in tokens:
                    if token not in exported:raise RuntimeError('Compiled deck builder hook missing: '+name+'.'+token)
                audit=dest/'compiled-source/deck_builder'/(name+'.as');audit.parent.mkdir(parents=True,exist_ok=True)
                audit.write_text(exported)
            exported=(dest/'compiled-source/deck_builder/DeckBuilderMenu.as').read_text()
            if exported.index('"gwai.deck.bondart"')>exported.index('"gwint.deckbuilder.decks"'):raise RuntimeError('Deck art switch registered after the deck data')
            report['deckBuilderSha256']=sha(dest/'deck_builder.swf')
            report['decisionHookConnected']=True
            report['publicContextBridgeCompiled']=True
            report['settingsBridgeCompiled']=True
            report['autoplayControllerConnected']=True
            report['explicitChoiceHooksCompiled']=True
            assert sha(source)==inputs[str(source.relative_to(ROOT))] and sha(deck_source)==inputs[str(deck_source.relative_to(ROOT))]
            report.update(status='core_compiled',compiledSha256=sha(dest/'gwint_game.swf'))
    except Exception as exc:report.update(status='build_failed',error=str(exc))
    (dest/'build.log').write_text('\n'.join(logs));(dest/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return int(report['status']!='core_compiled')

if __name__=='__main__':raise SystemExit(main())
