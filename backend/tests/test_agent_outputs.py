"""Contracts and real SDK request serialization, entirely offline."""
import asyncio
import json
from datetime import date
from types import SimpleNamespace as NS

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.agents.output_contracts import (
    ResearchAnswer, SpecialistOutput, StrategyOutput, InteractionsOutput,
)
from app.config import Settings
from app.models import CaseProfile
from app.rag.scope import RetrievalScope


def settings():
    return Settings(_env_file=None, openai_api_key='test-only', database_url='')


@pytest.mark.parametrize('patch', [
    {'summary': ''}, {'summary': 'x' * 241}, {'roadblocks': ['x'] * 4},
    {'next_steps': ['x'] * 4}, {'required_documents': ['x'] * 5},
    {'missing_info': ['x' * 181]}, {'followups': [dict(id='i', prompt='q')] * 4},
    {'followups': [dict(id='i', prompt='q', options=['x'] * 13)]},
    {'match_level': 'definitely'}, {'unexpected': 'narrative'},
])
def test_eligibility_rejects_invalid_or_verbose_outputs(patch):
    with pytest.raises(ValidationError):
        SpecialistOutput.model_validate(dict(match_level='medium', summary='Confirm income.') | patch)


def test_aggregate_word_limits_cannot_be_bypassed_with_many_small_fields():
    with pytest.raises(ValidationError, match='220 words'):
        SpecialistOutput(match_level='medium', summary='x '*40,
                         roadblocks=['x '*45]*3, next_steps=['x '*45]*3)
    with pytest.raises(ValidationError, match='150 words'):
        ResearchAnswer(conclusion='x '*60, next_steps=['x '*50]*2)
    with pytest.raises(ValidationError):
        StrategyOutput(bullets=['x'] * 8)
    with pytest.raises(ValidationError):
        InteractionsOutput(interactions=[dict(note='n', action='', programs=['A','B'], source_titles=['S'])]*4)


def test_research_citations_must_match_document_and_page():
    answer = ResearchAnswer(conclusion='Use current coverage evidence.', findings=[{
        'finding':'The record supplies a coverage date.',
        'citations':[{'document_id':'doc-a','page':'2'}],
    }])
    answer.validate_evidence([dict(document_id='doc-a', source='fallback', page='2')])
    for evidence in [[], [dict(document_id='doc-a', source='fallback', page='3')]]:
        with pytest.raises(ValueError, match='supplied document and page'):
            answer.validate_evidence(evidence)


