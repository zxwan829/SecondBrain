import asyncio, json, shutil, os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from aiohttp.test_utils import TestClient, TestServer
from tests.gateway.test_api_server_runs import _make_adapter, _create_runs_app
from types import SimpleNamespace as NS

def _mock_tool_call(name,arguments):
    return NS(id="synthetic-call",type="function",function=NS(name=name,arguments=arguments))
def _mock_response(content,finish_reason="stop",tool_calls=None):
    return NS(choices=[NS(message=NS(content=content,tool_calls=tool_calls),finish_reason=finish_reason)],model="synthetic",usage=None)
from run_agent import AIAgent

@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["deny", "once", "skills"])
async def test_real_agent_file_approval(tmp_path, monkeypatch, scenario):
    home=tmp_path/'home'; home.mkdir()
    monkeypatch.setenv('HERMES_HOME',str(home))
    monkeypatch.setenv('HERMES_EXEC_ASK','1')
    monkeypatch.setattr(Path,'home',classmethod(lambda cls: tmp_path/'synthetic-user'))
    shutil.copytree(os.environ['SB_D078_PLUGIN_SOURCE'], home/'plugins'/'secondbrain-d078-guard')
    (home/'config.yaml').write_text('plugins:\n  enabled: [secondbrain-d078-guard]\nskills:\n  write_approval: true\napprovals:\n  mode: manual\n  timeout: 15\nplatform_toolsets:\n  api_server: [file, skills, vision]\n')
    from hermes_cli import plugins
    plugins.discover_plugins(force=True)
    hooks=plugins.iter_hook_callbacks('pre_tool_call')
    assert len(hooks)==1, hooks
    import sys, traceback
    guard=sys.modules[hooks[0].__module__]
    hook_calls=[]
    original=guard.path_guard
    def traced(*a,**kw):
        try:
            result=original(*a,**kw)
            hook_calls.append((a,result))
            return result
        except Exception:
            traceback.print_exc()
            raise
    monkeypatch.setattr(guard,'path_guard',traced)
    target=(home/'skills'/'synthetic'/'SKILL.md') if scenario=='skills' else tmp_path/'unapproved.txt'
    monkeypatch.setenv('HERMES_WRITE_SAFE_ROOT',str(tmp_path))
    adapter=_make_adapter()
    a_holder=[]
    def factory(**kw):
        with patch('agent.process_bootstrap.OpenAI'):
            a=AIAgent(api_key='synthetic-only',base_url='http://127.0.0.1:1/v1',model='synthetic',enabled_toolsets=['file'],quiet_mode=True,skip_context_files=True,skip_memory=True,platform='api_server',session_id=kw.get('session_id'),max_iterations=2)
        a.client=MagicMock()
        responses=[_mock_response(content='',finish_reason='tool_calls',tool_calls=[_mock_tool_call(name='write_file',arguments=json.dumps({'path':str(target),'content':'synthetic'}))]),_mock_response(content='done')]
        a.client.chat.completions.create.side_effect=responses
        a._create_request_openai_client=lambda **k:a.client
        a.compression_enabled=False
        a_holder.append(a)
        return a
    with patch.object(adapter,'_create_agent',side_effect=factory):
        async with TestClient(TestServer(_create_runs_app(adapter))) as client:
            resp=await client.post('/v1/runs',json={'input':'synthetic probe'})
            assert resp.status==202
            run=(await resp.json())['run_id']
            events=[]
            async def read_events():
                async with client.get('/v1/runs/'+run+'/events') as response:
                    async for line in response.content:
                        if line.startswith(b'data: '):
                            events.append(json.loads(line[6:]))
            reader=asyncio.create_task(read_events())
            try:
                for _ in range(150):
                    if any(e.get('event')=='approval.request' for e in events): break
                    if any(e.get('event') in ('run.failed','run.completed') for e in events): break
                    await asyncio.sleep(.1)
                print('EVENTS',events)
                assert hook_calls, 'real dispatcher did not invoke Guard path policy'
                if scenario=='skills':
                    assert any(result and 'skills_write_gate' in result for _,result in hook_calls), hook_calls
                    assert not any(e.get('event')=='approval.request' for e in events), events
                    assert not target.exists()
                    assert any(e.get('event')=='run.completed' for e in events), events
                    return
                assert any(e.get('event')=='approval.request' for e in events), events
                assert not target.exists()
                event=next(e for e in events if e.get('event')=='approval.request')
                response=await client.post('/v1/runs/'+run+'/approval',json={'request_id':event['request_id'],'choice':scenario})
                assert response.status==200, await response.text()
                await asyncio.wait_for(reader,10)
                if scenario=='once':
                    assert target.read_text()=='synthetic'
                else:
                    assert not target.exists()
                assert any(e.get('event')=='run.completed' for e in events), events
            finally:
                reader.cancel()
