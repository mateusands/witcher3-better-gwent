"""Lab autopilot (lab/autopilot.py): the Google Cloud server improves the NPC on its own.

Spec (owner, 13 October 2026): the owner no longer tests the AI move by move in the game. The
Lab server must keep looking for improvements by itself, test them, and report what is proven,
so we turn only proven results into changes in the mod.
- Ideas: a list of idea families (Lab switches and modes). The autopilot keeps up to `explore`
  idea jobs active at a time, each a paired SPRT A/B job ('ab') against the fair scene, named
  "AUTO idea <switches> <decks>", with its own seed; an idea is never queued twice (the job
  names in the Lab are the memory).
- Confirmation: about 1 in 20 SPRT passes is luck, so every passed idea job (and every passed
  'ab' job queued by hand) gets two confirmation jobs on new seeds, named
  "AUTO confirm <id> <k>", queued once.
- Promotion: an idea is promoted when both of its confirmations pass; rejected when either
  fails. Confirmations are never confirmed again.
- Report: promoted, rejected, waiting and tested ideas are written to a JSON report.
- Results from elsewhere (Runpod, 13 October 2026): ideas already decided there are not queued
  again, and the ones that passed there get their two confirmations on the cloud server, named
  "AUTO confirm <tag> <k>" with the tag of the outside result. Ideas already confirmed (or
  rejected) elsewhere are reported as such and get no confirmation here.
- Runpod, 13 October 2026: spy-first and fusion20 on Original passed three times (promoted);
  fusion15 and spy-first+fusion25 on Original failed their confirmations (rejected); r1cap20 on
  Original is still open, so the cloud server tests it first.

Given the Lab's jobs, when the autopilot steps, then it queues the confirmations of new passes
once, fills the free idea slots with untested ideas, and reports promoted and rejected ideas.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'lab'))
sys.path.insert(0, str(ROOT / 'sim'))

import autopilot  # noqa: E402

SCENE = 'response-v8:player-mulligan+base-mulligan'


def ab(jid, name, policy=SCENE + '+fusion25', decks='strong', status='done', result=None):
    params = dict(policy=policy, npc_decks=decks, base_policy=SCENE, base_decks=decks)
    if result:
        params['verdict'] = dict(result=result, n=1000, mean=0.02, z=2.5)
    return dict(id=jid, name=name, kind='ab', status=status, params=params)


def test_a_pass_gets_two_confirmations_once():
    jobs = [ab(7, 'SPRT fusion25 strong', result='better'), ab(8, 'SPRT beam4 strong', result='not better')]
    new = [j for j in autopilot.confirmations(jobs) if not j['name'].startswith('AUTO confirm runpod')]
    assert [j['name'] for j in new] == ['AUTO confirm 7 1', 'AUTO confirm 7 2']
    assert all(j['kind'] == 'ab' and j['policy'] == SCENE + '+fusion25' and j['npc_decks'] == 'strong' for j in new)
    assert len({j['seeds'][0] for j in new}) == 2
    queued = jobs + [dict(ab(9, 'AUTO confirm 7 1', status='active')), dict(ab(10, 'AUTO confirm 7 2', status='active'))]
    assert [j for j in autopilot.confirmations(queued) if not j['name'].startswith('AUTO confirm runpod')] == []


def test_confirmations_are_never_confirmed_again():
    jobs = [ab(9, 'AUTO confirm 7 1', result='better')]
    assert all(j['name'].startswith('AUTO confirm runpod') for j in autopilot.confirmations(jobs))


def test_promotion_needs_both_confirmations():
    base = ab(7, 'SPRT fusion25 strong', result='better')
    both = [base, ab(9, 'AUTO confirm 7 1', result='better'), ab(10, 'AUTO confirm 7 2', result='better')]
    one_fails = [base, ab(9, 'AUTO confirm 7 1', result='better'), ab(10, 'AUTO confirm 7 2', result='not better')]
    waiting = [base, ab(9, 'AUTO confirm 7 1', result='better'), ab(10, 'AUTO confirm 7 2', status='active')]
    ours = lambda entries: [p['id'] for p in entries if isinstance(p['id'], int)]
    assert ours(autopilot.report(both)['promoted']) == [7]
    assert ours(autopilot.report(one_fails)['rejected']) == [7]
    assert ours(autopilot.report(waiting)['waiting']) == [7]


def test_free_slots_get_untested_ideas():
    families = [('fusion10', 'strong'), ('fusion10', 'balanced'), ('fusion20', 'strong')]
    jobs = [ab(1, 'AUTO idea fusion10 strong', status='done', result='not better'),
            ab(2, 'AUTO idea fusion10 balanced', status='active')]
    new = autopilot.next_ideas(jobs, families, explore=2)
    assert [j['name'] for j in new] == ['AUTO idea fusion20 strong']
    assert new[0]['policy'] == SCENE + '+fusion20' and new[0]['base_policy'] == SCENE
    assert autopilot.next_ideas(jobs + [ab(3, 'AUTO idea fusion20 strong', status='active')], families, explore=2) == []


def test_idea_seeds_are_stable_and_distinct():
    a = autopilot.idea_job('fusion10', 'strong')['seeds'][0]
    assert a == autopilot.idea_job('fusion10', 'strong')['seeds'][0]
    assert a != autopilot.idea_job('fusion10', 'balanced')['seeds'][0]


def test_the_shipped_idea_list_is_valid():
    from gwentsim import response_search, response_v8 as v8
    from gwentsim.options import Difficulty
    assert len(autopilot.IDEAS) >= 20 and len(set(autopilot.IDEAS)) == len(autopilot.IDEAS)
    for switches, decks in autopilot.IDEAS:
        assert decks in ('balanced', 'strong', 'original')
        for s in switches.split('+'):
            known = s in v8.NPC_SWITCHES or s in v8.WEIGHT_SWITCHES or v8.r1_cap_lead(frozenset({s}), 1, 1)
            if not known:
                v8.VARIANT, v8.NPC_SEAT = frozenset({s}), 1
                known = response_search.search_settings(Difficulty.HARD, 1) != response_search.SearchSettings(4, 2048, 8, 0.0, 0.0)
            assert known, s


def test_outside_results_are_skipped_and_their_passes_confirmed():
    assert all(autopilot.idea_job(s, d)['name'] not in [j['name'] for j in autopilot.next_ideas([], explore=99)]
               for s, d in autopilot.DECIDED_ELSEWHERE)
    new = autopilot.confirmations([])
    tags = sorted({j['name'].rsplit(' ', 1)[0] for j in new})
    assert tags == sorted('AUTO confirm %s' % autopilot.outside_tag(s, d) for s, d in autopilot.PASSED_ELSEWHERE)
    assert len(new) == 2 * len(autopilot.PASSED_ELSEWHERE) and len({j['seeds'][0] for j in new}) == len(new)
    done = [dict(id=50 + i, name=j['name'], kind='ab', status='done', params=dict(j, verdict=dict(result='better')))
            for i, j in enumerate(new)]
    assert autopilot.confirmations(done) == []
    assert len([e for e in autopilot.report(done)['promoted'] if e['name'].startswith('AUTO')]) <= len(autopilot.PASSED_ELSEWHERE)


def test_runpod_verdicts_are_reported_and_not_tested_again():
    rep = autopilot.report([])
    promoted = {e['name'] for e in rep['promoted']}
    assert {'Runpod spy-first original', 'Runpod fusion20 original'} <= promoted
    assert {'Runpod fusion15 original', 'Runpod spy-first+fusion25 original'} <= {e['name'] for e in rep['rejected']}
    assert autopilot.confirmations([]) == []                       # nothing left to confirm from Runpod
    assert autopilot.next_ideas([], explore=1)[0]['name'] == 'AUTO idea r1cap20 original'