async def with_transport(output, operation):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        tool = next(t for t in body['tools'] if t['function']['name'].startswith('final_result'))
        return httpx.Response(200, json={
            'id':'test', 'object':'chat.completion', 'created':0, 'model':'gpt-5-mini',
            'choices':[{'index':0, 'finish_reason':'tool_calls', 'message':{
                'role':'assistant', 'content':None, 'tool_calls':[{
                    'id':'call-test', 'type':'function',
                    'function':{'name':tool['function']['name'], 'arguments':json.dumps(output)},
                }],
            }}], 'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},
        })
    async with AsyncOpenAI(api_key='test-only', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as client:
        result = await operation(client)
    return result, calls


def assert_strict_request(call, tokens):
    tool = next(t for t in call['tools'] if t['function']['name'].startswith('final_result'))
    assert tool['function']['strict'] is True
    schema = tool['function']['parameters']
    assert schema['additionalProperties'] is False
    assert set(schema['required']) == set(schema['properties'])
    assert call['max_completion_tokens'] == tokens
    assert call['reasoning_effort'] == 'low'


def test_research_uses_typed_bounded_output_and_validates_citations():
    from app.agents.research import _answer_question
    async def operation(client):
        return await _answer_question(client, settings(), 'tax', 'What next?',
                                      RetrievalScope('tax', 'CA', date(2026,11,15)),
                                      [dict(document_id='a', source='a', page='1')])
    output = dict(conclusion='Confirm the tax year.', findings=[dict(
        finding='The form is for the stated year.', citations=[dict(document_id='a', page='1')])],
        next_steps=[], limitations=[])
    result, calls = asyncio.run(with_transport(output, operation))
    assert isinstance(result, ResearchAnswer)
    assert_strict_request(calls[0], 3072)


def test_unsupported_research_citations_fail_after_bounded_retry():
    from app.agents.research import _answer_question
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    async def operation(client):
        with pytest.raises(UnexpectedModelBehavior):
            await _answer_question(client, settings(), 'tax', 'Question',
                                   RetrievalScope('tax','CA',date(2026,11,15)),
                                   [dict(document_id='a',source='a',page='1')])
    _, calls = asyncio.run(with_transport(dict(conclusion='Check.', findings=[dict(
        finding='Claim.', citations=[dict(document_id='invented',page='2')])],
        next_steps=[], limitations=[]), operation))
    assert len(calls) == 2


def test_specialist_activity_preserves_public_result_shape(monkeypatch):
    import openai
    from durable.activities import specialist as s
    monkeypatch.setattr(s, 'get_settings', settings)
    async def operation(client):
        monkeypatch.setattr(openai, 'AsyncOpenAI', lambda **kw: client)
        return await s.specialist_activity(dict(doc_key='ihss', profile_json=CaseProfile(id='synthetic').model_dump_json()))
    result, calls = asyncio.run(with_transport(
        SpecialistOutput(match_level='medium',summary='Confirm current Medi-Cal coverage.').model_dump(), operation))
    assert result['match_level'] == 'medium'
    assert json.loads(result['eligibility_result_json'])['rationale'] == 'Confirm current Medi-Cal coverage.'
    assert_strict_request(calls[0], 4096)


def test_synthesis_uses_contract_and_preserves_strategy_string(monkeypatch):
    import openai
    from durable.activities import synthesis as s
    monkeypatch.setattr(s,'get_settings',settings)
    monkeypatch.setattr(s,'get_profile',lambda _:None)
    monkeypatch.setattr(s,'save_profile',lambda _:None)
    async def operation(client):
        monkeypatch.setattr(openai,'AsyncOpenAI',lambda **kw:client)
        return await s.synthesis_activity(dict(case_id='synthetic',profile_json=CaseProfile(id='synthetic').model_dump_json(),specialist_results=[]))
    result,calls=asyncio.run(with_transport(dict(bullets=[]),operation))
    assert isinstance(result['strategy'],str)
    assert_strict_request(calls[0],4096)


def test_interactions_validate_strict_json_and_reject_overflow(monkeypatch):
    import openai
    from app.agents import interactions as i
    monkeypatch.setattr(i,'get_settings',settings)
    hit=NS(document_id='a',source='a',page='1',title='Official source',source_url='',program='medical',policy={},text='Policy.')
    monkeypatch.setattr(i,'_retrieve',lambda *args:[hit])
    item=dict(note='Check program coordination.',programs=['A','B'],action='Confirm coverage.',source_titles=['Official source'])
    calls=[]
    def create(**kw):
        calls.append(kw)
        return NS(choices=[NS(finish_reason='stop',message=NS(refusal=None,content=json.dumps(dict(interactions=[item]))))])
    monkeypatch.setattr(openai,'OpenAI',lambda **kw:NS(chat=NS(completions=NS(create=create))))
    result=i.analyze_program_interactions(CaseProfile(id='synthetic'),['A','B'])
    assert len(result)==1 and len(result[0].citations)==1
    assert calls[0]['response_format']['json_schema']['strict'] is True
    assert calls[0]['reasoning_effort']=='low'


def test_research_cli_defaults_to_compact_console(monkeypatch,capsys):
    from app.agents import research as r
    async def run(args):return dict(results=[dict(program='tax',answer=dict(conclusion='Check year.'),evidence=['long passages'])])
    monkeypatch.setattr(r,'run',run)
    monkeypatch.setattr('sys.argv',['research','Question','--program','tax'])
    r.main()
    assert 'evidence' not in json.loads(capsys.readouterr().out)['results'][0]


def test_strategy_cannot_hide_multiple_bullets_in_one_item():
    with pytest.raises(ValidationError, match='one line'):
        StrategyOutput(bullets=['First\nSecond'])


@pytest.mark.parametrize('flag,expect_evidence', [([],False),(['--include-evidence'],True),(['--retrieve-only'],True)])
def test_research_console_evidence_is_opt_in(monkeypatch,capsys,flag,expect_evidence):
    from app.agents import research as r
    async def run(args):return dict(results=[dict(program='tax',answer=None,evidence=['passage'])])
    monkeypatch.setattr(r,'run',run)
    monkeypatch.setattr('sys.argv',['research','Question','--program','tax',*flag])
    r.main()
    assert ('evidence' in json.loads(capsys.readouterr().out)['results'][0]) is expect_evidence


def test_research_archive_keeps_evidence(monkeypatch,tmp_path):
    from app.agents import research as r
    async def run(args):return dict(results=[dict(program='tax',answer=None,evidence=['passage'])])
    monkeypatch.setattr(r,'run',run)
    path=tmp_path/'audit.json'
    monkeypatch.setattr('sys.argv',['research','Question','--program','tax','--output',str(path)])
    r.main()
    assert json.loads(path.read_text())['results'][0]['evidence']==['passage']


def test_research_waits_for_siblings_before_closing_shared_resources(monkeypatch):
    from dataclasses import dataclass
    import openai
    from app.agents import research as r
    from app.rag import index as idx
    from app import config
    state={'client_closed':False,'pool_closed':False,'finished':False}
    @dataclass
    class Hit:
        document_id:str='doc'
        source:str='doc'
        page:str='1'
        text:str='Public policy passage.'
    class Index:
        def __init__(self,*args):self._pool=NS(close=lambda:state.update(pool_closed=True))
        def ensure(self):return 1
        def search(self,*args,**kw):return [Hit()]
    class Client:
        async def close(self):state['client_closed']=True
    async def answer(client,settings,program,*args):
        if program=='ihss':raise ValueError('invalid output')
        await asyncio.sleep(0.01)
        assert not state['client_closed'] and not state['pool_closed']
        state['finished']=True
        return ResearchAnswer(conclusion='Resolve the missing fact.')
    monkeypatch.setattr(idx,'PgVectorIndex',Index)
    monkeypatch.setattr(config,'get_settings',lambda:NS(database_url='test',openai_api_key='test',openai_base_url='',openai_model='gpt-5-mini'))
    monkeypatch.setattr(openai,'AsyncOpenAI',lambda **kw:Client())
    monkeypatch.setattr(r,'_answer_question',answer)
    args=NS(program=['ihss','tax'],query=None,question='Question',retrieve_only=False,state='CA',as_of=date(2026,11,15),k=1)
    with pytest.raises(ValueError,match='invalid output'):
        asyncio.run(r.run(args))
    assert state=={'client_closed':True,'pool_closed':True,'finished':True}
