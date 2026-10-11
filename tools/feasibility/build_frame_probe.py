#!/usr/bin/env python3
"""Build a private SWF dummy probe from local vanilla; never install it.

Adds an original internal AS3 class in an existing script pack. The patched native
script is temporary/private, never publication source. Runtime metrics require the
my in-game test and the accompanying original WS event.
"""
import hashlib,json,re,subprocess,tempfile,sys,zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import redswf
PKG='red.game.witcher3.menus.gwint'

def main():
    src=ROOT/'game/vanilla/swf/gwint_game.swf'
    probe=ROOT/'mod/feasibility/as3/GwaiFrameBudgetProbe.as'
    dest=ROOT/'game/feasibility/frame-probe'
    dest.mkdir(parents=True,exist_ok=True)
    jar=ROOT/'tools/ffdec/ffdec-cli.jar'
    logs=[]
    def ffdec(*args):
        result=subprocess.run(['java','-jar',str(jar),*map(str,args)],capture_output=True,text=True)
        logs.append(result.stdout+result.stderr)
        if result.returncode or re.search(r'\b(error|exception)\b',logs[-1],re.I):
            raise RuntimeError(logs[-1][-5000:])
    report=dict(sourceSha256=hashlib.sha256(src.read_bytes()).hexdigest(),
        originalProbeSha256=hashlib.sha256(probe.read_bytes()).hexdigest(),installed=False,
        runtimeVerified=False,workload='dummy arithmetic; not ISMCTS throughput')
    try:
        with tempfile.TemporaryDirectory(prefix='gwai-frame-probe-') as tmp:
            tmp=Path(tmp)
            ffdec('-selectclass',PKG+'.AIPlayerController','-export','script',tmp/'export',src)
            path=tmp/'export/scripts'/Path(PKG.replace('.','/'))/'AIPlayerController.as'
            text=path.read_text()
            pattern=r'(protected function state_begin_ChoseMove\(\)\s*:\s*void\s*\{)'
            text,n=re.subn(pattern,r'\1\n         GwaiFrameBudgetProbe.attach(GwintGameMenu.mSingleton);',text)
            if n!=1:raise RuntimeError('native hook not uniquely found')
            offset=text.rfind('}')
            text=text[:offset]+ '\n'+probe.read_text()+'\n'+text[offset:]
            target=tmp/'import'/Path(PKG.replace('.','/'))/'AIPlayerController.as'
            target.parent.mkdir(parents=True);target.write_text(text)
            ffdec('-importScript',src,dest/'gwint_game.swf',tmp/'import')
            ffdec('-selectclass',PKG+'.GwaiFrameBudgetProbe','-export','script',tmp/'verify',dest/'gwint_game.swf')
            found=list((tmp/'verify').rglob('*GwaiFrameBudgetProbe*.as'))
            if not found:raise RuntimeError('compiled output lacks new class')
            verified=found[0].read_text()
            if 'REMOVED_FROM_STAGE' not in verified or 'removeEventListener' not in verified:
                raise RuntimeError('compiled probe lacks listener cleanup')
            ffdec('-selectclass',PKG+'.AIPlayerController','-export','script',tmp/'verify-hook',dest/'gwint_game.swf')
            verified_hook=(tmp/'verify-hook/scripts'/Path(PKG.replace('.','/'))/'AIPlayerController.as').read_text()
            if len(re.findall(r'GwaiFrameBudgetProbe\s*\.\s*attach\s*\(',verified_hook))!=1:
                raise RuntimeError('compiled decision hook not uniquely found')
            compiled=(dest/'gwint_game.swf').read_bytes()
            if compiled[:3]==b'CWS':compiled=b'FWS'+compiled[3:8]+zlib.decompress(compiled[8:])
            raw=(ROOT/'game/vanilla/swf/gwint_game.redswf').read_bytes()
            _,trailer=redswf.split_redswf(raw)
            patched=redswf.patch_redswf(raw,compiled,trailer)
            bundle,meta=redswf.build_bundle([('gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf',patched,True)])
            content=ROOT/'mod/feasibility/frame-probe/modGwentAIFrameProbe/content'
            content.mkdir(parents=True,exist_ok=True)
            (content/'blob0.bundle').write_bytes(bundle)
            (content/'metadata.store').write_bytes(meta)
            script=content/'scripts/local/gwai_search_probe.ws'
            script.parent.mkdir(parents=True,exist_ok=True)
            script.write_bytes((ROOT/'mod/feasibility/as3/gwai_search_probe.ws').read_bytes())
            report.update(status='compiled_class_verified',swfSha256=hashlib.sha256((dest/'gwint_game.swf').read_bytes()).hexdigest())
            report['offlinePackage']=str(content.parent.relative_to(ROOT))
            report['witcherScriptEngineCompiled']=False
            report['attachHookVerified']=True
            report['cleanupCodeVerified']=True
            report['packageSha256']={str(p.relative_to(content)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(content.rglob('*')) if p.is_file()}
            if hashlib.sha256(src.read_bytes()).hexdigest()!=report['sourceSha256']:
                raise RuntimeError('native source changed during offline build')
    except Exception as error:
        report.update(status='build_failed',error=str(error))
    (dest/'build.log').write_text('\n'.join(logs))
    (dest/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return int(report['status']!='compiled_class_verified')

if __name__=='__main__':raise SystemExit(main())
