"""本机页面可配置模型；鉴权、原配置、密钥保密与测试调用均需保留。"""

import json
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.llm import client as llm
from app.models.analysis import GreetingPlan
from app.services import model_settings


@pytest.fixture
def settings_client(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# 保留用户设置\nDATABASE_URL='sqlite:///private.db'\nLLM_API_KEY=\n", encoding="utf-8")
    monkeypatch.setattr(llm, "LLM_SETTINGS_PATH", path)
    for name in ["LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_API_STYLE"]:
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(tmp_path / "data", token="local-test-connection"),
                    headers={"X-JobPilot-Token": "local-test-connection"}) as client:
        yield client, path


def test_save_preserves_settings_and_never_returns_key(settings_client):
    client, path = settings_client
    assert not client.get("/api/model-settings").json()["configured"]
    key = "synthetic-private-deepseek-key"
    result = client.post("/api/model-settings", json={"api_key": key})
    assert result.status_code == 200 and result.json()["configured"]
    assert key not in result.text and key not in client.get("/api/model-settings").text
    values = dotenv_values(path, interpolate=False)
    assert values["DATABASE_URL"] == "sqlite:///private.db"
    assert values["LLM_API_KEY"] == key and values["LLM_API_STYLE"] == "responses"
    assert "# 保留用户设置" in path.read_text("utf-8")
    assert llm.create_llm("live").url == "https://api.deepseek.com/responses"
    assert not list(path.parent.glob(".env.*.tmp"))


@pytest.mark.parametrize("key", ["private\nLLM_MODEL=bad", {"secret": "private-key-value"}, "short"])
def test_invalid_key_never_leaks_or_changes_file(settings_client, key):
    client, path = settings_client
    original = path.read_bytes()
    response = client.post("/api/model-settings", json={"api_key": key})
    assert response.status_code in {409, 422}
    assert "private-key-value" not in response.text and "LLM_MODEL=bad" not in response.text
    assert path.read_bytes() == original


def test_settings_need_local_auth_and_same_origin(settings_client):
    client, path = settings_client
    original = path.read_bytes()
    for suffix in ["", "/test"]:
        assert client.post("/api/model-settings" + suffix, json={"api_key": "test-private-key"},
                           headers={"X-JobPilot-Token": "wrong"}).status_code == 401
        assert client.post("/api/model-settings" + suffix, json={"api_key": "test-private-key"},
                           headers={"Origin": "https://external.invalid"}).status_code == 403
    assert path.read_bytes() == original


def test_environment_override_and_failed_write_preserve_old_file(settings_client, monkeypatch):
    client, path = settings_client
    original = path.read_bytes()
    monkeypatch.setenv("LLM_API_KEY", "process-private-key")
    assert client.post("/api/model-settings", json={"api_key": "test-private-key"}).status_code == 409
    monkeypatch.delenv("LLM_API_KEY")
    def failed_replace(*args):
        raise PermissionError("private-file-error")
    monkeypatch.setattr(model_settings.os, "replace", failed_replace)
    result = client.post("/api/model-settings", json={"api_key": "test-private-key"})
    assert result.status_code == 409 and "private" not in result.text
    assert path.read_bytes() == original and not list(path.parent.glob(".env.*.tmp"))


def test_connection_is_explicit_and_uses_no_resume(settings_client, monkeypatch):
    client, path = settings_client
    calls = []
    def complete(self, task, payload, schema):
        calls.append((task, payload))
        return GreetingPlan(evidence_ids=["connection-test"])
    monkeypatch.setattr(llm.CompatibleLLMClient, "complete", complete)
    client.post("/api/model-settings", json={"api_key": "synthetic-private-key"})
    assert calls == []
    response = client.post("/api/model-settings/test")
    assert response.status_code == 200 and response.json()["ok"]
    assert len(calls) == 1 and calls[0][1]["allowed_evidence_ids"] == ["connection-test"]
    assert "synthetic-private-key" not in json.dumps(calls) + response.text


def test_saved_deepseek_config_reaches_background_workflow(settings_client, monkeypatch):
    """页面保存配置后，新任务立即使用该配置，无需重启；HTTP 答复仍由本地模拟。"""
    from unittest.mock import MagicMock
    from app.llm.offline import OfflineLLMClient
    from app.models.analysis import JobAnalysis
    from tests.integration.test_http_api import wait_for_pause

    client, _ = settings_client
    requests = []
    def open_response(request, timeout):
        requests.append(request)
        body = json.loads(request.data)
        payload = json.loads(body["input"][1]["content"])
        assert set(payload) == {"description"}  # 不把候选人资料夹带进岗位分析。
        analysis = OfflineLLMClient().complete("analyze", payload, JobAnalysis)
        raw = {"status": "completed", "output": [{"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": analysis.model_dump_json()}]}],
            "usage": {"input_tokens": 30, "output_tokens": 20}}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(raw).encode()
        return response
    opener = MagicMock()
    opener.open.side_effect = open_response
    monkeypatch.setattr(llm, "build_opener", lambda *args: opener)
    assert client.post("/api/model-settings", json={"api_key": "synthetic-private-key"}).status_code == 200
    profile = client.get("/api/candidate-example").json()
    response = client.post("/api/runs", json={"candidate": profile, "mode": "live", "source": "mock",
                                             "search_limit": 1, "analysis_only": True})
    assert response.status_code == 202
    result = wait_for_pause(client, response.json()["id"])
    assert result["status"] == "COMPLETED" and result["snapshot"]["results"]
    assert len(requests) == 1 and requests[0].full_url == "https://api.deepseek.com/responses"
    assert client.get("/api/actions").json() == []
