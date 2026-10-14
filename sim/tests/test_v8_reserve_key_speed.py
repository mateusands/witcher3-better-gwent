"""Reserve-cache key built directly (AS3 speed, no decision change).

Spec (14 October 2026, frame rate while the NPC thinks): profiling the AS3 search on 203 real NPC
decisions showed about 28% of the time in GwaiV8Position.reserveKey, which built nested arrays and
serialized them with the generic GwaiV8Hash.text. The key must stay the same text, character for
character, so every cache hit and every decision is unchanged; it is built directly instead, and
the generic serializer is used only for the rare recovery part.

Given positions with cards in hand, in the deck, on the board and in the graveyards, when the
reserve key is built, then it equals the old nested-array text, and building it calls the generic
serializer at most once (for the recovery part).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_horn_evaluation import board, card, unit, horn  # noqa: F401
from test_position import capture
from test_v8_as_position import payload

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from v8_as_test import core_javascript, script_file  # noqa: E402

OLD_KEY = '''
function oldKey(s){
  var held=[],remaining=[],recovery=[];
  for(var i=0;i<s.hand.length;++i)held.push([s.hand[i],s.cards[s.hand[i]].template]);
  held.sort((a,b)=>a[0]-b[0]);
  for(var key in s.counts)remaining.push([key|0,s.counts[key]]);
  remaining.sort((a,b)=>a[0]-b[0]);
  if(s.recoveryRelevant()){var rows=[];for(var side=0;side<2;++side)for(var r=0;r<GwaiV8Position.ROWS.length;++r)rows.push(s.board[GwaiV8Position.slot(side,GwaiV8Position.ROWS[r])]);recovery=[s.grave[0],s.grave[1],rows];}
  return GwaiV8Hash.text([s.player,held,remaining,s.unknown_draws,s.draw_value,s.leaderModeled(s.player),recovery]);
}
'''


def keys(state):
    script = core_javascript() + OLD_KEY + '''
var data=JSON.parse(require("fs").readFileSync(0,"utf8"));
var state=Object.assign(new GwaiV8Position(),data);
var calls=0,text=GwaiV8Hash.text;GwaiV8Hash.text=function(v){calls++;return text(v);};
var key=state.reserveKey(),used=calls;GwaiV8Hash.text=text;
var out=[[key,oldKey(state),used]];
var actions=state.cardActions();
for(var a of actions.slice(0,6)){var next=state.applyCard(a);calls=0;GwaiV8Hash.text=function(v){calls++;return text(v);};
  var k=next.reserveKey(),u=calls;GwaiV8Hash.text=text;out.push([k,oldKey(next),u]);}
console.log(JSON.stringify(out));
'''
    done = subprocess.run(['node', script_file(script)], input=json.dumps(payload(state)), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.parametrize('scenario', range(4))
def test_reserve_key_text_is_unchanged_and_built_directly(board, scenario):  # noqa: F811
    for n in range(3 + scenario):
        card(board, 2 + n, 1 + n % 3, 9)
    card(board, 6, 1, 9, player=1); unit(board, 5, 5)
    if scenario >= 1:
        horn(board)
    if scenario >= 2:
        card(board, 4, 1, 32, (26,))           # a medic: the graveyards matter (recovery part)
    if scenario == 3:
        unit(board, 8, 4, hero=True)
    for key, old, calls in keys(capture(board)):
        assert key == old
        assert calls <= 1
