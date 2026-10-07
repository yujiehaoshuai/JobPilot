"""API 通过真实工作线程和临时数据库验证鉴权、审批以及状态流。"""

import time
from fastapi.testclient import TestClient
from app.api.server import create_app


def wait_for_pause(client, run_id):
    for _ in range(100):
        result = client.get(f"/api/runs/{run_id}").json()
        if result["status"] in {"PAUSED", "FAILED", "COMPLETED"}:
            assert result["status"] != "FAILED", result.get("error")
            return result
        time.sleep(0.05)
    raise AssertionError("API 任务未在预期时间内暂停")


def test_api_auth_and_origin(tmp_path):
    with TestClient(create_app(tmp_path, token="test-token")) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/runs").status_code == 401
        assert client.get("/api/runs", headers={"X-JobPilot-Token": "test-token", "Origin": "https://evil.test"}).status_code == 403


def test_api_workflow_approval_and_sse(tmp_path):
    with TestClient(create_app(tmp_path, token="test-token"), headers={"X-JobPilot-Token": "test-token"}) as client:
        profile = client.get("/api/candidate-example").json()
        response = client.post("/api/runs", json={"candidate": profile})
        assert response.status_code == 202
        run_id = response.json()["id"]
        state = wait_for_pause(client, run_id)
        assert state["interrupts"][0]["kind"] == "approval"
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 409
        action = client.get("/api/actions", params={"run_id": run_id}).json()[0]
        assert client.post(f"/api/actions/{action['id']}/decision", json={"digest": "0" * 64, "approve": True}).status_code == 409
        assert client.post(f"/api/actions/{action['id']}/decision", json={"digest": action["digest"], "approve": False}).status_code == 200
        response = client.get(f"/api/runs/{run_id}/events")
        assert "event: state" in response.text and "text/event-stream" in response.headers["content-type"]
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 202
        wait_for_pause(client, run_id)
        assert client.get("/api/applications").json()


def test_api_rejects_invalid_candidate(tmp_path):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token": "t"}) as client:
        assert client.post("/api/runs", json={"candidate": {"name": "缺少编号"}}).status_code == 422


def test_search_limit_is_persisted_and_used_by_worker(tmp_path):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        profile = client.get("/api/candidate-example").json()
        run_id = client.post("/api/runs", json={"candidate":profile,"analysis_only":True,"search_limit":2}).json()["id"]
        result = wait_for_pause(client, run_id)
        assert result["status"] == "COMPLETED"
        assert result["snapshot"]["search_limit"] == 2
        assert result["snapshot"]["discovery"]["received"] == 2
        for limit in [0, 41, True, "5"]:
            assert client.post("/api/runs",json={"candidate":profile,"search_limit":limit}).status_code == 422


def test_unconfigured_live_model_does_not_create_failed_run(tmp_path, monkeypatch):
    from app.exceptions import ConfigurationError
    def missing_config(mode):
        assert mode == "live"
        raise ConfigurationError("请配置本机模型")
    monkeypatch.setattr("app.llm.client.create_llm", missing_config)
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        profile = client.get("/api/candidate-example").json()
        response = client.post("/api/runs", json={"candidate":profile,"mode":"live"})
        assert response.status_code == 409 and "配置" in response.json()["detail"]
        assert client.get("/api/runs").json() == []


def test_api_manual_recovery_preserves_approval_boundary(tmp_path):
    from app.storage.relational import database_engine, RelationalActionStore
    url = "sqlite:///" + (tmp_path / "agent.db").as_posix()
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token": "t"}) as client:
        profile = client.get("/api/candidate-example").json()
        run_id = client.post("/api/runs", json={"candidate": profile}).json()["id"]
        wait_for_pause(client, run_id)
        action = client.get("/api/actions", params={"run_id": run_id}).json()[0]
        path = f"/api/actions/{action['id']}/resolve"
        body = {"digest": action["digest"], "sent": False, "note": "人工核对未发送"}
        assert client.post(path, json=body).status_code == 409
        engine = database_engine(url)
        try:
            store = RelationalActionStore(engine)
            store.decide(action["id"], action["digest"], True, "test-human")
            store.transition(action["id"], "APPROVED", "EXECUTING")
            store.transition(action["id"], "EXECUTING", "UNCERTAIN")
            response = client.post(path, json=body)
            assert response.status_code == 200
            assert response.json()["status"] == "REJECTED"
            assert response.json()["resolved_by"] == "authenticated-local-user"
        finally:
            engine.dispose()
