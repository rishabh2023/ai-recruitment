"""Anthropic (Claude Haiku) JD extraction: JSON mapping + robust fallback. No network."""

from __future__ import annotations

import types

import anthropic
import pytest

from app.integrations.llm.anthropic_provider import AnthropicLLMProvider, _to_extracted_job


def _text_response(text: str):
    block = types.SimpleNamespace(type="text", text=text)
    return types.SimpleNamespace(content=[block])


def _provider() -> AnthropicLLMProvider:
    # Constructed with a dummy key; we never actually call the network (create is patched).
    return AnthropicLLMProvider(api_key="sk-ant-dummy", model="claude-haiku-4-5")


def test_to_extracted_job_maps_and_clamps_role_family():
    job = _to_extracted_job(
        {
            "title": "Backend Engineer",
            "role_family": "wizardry",  # invalid → clamped to general
            "experience_min_years": "3",
            "skills": ["python", "fastapi", 5],
            "must_haves": "not a list",
        }
    )
    assert job.title == "Backend Engineer"
    assert job.role_family == "general"
    assert job.experience_min_years == 3
    assert job.skills == ["python", "fastapi", "5"]
    assert job.must_haves == []


def test_extract_job_parses_model_json(monkeypatch):
    p = _provider()
    monkeypatch.setattr(
        p._client.messages,
        "create",
        lambda **kw: _text_response('{"title":"Sales Rep","role_family":"sales","skills":["crm"]}'),
    )
    job = p.extract_job("Sales Rep JD text")
    assert job.title == "Sales Rep" and job.role_family == "sales" and job.skills == ["crm"]


def test_extract_job_strips_code_fences(monkeypatch):
    p = _provider()
    fenced = '```json\n{"title":"X","role_family":"engineering"}\n```'
    monkeypatch.setattr(p._client.messages, "create", lambda **kw: _text_response(fenced))
    assert p.extract_job("some JD").role_family == "engineering"


def test_extract_job_falls_back_to_stub_on_api_error(monkeypatch):
    p = _provider()

    def boom(**kw):
        raise anthropic.APIError("down", request=None, body=None)

    monkeypatch.setattr(p._client.messages, "create", boom)
    # Stub fallback classifies an engineering JD deterministically → never raises.
    job = p.extract_job("Senior Backend Engineer, Python")
    assert job.role_family == "engineering"


def test_extract_job_falls_back_on_bad_json(monkeypatch):
    p = _provider()
    monkeypatch.setattr(p._client.messages, "create", lambda **kw: _text_response("not json at all"))
    job = p.extract_job("Account Executive with quota")
    assert job.role_family == "sales"  # stub fallback
