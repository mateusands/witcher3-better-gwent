"""Validate generated candidate shipping contents; no installation or engine claim."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib
import xml.etree.ElementTree as ET

import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import metastore
from redswf import split_redswf
from build_settings import LANGUAGES,VERSION,build,language_labels


@pytest.fixture(scope='module',params=['release','recorder'])
def shipping(request):
    archive=ROOT/('dist/BetterGwent-%s%s.zip' % (VERSION,'-recorder' if request.param=='recorder' else ''))
    if not archive.exists():pytest.skip('Build the SWF and run tools/build_v8_package.py %s first' % request.param)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files={name:z.read(name) for name in z.namelist()}
    manifest=json.loads(files['BUILD_MANIFEST.json'])
    assert manifest['variant']==request.param
    return files,manifest


def test_archive_hashes_exact_contents_and_explicit_runtime_status(shipping):
    files,manifest=shipping
    assert set(files)==set(manifest['files'])|{'BUILD_MANIFEST.json'}
    for name,digest in manifest['files'].items():assert hashlib.sha256(files[name]).hexdigest()==digest
    assert manifest['status']=='offline_verified_package' and manifest['version']==VERSION
    assert manifest['installed'] is False and manifest['runtimeGameVerified'] is False
    assert manifest['witcherScriptEngineCompiled'] is False
    for path,digest in manifest['packageInputs'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
    assert not any(Path(name).suffix in ('.py','.as','.exe','.sh') for name in files)
    assert {name.split('/')[1] for name in files if name.startswith('Mods/')}=={'modBetterGwent'}


def test_both_interface_resources_round_trip_compiled_swf_and_native_trailer(shipping):
    files,manifest=shipping;prefix='Mods/modBetterGwent/content/'
    blob=files[prefix+'blob0.bundle'];meta=files[prefix+'metadata.store']
    stems={'gameplay\\gui_new\\swf\\gwint\\gwint_game.redswf':'gwint_game',
           'gameplay\\gui_new\\swf\\gwint\\deck_builder.redswf':'deck_builder'}
    assert manifest['resources']==list(stems) and manifest['resource']==list(stems)[0]
    assert blob[:8]==b'POTATO70' and struct.unpack_from('<I',blob,16)[0]==0x130*len(stems)
    build=ROOT/'game/port-v8'/('combined' if manifest['variant']=='recorder' else 'core')
    expected=[]
    for i,(resource,stem) in enumerate(stems.items()):
        entry=blob[32+i*0x130:32+(i+1)*0x130]
        path=entry[:0x100].split(b'\0')[0].decode()
        offset,_,size,zsize,crc,comp=struct.unpack_from('<6I',entry,0x110)
        assert path==resource and comp==1
        red=zlib.decompress(blob[offset:offset+zsize])
        assert len(red)==size and zlib.crc32(red)==crc
        swf,trailer=split_redswf(red)
        compiled=(build/(stem+'.swf')).read_bytes()
        if compiled[:3]==b'CWS':compiled=b'FWS'+compiled[3:8]+zlib.decompress(compiled[8:])
        assert swf==compiled
        # Each file keeps its own Scaleform symbol table.
        assert trailer==split_redswf((ROOT/'game/vanilla/swf'/(stem+'.redswf')).read_bytes())[1]
        expected.append(dict(path=path,size=size,zsize=zsize,comp=comp,offset=offset))
    assert hashlib.sha256((build/'deck_builder.swf').read_bytes()).hexdigest()==manifest['deckBuilderSha256']
    metadata,_=metastore.read(meta)
    assert metadata==expected


def test_settings_receiver_and_close_channels_are_shipped_together(shipping):
    files,manifest=shipping;prefix='Mods/modBetterGwent/content/scripts/local/'
    settings=files[prefix+'gwai_settings.ws'].decode()
    betting=files[prefix+'gwai_betting.ws'].decode()
    assert 'SetFlashObject("gwai.match.settings", packet)' in settings
    assert 'SetFlashBool("gwai.match.stop", true)' in betting
    if manifest['variant']=='recorder':
        recorder=files[prefix+'gwai_recorder.ws'].decode()
        for name in ('OnGwaiRec','OnGwaiEnd','OnGwaiStart'):assert 'event '+name+'(' in recorder
    else:
        assert prefix+'gwai_recorder.ws' not in files
    assert 'function GetCurrentAIDeck()' in files[prefix+'gwai_npc_decks.ws'].decode()
    assert 'function GwaiNpcDeckTable(' in files[prefix+'gwai_npc_decks_data.ws'].decode()
    menu=ET.fromstring(files['bin/config/r4game/user_config_matrix/pc/modGwentAI.xml'])
    ids={node.attrib['id'] for node in menu.findall('.//VisibleVars/Var')}
    assert ids=={'GwaiEnabled','GwaiDifficulty','GwaiNpcDecks','GwaiAutoPlay','GwaiMaxBet','GwaiStakesStronger'}
    assert not any('filelist' in name for name in files)
    for language in LANGUAGES:
        assert files['Mods/modBetterGwent/content/'+language+'.w3strings']==build(language_labels(language))
    assert files['Mods/modBetterGwent/content/br.w3strings']!=files['Mods/modBetterGwent/content/en.w3strings']
