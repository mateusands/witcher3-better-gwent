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
from build_settings import LANGUAGES,build


@pytest.fixture(scope='module')
def shipping():
    archive=ROOT/'dist/BetterGwentAI-V8-5.01-test.zip'
    if not archive.exists():pytest.skip('Generate combined build and offline package first')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files={name:z.read(name) for name in z.namelist()}
    return files,json.loads(files['BUILD_MANIFEST.json'])


def test_archive_hashes_exact_contents_and_explicit_runtime_status(shipping):
    files,manifest=shipping
    assert set(files)==set(manifest['files'])|{'BUILD_MANIFEST.json'}
    for name,digest in manifest['files'].items():assert hashlib.sha256(files[name]).hexdigest()==digest
    assert manifest['status']=='offline_verified_test_candidate'
    assert manifest['installed'] is False and manifest['runtimeGameVerified'] is False
    assert manifest['witcherScriptEngineCompiled'] is False
    for path,digest in manifest['packageInputs'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
    assert not any(Path(name).suffix in ('.py','.as','.exe','.sh') for name in files)
    assert {name.split('/')[1] for name in files if name.startswith('Mods/')}=={'modBetterGwentAI'}


def test_one_combined_resource_round_trips_compiled_swf_and_native_trailer(shipping):
    files,manifest=shipping;prefix='Mods/modBetterGwentAI/content/'
    blob=files[prefix+'blob0.bundle'];meta=files[prefix+'metadata.store']
    assert blob[:8]==b'POTATO70' and struct.unpack_from('<I',blob,16)[0]==0x130
    entry=blob[32:32+0x130]
    path=entry[:0x100].split(b'\0')[0].decode()
    offset,_,size,zsize,crc,comp=struct.unpack_from('<6I',entry,0x110)
    assert path==manifest['resource'] and comp==1
    red=zlib.decompress(blob[offset:offset+zsize])
    assert len(red)==size and zlib.crc32(red)==crc
    swf,trailer=split_redswf(red)
    compiled=(ROOT/'game/port-v8/combined/gwint_game.swf').read_bytes()
    if compiled[:3]==b'CWS':compiled=b'FWS'+compiled[3:8]+zlib.decompress(compiled[8:])
    assert swf==compiled
    assert trailer==split_redswf((ROOT/'game/vanilla/swf/gwint_game.redswf').read_bytes())[1]
    metadata,_=metastore.read(meta)
    assert metadata==[dict(path=path,size=size,zsize=zsize,comp=comp,offset=offset)]


def test_settings_receiver_and_close_channels_are_shipped_together(shipping):
    files,_=shipping;prefix='Mods/modBetterGwentAI/content/scripts/local/'
    settings=files[prefix+'gwai_settings.ws'].decode()
    betting=files[prefix+'gwai_betting.ws'].decode()
    recorder=files[prefix+'gwai_recorder.ws'].decode()
    assert 'SetFlashObject("gwai.match.settings", packet)' in settings
    assert 'SetFlashBool("gwai.match.stop", true)' in betting
    for name in ('OnGwaiRec','OnGwaiEnd','OnGwaiStart'):assert 'event '+name+'(' in recorder
    assert 'function GetCurrentAIDeck()' in files[prefix+'gwai_npc_decks.ws'].decode()
    assert 'function GwaiNpcDeckTable(' in files[prefix+'gwai_npc_decks_data.ws'].decode()
    menu=ET.fromstring(files['bin/config/r4game/user_config_matrix/pc/modGwentAI.xml'])
    ids={node.attrib['id'] for node in menu.findall('.//VisibleVars/Var')}
    assert ids=={'GwaiEnabled','GwaiDifficulty','GwaiNpcDecks','GwaiAutoPlay','GwaiMaxBet','GwaiStakesStronger'}
    assert not any('filelist' in name for name in files)
    labels=build(json.loads((ROOT/'mod/settings/menu/labels.en.json').read_text()))
    for language in LANGUAGES:assert files['Mods/modBetterGwentAI/content/'+language+'.w3strings']==labels
