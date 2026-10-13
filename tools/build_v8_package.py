#!/usr/bin/env python3
"""Package the mod, offline only.

  release   the mod alone (core SWF, no recorder): BetterGwent-<version>.zip
  recorder  the same mod plus the match recorder, for people who help with development:
            BetterGwent-<version>-recorder.zip (same folder name; it replaces the release)
"""
import argparse
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
from build_settings import build,language_labels,LANGUAGES,VERSION

ROOT=Path(__file__).resolve().parents[1]
RESOURCE='gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf'
DECK_RESOURCE='gameplay\\gui_new\\swf\\gwint\\deck_builder.redswf'
# Bundle resource -> stem of the vanilla file in game/vanilla/swf and of the compiled SWF.
RESOURCES={RESOURCE:'gwint_game',DECK_RESOURCE:'deck_builder'}
VARIANTS={'release':('core','INSTALL.md',''),'recorder':('combined','RECORDER.md','-recorder')}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_swf(data):
    if data[:3]==b'CWS':data=b'FWS'+data[3:8]+zlib.decompress(data[8:])
    if data[:3]!=b'FWS' or struct.unpack('<I',data[4:8])[0]!=len(data):
        raise ValueError('invalid compiled SWF length/header')
    return data


def verify_resources(content,expected):
    """expected: [(path, swf, trailer)] in bundle order."""
    entries=bundle.toc(str(content/'blob0.bundle'))
    if [e[0] for e in entries]!=[path for path,_,_ in expected]:raise ValueError('resource override count/path mismatch')
    files,_=metastore.read((content/'metadata.store').read_bytes())
    if [f['path'] for f in files]!=[path for path,_,_ in expected]:raise ValueError('metadata resource mismatch')
    for entry,meta,(path,swf,trailer) in zip(entries,files,expected):
        red=bundle.extract(str(content/'blob0.bundle'),entry)
        actual,tail=split_redswf(red)
        if actual!=swf or tail!=trailer:raise ValueError('packed SWF/trailer differs from compiled input: '+path)
        if meta['size']!=len(red):raise ValueError('metadata resource size mismatch: '+path)


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('variant',choices=sorted(VARIANTS))
    variant=parser.parse_args().variant
    build_dir,readme_name,suffix=VARIANTS[variant]
    name='BetterGwent-'+VERSION+suffix
    compiled=ROOT/'game/port-v8'/build_dir
    proof=json.loads((compiled/'manifest.json').read_text())
    if proof['status']!='core_compiled' or not all(proof.get(k) for k in ['decisionHookConnected','autoplayControllerConnected','explicitChoiceHooksCompiled']):
        raise ValueError('compiled build is incomplete')
    if bool(proof.get('recorderMerged'))!=(variant=='recorder'):
        raise ValueError('recorder presence does not match the variant')
    for path,digest in proof['inputs'].items():
        if sha(ROOT/path)!=digest:raise ValueError('stale compiled input: '+path)
    if sha(compiled/'gwint_game.swf')!=proof['compiledSha256']:raise ValueError('compiled SWF digest mismatch')
    if sha(compiled/'deck_builder.swf')!=proof.get('deckBuilderSha256'):raise ValueError('compiled deck builder digest mismatch')
    stage=ROOT/'dist'/name
    if stage.exists():shutil.rmtree(stage)
    content=stage/'Mods/modBetterGwent/content';content.mkdir(parents=True)
    inputs={'tools/build_v8_package.py':sha(Path(__file__))}
    packed,expected=[],[]
    for path,stem in RESOURCES.items():
        # Each resource keeps its own Scaleform trailer (symbol table) from the vanilla file.
        source=ROOT/'game/vanilla/swf'/(stem+'.redswf')
        old=source.read_bytes();original,trailer=split_redswf(old)
        if original!=canonical_swf((ROOT/'game/vanilla/swf'/(stem+'.swf')).read_bytes()):raise ValueError('vanilla SWF source mismatch: '+stem)
        swf=canonical_swf((compiled/(stem+'.swf')).read_bytes())
        packed.append((path,patch_redswf(old,swf,trailer),True));expected.append((path,swf,trailer))
        inputs[str(source.relative_to(ROOT))]=sha(source)
    blob,meta=build_bundle(packed)
    (content/'blob0.bundle').write_bytes(blob);(content/'metadata.store').write_bytes(meta)
    verify_resources(content,expected)
    scripts=content/'scripts/local';scripts.mkdir(parents=True)
    for path in ['mod/settings/modGwentAISettings/content/scripts/local/gwai_settings.ws',
        'mod/settings/modGwentAISettings/content/scripts/local/gwai_betting.ws',
        'mod/settings/modGwentAISettings/content/scripts/local/gwai_npc_decks.ws',
        'mod/settings/modGwentAISettings/content/scripts/local/gwai_npc_decks_data.ws',
        'mod/settings/modGwentAISettings/content/scripts/local/gwai_glossary.ws']+(
        ['mod/recorder/modGwentAIRecorder/content/scripts/local/gwai_recorder.ws'] if variant=='recorder' else []):
        shutil.copyfile(ROOT/path,scripts/Path(path).name);inputs[path]=sha(ROOT/path)
    for language in LANGUAGES:(content/(language+'.w3strings')).write_bytes(build(language_labels(language)))
    for labels in [ROOT/'mod/settings/menu/labels.en.json',ROOT/'mod/settings/menu/labels.translations.json',ROOT/'tools/build_settings.py']:
        inputs[str(labels.relative_to(ROOT))]=sha(labels)
    menu=ROOT/'mod/settings/menu/modGwentAI.xml'
    target=stage/'bin/config/r4game/user_config_matrix/pc/modGwentAI.xml';target.parent.mkdir(parents=True)
    shutil.copyfile(menu,target);inputs[str(menu.relative_to(ROOT))]=sha(menu)
    readme=ROOT/'docs'/readme_name;shutil.copyfile(readme,stage/'README.md');inputs[str(readme.relative_to(ROOT))]=sha(readme)
    manifest=dict(status='offline_verified_package',version=VERSION,variant=variant,installed=False,runtimeGameVerified=False,
        witcherScriptEngineCompiled=False,patch='5.01',policy='response-v8',recorderMerged=variant=='recorder',
        decisionHookConnected=True,autoplayControllerConnected=True,resource=RESOURCE,resources=list(RESOURCES),
        compiledSha256=proof['compiledSha256'],deckBuilderSha256=proof['deckBuilderSha256'],compiledInputs=proof['inputs'],packageInputs=inputs,
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
    (compiled/('package-report-%s.json' % variant)).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
