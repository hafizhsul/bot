# tests/test_llm_client.py
import json
import requests
from unittest import mock

import llm_client


def _fake_resp(status, content):
    fake = mock.Mock()
    fake.status_code = status
    fake.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return fake


def test_suggest_queries_valid_array():
    resp = _fake_resp(200, '["pdf tools", "document automation"]')
    with mock.patch("llm_client.requests.post", return_value=resp):
        queries = llm_client.suggest_queries("professional PDF tools")
    assert queries == ["pdf tools", "document automation"]


def test_suggest_queries_fenced_json():
    resp = _fake_resp(200, '```json\n["ai agent skills", "llm orchestration"]\n```')
    with mock.patch("llm_client.requests.post", return_value=resp):
        queries = llm_client.suggest_queries("skills agent")
    assert queries == ["ai agent skills", "llm orchestration"]


def test_suggest_queries_non_200():
    resp = _fake_resp(500, "error")
    with mock.patch("llm_client.requests.post", return_value=resp):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_invalid_json():
    resp = _fake_resp(200, "not json at all")
    with mock.patch("llm_client.requests.post", return_value=resp):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_missing_key():
    with mock.patch("config.OPENROUTER_API_KEY", ""):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_empty_array():
    resp = _fake_resp(200, "[]")
    with mock.patch("llm_client.requests.post", return_value=resp):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_network_error():
    with mock.patch(
        "llm_client.requests.post",
        side_effect=requests.exceptions.RequestException("boom"),
    ):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError as e:
            assert e.kind == "api"
