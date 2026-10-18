"""历史清理必须真正删掉搜索副本，同时保住联系记录、共享资料和恢复边界。"""

from concurrent.futures import Future
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.api.server import create_app
from app.models.action import ActionPayload
from app.storage.relational import candidate_table, job_table, application_table
from app.workflow.checkpoints import open_checkpointer
from app.workflow.runtime import graph_config
from tests.integration.test_http_api import wait_for_pause


def finished_search(client, candidate_id=None):
    profile = client.get("/api/candidate-example").json()
    if candidate_id is not None:
        profile["id"] = candidate_id
    run_id = client.post("/api/runs", json={"candidate": profile,
        "analysis_only": True, "search_limit": 2}).json()["id"]
    assert wait_for_pause(client, run_id)["status"] == "COMPLETED"
    # 完成状态现在意味着资源已释放；按用户操作直接清理，不等待内部 Future。
    return run_id


def test_cleanup_removes_snapshot_checkpoint_bridge_and_unshared_data(tmp_path):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        run_id = finished_search(client)
        worker, bridge = client.app.state.worker, client.app.state.boss_bridge
        bridge.ensure(run_id, ["Python"], 2, ["上海"])
        with open_checkpointer(tmp_path) as saver:
            assert saver.get_tuple(graph_config(run_id)) is not None
        result = client.delete("/api/runs/history")
        assert result.status_code == 200 and result.json()["deleted_ids"] == [run_id]
        assert client.get(f"/api/runs/{run_id}").status_code == 404
        assert bridge.get(run_id) is None
        with open_checkpointer(tmp_path) as saver:
            assert saver.get_tuple(graph_config(run_id)) is None
        with worker.runs.engine.connect() as conn:
            for table in [candidate_table, job_table, application_table]:
                assert conn.execute(select(func.count()).select_from(table)).scalar_one() == 0
        assert client.delete("/api/runs/history").json()["deleted_count"] == 0


def test_cleanup_preserves_shared_profile_jobs_and_contact_history(tmp_path):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        first, second = finished_search(client), finished_search(client)
        service = client.app.state.boss_contacts
        run = client.app.state.runs.get(second)
        payload = ActionPayload(candidate=run["snapshot"]["candidate"], job=run["snapshot"]["jobs"][0],
            content="虚构审批记录", evidence_ids=[])
        action = service.actions.prepare(second, payload)
        result = client.delete("/api/runs/history").json()
        assert result == {"deleted_ids":[first], "deleted_count":1, "kept_count":1}
        assert service.actions.get(action.id) == action
        assert service.tracker.list_jobs() and service.tracker.list_applications()
        with open_checkpointer(tmp_path) as saver:
            assert saver.get_tuple(graph_config(second)) is not None


def test_cleanup_failure_can_resume_cleanup_but_never_restart_search(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"},
                    raise_server_exceptions=False) as client:
        run_id = finished_search(client)
        bridge = client.app.state.boss_bridge
        original = bridge.delete_request
        def unavailable(run_id):
            raise OSError("合成写入失败")
        monkeypatch.setattr(bridge, "delete_request", unavailable)
        assert client.delete("/api/runs/history").status_code == 500
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "DELETING"
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 409
        assert client.post(f"/api/runs/{run_id}/expand", json={"expected_limit":2}).status_code == 409
        monkeypatch.setattr(bridge, "delete_request", original)
        assert client.delete("/api/runs/history").json()["deleted_count"] == 1


def test_cleanup_requires_auth_and_waits_for_running_worker(tmp_path):
    with TestClient(create_app(tmp_path, token="t")) as client:
        assert client.delete("/api/runs/history").status_code == 401
        client.headers["X-JobPilot-Token"] = "t"
        assert client.delete("/api/runs/history", headers={"Origin":"https://evil.test"}).status_code == 403
        run_id = finished_search(client)
        pending = Future()
        client.app.state.worker.futures["pending"] = pending
        assert client.delete("/api/runs/history").status_code == 409
        pending.set_result(None)
        assert client.get(f"/api/runs/{run_id}").status_code == 200


def test_cleanup_preserves_manually_tracked_progress(tmp_path):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        run_id = finished_search(client)
        tracker = client.app.state.boss_contacts.tracker
        application = tracker.list_applications()[0]
        tracker.update_status(application.id, "CONTACT_READY", confirmed=True)
        assert client.delete("/api/runs/history").json()["deleted_count"] == 0
        assert client.get(f"/api/runs/{run_id}").status_code == 200


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "PAUSED"])
def test_cleanup_preserves_unfinished_runs(tmp_path, status):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        run_id = str(uuid4())
        client.app.state.runs.create(run_id, {"source":"mock", "input":{"analysis_only":True}})
        client.app.state.runs.update(run_id, status)
        assert client.delete("/api/runs/history").json()["deleted_count"] == 0
        assert client.get(f"/api/runs/{run_id}").json()["status"] == status
