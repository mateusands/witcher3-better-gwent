#!/usr/bin/env python3
"""Package the verified combined SWF and original WS/menu sources, offline only."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zipfile
import zlib

from redswf import split_redswf,patch_redswf,build_bundle
import bundle
import metastore
from build_settings import build,LANGUAGES

ROOT=Path(__file__).resolve().parents[1]
RESOURCE='gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf'
NAME='BetterGwentAI-V8-5.01-test'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_swf(data):
    if data[:3]==b'CWS':data=b'FWS'+data[3:8]+zlib.decompress(data[8:])
    if data[:3]!=b'FWS' or struct.unpack('<I',data[4:8])[0]!=len(data):
        raise ValueError('invalid compiled SWF length/header')
    return data


def verify_resource(content,swf,trailer):
    entries=bundle.toc(str(content/'blob0.bundle'))
    if len(entries)!=1 or entries[0][0]!=RESOURCE:raise ValueError('resource override count/path mismatch')
    red=bundle.extract(str(content/'blob0.bundle'),entries[0])
    actual,tail=split_redswf(red)
    if actual!=swf or tail!=trailer:raise ValueError('packed SWF/trailer differs from compiled input')
    files,_=metastore.read((content/'metadata.store').read_bytes())
    if len(files)!=1 or files[0]['path']!=RESOURCE or files[0]['size']!=len(red):raise ValueError('metadata resource mismatch')
    return red


def main():
    compiled=ROOT/'game/port-v8/combined'
    proof=json.loads((compiled/'manifest.json').read_text())
    if proof['status']!='core_compiled' or not all(proof.get(k) for k in ['decisionHookConnected','autoplayControllerConnected','recorderMerged','explicitChoiceHooksCompiled']):
        raise ValueError('combined build is incomplete')
    for path,digest in proof['inputs'].items():
        if sha(ROOT/path)!=digest:raise ValueError('stale compiled input: '+path)
    if sha(compiled/'gwint_game.swf')!=proof['compiledSha256']:raise ValueError('compiled SWF digest mismatch')
    stage=ROOT/'dist'/NAME
    if stage.exists():shutil.rmtree(stage)
    content=stage/'Mods/modBetterGwentAI/content';content.mkdir(parents=True)
    source=ROOT/'game/vanilla/swf/gwint_game.redswf'
    old=source.read_bytes();original,trailer=split_redswf(old)
    if original!=canonical_swf((ROOT/'game/vanilla/swf/gwint_game.swf').read_bytes()):raise ValueError('vanilla SWF source mismatch')
    swf=canonical_swf((compiled/'gwint_game.swf').read_bytes())
    red=patch_redswf(old,swf,trailer)
    blob,meta=build_bundle([(RESOURCE,red,True)])
    (content/'blob0.bundle').write_bytes(blob);(content/'metadata.store').write_bytes(meta)
    verify_resource(content,swf,trailer)
    scripts=content/'scripts/local';scripts.mkdir(parents=True)
    inputs={str(source.relative_to(ROOT)):sha(source),'tools/build_v8_package.py':sha(Path(__file__))}
    for path in ['mod/settings/modGwentAISettings/content/scripts/local/gwai_settings.ws',
        'mod/settings/modGwentAISettings/content/scripts/local/gwai_betting.ws',
        'mod/recorder/modGwentAIRecorder/content/scripts/local/gwai_recorder.ws']:
        shutil.copyfile(ROOT/path,scripts/Path(path).name);inputs[path]=sha(ROOT/path)
    labels=ROOT/'mod/settings/menu/labels.en.json'
    strings=build(json.loads(labels.read_text()))
    for language in LANGUAGES:(content/(language+'.w3strings')).write_bytes(strings)
    inputs[str(labels.relative_to(ROOT))]=sha(labels)
    menu=ROOT/'mod/settings/menu/modGwentAI.xml'
    target=stage/'bin/config/r4game/user_config_matrix/pc/modGwentAI.xml';target.parent.mkdir(parents=True)
    shutil.copyfile(menu,target);inputs[str(menu.relative_to(ROOT))]=sha(menu)
    readme=ROOT/'docs/V8_INSTALL_TEST.md';shutil.copyfile(readme,stage/'README.md');inputs[str(readme.relative_to(ROOT))]=sha(readme)
    manifest=dict(status='offline_verified_test_candidate',installed=False,runtimeGameVerified=False,
        witcherScriptEngineCompiled=False,patch='5.01',policy='response-v8',recorderMerged=True,
        decisionHookConnected=True,autoplayControllerConnected=True,resource=RESOURCE,
        compiledSha256=proof['compiledSha256'],compiledInputs=proof['inputs'],packageInputs=inputs,
        files={str(p.relative_to(stage)):sha(p) for p in sorted(stage.rglob('*')) if p.is_file()})
    (stage/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=stage.parent/(stage.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for path in sorted(stage.rglob('*')):
            if path.is_file():output.write(path,path.relative_to(stage))
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:raise ValueError('archive CRC failure')
        if set(check.namelist())!=set(manifest['files'])|{'BUILD_MANIFEST.json'}:raise ValueError('archive file set mismatch')
        for name,digest in manifest['files'].items():
            if hashlib.sha256(check.read(name)).hexdigest()!=digest:raise ValueError('archive content mismatch: '+name)
    report=dict(archive=str(archive),sha256=sha(archive),files=len(manifest['files'])+1,installed=False,
        runtimeGameVerified=False,resourceRoundTripVerified=True,compiledSha256=proof['compiledSha256'])
    (ROOT/'game/port-v8/combined/package-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
