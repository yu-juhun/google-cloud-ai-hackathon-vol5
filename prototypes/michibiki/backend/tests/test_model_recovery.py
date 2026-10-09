from types import SimpleNamespace

import pytest
from google.genai.errors import ServerError

from michibiki import agents
from michibiki.contracts import Plan


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [ServerError(504, {"error": {"message": "Deadline expired"}}), TimeoutError()])
async def test_planner_recovers_with_different_model(monkeypatch, failure):
    calls = []

    async def call(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise failure
        return SimpleNamespace(
            candidates=[], usage_metadata=None,
            text='{"assignments":[{"role":"聖地調査","goal":"候補を調べる","search_query":"乃木坂46 聖地"}]}',
        )

    async def noop(*args):
        pass

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=call), aclose=noop),
        close=lambda: None,
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setattr(agents.genai, "Client", lambda **kwargs: client)
    monkeypatch.setattr(agents.asyncio, "sleep", noop)
    result = await agents.generate("gemini-3.8-flash", "plan", {}, Plan)
    assert calls == ["gemini-3.8-flash", "gemini-2.5-flash"]
    assert len(result["assignments"]) == 1
