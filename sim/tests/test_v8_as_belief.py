"""Exact isolated seed/RNG/public-hypothesis parity with the Python V8 reference."""
from dataclasses import asdict, replace
import hashlib
import json
import random
import subprocess

import pytest
from test_horn_evaluation import board, card
from test_position import capture
from test_v8_as_position import payload
from gwentsim.sequence_search import Context
from gwentsim.opponent_belief import public_seed, hypotheses, opponent_view
from v8_as_test import core_javascript, script_file


def run(inputs, expression):
    script=core_javascript()+'\nvar inputs=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    script+='\nconsole.log(JSON.stringify(inputs.map(data => '+expression+')));'
    process=subprocess.run(['node',script_file(script)],input=json.dumps(inputs),capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    return json.loads(process.stdout)


def limbs(seed):
    out=[]
    while seed:
        out.append(seed & 0xffffffff);seed>>=32
    return out or [0]


def test_integer_seeding_twists_and_53bit_draws_are_exact():
    seeds=[0,1,234,2**32-1,2**32,2**63+234,2**64-1,2**64+3]
    actual=run([limbs(s) for s in seeds],'(() => {var rng=new GwaiV8Random(data); return Array.from({length:1500},()=>rng.random());})()')
    for seed,draws in zip(seeds,actual):
        rng=random.Random(seed)
        assert draws==[rng.random() for _ in range(1500)]
    actual=run([limbs(s) for s in seeds],'(() => {var rng=new GwaiV8Random(data); return Array.from({length:1500},()=>rng.nextWord());})()')
    for seed,words in zip(seeds,actual):
        rng=random.Random(seed)
        assert words==[rng.getrandbits(32) for _ in range(1500)]


def test_sha256_padding_boundaries_and_full_digest():
    texts=['','abc','a'*55,'a'*56,'a'*63,'a'*64,'a'*65,'abc'*1000]
    actual=run(texts,'GwaiV8Hash.digest(data)')
    for text,words in zip(texts,actual):
        digest=hashlib.sha256(text.encode()).digest()
        assert words==[int.from_bytes(digest[i:i+4],'big') for i in range(0,32,4)]


def test_seed_increment_has_no_53bit_integer_rounding():
    cases=[[[0xffffffff,0xffffffff],6],[[0xffffffff,0],1],[[234,0x80000000],5]]
    actual=run(cases,'GwaiV8Belief.increment(data[0],data[1])')
    for case,words in zip(cases,actual):
        assert sum(w << (32*i) for i,w in enumerate(words))==sum(w << (32*i) for i,w in enumerate(case[0]))+case[1]


@pytest.mark.parametrize('known',[False,True])
@pytest.mark.parametrize('faction',range(1,6))
@pytest.mark.parametrize('hand_count',[0,1,5,99])
def test_public_seed_sampling_and_opponent_view_match(board,faction,hand_count,known):
    for n in range(12):
        flags=[9,10,12,137,16,32,71][n%7]
        effects=(23,) if flags==16 else (27,) if flags==71 else (42,) if n%5==0 else ()
        unit=card(board,3+n,1,flags,effects)
        unit.templateRef.factionIdx=n%6
    # Revealed opposing hero consumes its only public-catalog copy.
    revealed=card(board,15,5,137,player=1)
    revealed.templateRef.factionIdx=faction
    state=capture(board);state.counts={2:2,5:1}
    context=Context(1,0,1,False,hand_count,3,faction,True,False)
    if known:
        # Cards seen going back to the opponent's hand (Decoy): fixed in every hypothesis.
        eligible=[t for t,c in sorted(state.catalog.items()) if c.faction in (0,faction) and t!=revealed.templateId]
        context=replace(context,opponent_known=tuple(eligible[:2])+(eligible[0],))
    sample=dict(state=payload(state),context=asdict(context))
    expression='(() => {var state=Object.assign(new GwaiV8Position(),data.state); var before=JSON.stringify(state); var hs=GwaiV8Belief.hypotheses(state,data.context,6); var out={seed:GwaiV8Belief.publicSeed(state,data.context),hypotheses:hs,views:hs.map(h=>GwaiV8Belief.opponentView(state,h))}; if(before!==JSON.stringify(state))throw new Error("input mutated");return out;})()'
    actual=run([sample],expression)[0]
    seed=public_seed(state,context)
    assert actual['seed']==[seed & 0xffffffff,seed >> 32]
    expected=hypotheses(state,context,6)
    assert actual['hypotheses']==json.loads(json.dumps([asdict(h) for h in expected]))
    assert actual['views']==json.loads(json.dumps([payload(opponent_view(state,h)) for h in expected]))
    for h in expected:
        assert all(c.template!=revealed.templateId for c in h.hand)
        fixed=context.opponent_known[:hand_count]
        assert [c.template for c in h.hand[:len(fixed)]]==list(fixed)
