"""Regression checks for in-game WS parser failures, not engine compilation."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'mod/settings/modGwentAISettings/content/scripts/local'


def body(source, name):
    start = source.index('{', source.index(' ' + name + '('))
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start + 1:end - 1]


def test_installed_parser_errors_cannot_recur_in_shipping_sources():
    sources = [p.read_text() for p in LOCAL.glob('*.ws')]
    sources += [(ROOT / 'mod/recorder/modGwentAIRecorder/content/scripts/local/gwai_recorder.ws').read_text()]
    for source in sources:
        assert not re.search(r'@wrapMethod\s*\(\s*\)', source)
        # Native events and access modifiers are not repeated on wrapper syntax.
        wrappers = re.findall(r'@wrapMethod\([^)]*\)\s*(\w+)', source)
        assert wrappers and all(token == 'function' for token in wrappers) if wrappers else True
        assert not re.search(r'\bvar\s+reward\s*:', source)
    settings = (LOCAL / 'gwai_settings.ws').read_text()
    assert 'function IngameMenu_FillSubMenuOptionsList(' not in settings
    assert 'function SetOptionSkipsAndLocks(' not in settings


def test_each_wrapper_calls_wrapped_method_at_most_once():
    # In-game 5.01 compiler: a second call in one wrapper fails with
    # "Could not find function 'wrappedMethod'".
    paths = list(LOCAL.glob('*.ws')) + [ROOT / 'mod/recorder/modGwentAIRecorder/content/scripts/local/gwai_recorder.ws']
    for path in paths:
        source = path.read_text()
        for match in re.finditer(r'@wrapMethod\(\w+\)\s*function\s+(\w+)', source):
            start = source.index('{', match.end())
            depth, end = 1, start + 1
            while depth:
                depth += (source[end] == '{') - (source[end] == '}')
                end += 1
            assert source[start:end].count('wrappedMethod(') <= 1, (path.name, match.group(1))


def test_menu_wrappers_match_native_signatures_and_preserve_call_order():
    source = (LOCAL / 'gwai_settings.ws').read_text()
    native = (ROOT / 'game/vanilla/scripts/game/gui/main_menu/ingameMenu.ws').read_text()
    for name in ('OnConfigUI', 'OnShowOptionSubmenu'):
        signature = re.search(r'function\s+' + name + r'\([^)]*\)(?:\s*:\s*void)?', source).group()
        original = re.search(r'event\s+' + name + r'\([^)]*\)(?:\s*:\s*void)?', native).group()
        assert re.sub(r'\s+', '', signature.replace('function', 'event', 1)) == re.sub(r'\s+', '', original)
        assert re.search(r'@wrapMethod\(CR4IngameMenu\)\s*' + re.escape(signature), source)
    script = '''
    let calls=[];
    function GwaiSettingsInitialize(){calls.push('initialize');}
    function GwaiSettingsRefreshControlLocks(){calls.push('locks');}
    function wrappedMethod(...args){calls.push(['native',...args]);}
    function configure(){%s}
    function show(actionType,menuTag,id){%s}
    configure();show(100,7,'GwentAI');
    if(JSON.stringify(calls)!==JSON.stringify(['initialize',['native'],['native',100,7,'GwentAI'],'locks']))
        throw new Error(JSON.stringify(calls));
    ''' % (body(source, 'OnConfigUI'), body(source, 'OnShowOptionSubmenu'))
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)


def test_standard_reward_filter_still_rejects_mixed_and_special_rewards():
    source = (LOCAL / 'gwai_betting.ws').read_text()
    predicate = body(source, 'GwaiIsStandardGoldBet').replace('var gwaiGoldReward : SReward;', 'var gwaiGoldReward = {};')
    script = '''
    let isGwentMode=true, current;
    const theGame={GetReward:(name,out)=>Object.assign(out,current)};
    function check(rewardName){%s}
    function reward(extra={}){return {gold:10,experience:0,items:{Size:()=>0},achievement:0,level:0,...extra};}
    current=reward();if(!check('generic_gwint_reward'))throw new Error('standard rejected');
    if(check('special_reward'))throw new Error('special accepted');
    for(const extra of [{gold:25},{experience:1},{items:{Size:()=>1}},{achievement:1},{level:1}]){
        current=reward(extra);if(check('generic_gwint_reward'))throw new Error('mixed accepted');
    }
    current=reward();isGwentMode=false;if(check('generic_gwint_reward'))throw new Error('non-Gwent accepted');
    ''' % predicate
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
