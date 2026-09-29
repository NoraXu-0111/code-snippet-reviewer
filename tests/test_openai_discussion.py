import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError

from backend.config import Settings
from backend.contracts import DiscussionTurn, Finding
from backend.discussion_provider import DiscussionFailure, OpenAIDiscussionProvider
from test_openai_reviewer import sample


def install_fake(monkeypatch, response=None, error=None):
    captured = {}
    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = self
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def create(self, **kwargs):
            captured["request"] = kwargs
            if error:
                raise error
            return response
    monkeypatch.setattr("backend.discussion_provider.AsyncOpenAI", Client)
    return captured


def finding():
    return Finding(id=uuid4(), review_run_id=uuid4(), start_line=2, end_line=2,
                   severity="info", category="style", description="Original finding", suggested_fix="Example")


def run(history=None):
    return asyncio.run(OpenAIDiscussionProvider(Settings(openai_api_key="synthetic-test-key")).reply(sample(), finding(), history or [], "Explain that?"))


def test_full_context_role_order_plaintext_and_request_controls(monkeypatch):
    captured = install_fake(monkeypatch, SimpleNamespace(status="completed", output=[], output_text="<script>plain text</script>\n  indented"))
    now = datetime.now(timezone.utc)
    prior = DiscussionTurn(conversation_id=uuid4(), id=uuid4(), finding_id=uuid4(), client_request_id=uuid4(), user_message="An example?",
                           assistant_message="The prior example", status="succeeded", attempt=1, created_at=now, started_at=now, finished_at=now)
    assert run([prior]) == "<script>plain text</script>\n  indented"
    request = captured["request"]
    assert request["store"] is False and request["max_output_tokens"] == 1500
    assert captured["client"]["max_retries"] == 0
    assert captured["client"]["base_url"] == "https://api.openai.com/v1"
    assert request["model"] == "gpt-4.1-mini"
    messages = request["input"]
    assert [m["role"] for m in messages] == ["system", "user", "user", "assistant", "user"]
    assert "untrusted data" in messages[0]["content"]
    context = json.loads(messages[1]["content"])
    assert context["language"] == "python" and context["lines"][1] == {"number": 2, "code": "print(1)"}
    assert context["finding"]["description"] == "Original finding"
    assert messages[2]["content"] == "An example?" and messages[3]["content"] == "The prior example"
    assert messages[4]["content"] == "Explain that?"
    assert "synthetic-test-key" not in str(request)


@pytest.mark.parametrize("response,message", [
    (SimpleNamespace(status="incomplete", output=[], output_text="partial"), "incomplete"),
    (SimpleNamespace(status="completed", output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal")])], output_text=""), "declined"),
    (SimpleNamespace(status="completed", output=[], output_text=" \n"), "empty"),
])
def test_refusal_incomplete_and_empty_reply_are_failures(monkeypatch, response, message):
    install_fake(monkeypatch, response)
    with pytest.raises(DiscussionFailure, match=message):
        run()


@pytest.mark.parametrize("kind,expected", [
    (AuthenticationError, "authentication"), (RateLimitError, "quota"),
    (APIStatusError, "rejected"), (APIConnectionError, "connect"), (APITimeoutError, "timed out"),
])
def test_provider_errors_are_sanitized(monkeypatch, kind, expected):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    if issubclass(kind, APIStatusError):
        error = kind("SECRET_PROVIDER_PAYLOAD", response=httpx.Response(400, request=request), body={"secret": "private"})
    elif kind is APITimeoutError:
        error = kind(request=request)
    else:
        error = kind(message="SECRET_PROVIDER_PAYLOAD", request=request)
    install_fake(monkeypatch, error=error)
    with pytest.raises(DiscussionFailure, match=expected) as result:
        run()
    assert "SECRET" not in str(result.value)
