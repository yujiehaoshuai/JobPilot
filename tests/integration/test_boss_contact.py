"""用临时数据库模拟用户审批和扩展回执；不连接 BOSS、不点击真实岗位。"""

from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.api.boss_contact import ObservedContact
from app.exceptions import ConfirmationRequiredError
from app.services.boss_contact import BossContactService
from app.models.action import ActionPayload


@pytest.fixture
def contact_env(tmp_path, candidate, make_job):
    app = create_app(tmp_path, token="main-test")
    service = app.state.boss_contacts
    main = {"X-JobPilot-Token": "main-test"}
    jobs = [make_job(id=f"boss-{i}", source="boss", source_job_id=f"fixture{i}",
        url=f"https://www.zhipin.com/job_detail/fixture{i}.html") for i in range(3)]
    run_id = str(uuid4())
    service.tracker.save_candidate(candidate)
    service.tracker.save_jobs(jobs)
    app.state.runs.create(run_id, {"source": "boss", "snapshot": {
        "candidate": candidate.model_dump(mode="json"),
        "results": [{"job": job.model_dump(mode="json")} for job in jobs]}})
    app.state.runs.update(run_id, "COMPLETED")
    with TestClient(app) as client:
        key = client.post("/api/boss/connect", headers=main).json()["connection"]
        bridge = {"X-JobPilot-Bridge": key, "X-JobPilot-Reader": str(uuid4())}
        yield client, service, run_id, main, bridge


def prepare(env, ids=("boss-0", "boss-1")):
    client, _, run_id, main, _ = env
    response = client.post(f"/api/runs/{run_id}/boss-actions", headers=main, json={"job_ids": list(ids)})
    assert response.status_code == 200, response.text
    return response.json()["actions"]


def decide(env, actions, approve=True, confirmed=True):
    client, _, _, main, _ = env
    return client.post("/api/boss-actions/decision", headers=main, json={
        "actions": [{"id": a["id"], "digest": a["digest"]} for a in actions],
        "approve": approve, "platform_details_confirmed": confirmed})


def permit(env, action, **changes):
    client, _, _, _, bridge = env
    job = action["payload"]["job"]
    return client.post(f"/api/boss/contacts/{action['id']}/permit", headers=bridge, json={
        "digest": action["digest"], "observed": {"job_id": job["source_job_id"],
        "title": job["title"], "company": job["company"], "button": "立即沟通", **changes}})


def test_selection_does_not_approve_and_bridge_cannot_approve(contact_env):
    env = contact_env
    client, service, run_id, main, bridge = env
    actions = prepare(env, ("boss-1",))
    assert len(actions) == 1 and actions[0]["status"] == "PENDING"
    assert service.next() is None
    assert permit(env, actions[0]).status_code == 409
    assert decide(env, actions, confirmed=False).status_code == 409
    assert client.post("/api/boss-actions/decision", headers=bridge, json={}).status_code == 401
    assert client.get("/api/boss-actions", headers=bridge).status_code == 401
    assert client.post(f"/api/actions/{actions[0]['id']}/decision", headers=main,
        json={"digest": actions[0]["digest"], "approve": True}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/boss-actions", headers=main,
        json={"job_ids": ["not-in-results"]}).status_code == 409


def test_batch_decision_rolls_back_if_any_digest_changes(contact_env):
    actions = prepare(contact_env)
    altered = [actions[0], {**actions[1], "digest": "0" * 64}]
    assert decide(contact_env, altered).status_code == 409
    assert {a.status for a in contact_env[1].list()} == {"PENDING"}
    assert decide(contact_env, [actions[0], actions[0]]).status_code == 409
    assert decide(contact_env, actions).status_code == 200
    assert decide(contact_env, actions, approve=False).status_code == 200
    assert contact_env[1].next() is None


def test_one_use_permit_checks_exact_target_and_receipt_owner(contact_env):
    env = contact_env
    client, service, _, main, bridge = env
    actions = prepare(env)
    assert decide(env, actions).status_code == 200
    public = client.get("/api/boss/contacts/next", headers=bridge).json()["action"]
    assert set(public) == {"id", "digest", "job_id", "url", "title", "company", "kind"}
    action = next(a for a in actions if a["id"] == public["id"])
    for changes in ({"job_id": "other"}, {"title": "不同岗位"}, {"company": "不同公司"}, {"button": "发送"}):
        assert permit(env, action, **changes).status_code == 409
    response = permit(env, action)
    assert response.status_code == 200
    ticket = response.json()
    assert permit(env, action).status_code == 409
    assert service.next() is None
    # 浏览器可能仍在点击，人工核查入口不能提前解除执行状态。
    assert client.post(f"/api/actions/{action['id']}/resolve", headers=main,
        json={"digest": action["digest"], "sent": False, "note": "人工看到还没有联系"}).status_code == 409
    path = f"/api/boss/contacts/{action['id']}/receipt"
    body = {"token": ticket["token"], "confirmed": True}
    assert client.post(path, headers={**bridge, "X-JobPilot-Reader": str(uuid4())}, json=body).status_code == 409
    assert client.post(path, headers=bridge, json={**body, "token": "x" * 43}).status_code == 409
    assert client.post(path, headers=bridge, json=body).json()["status"] == "SUCCEEDED"
    assert client.post(path, headers=bridge, json=body).json()["status"] == "SUCCEEDED"
    assert service.tracker.list_applications()[0].status == "CONTACTED"
    assert service.next()["id"] != action["id"]


def test_pause_timeout_restart_and_manual_resolution(contact_env, tmp_path):
    env = contact_env
    client, service, _, main, bridge = env
    actions = prepare(env)
    decide(env, actions)
    action = next(a for a in actions if a["id"] == service.next()["id"])
    ref = {"id": action["id"], "digest": action["digest"]}
    assert client.post(f"/api/boss/contacts/{action['id']}/pause", headers=bridge,
        json={"digest": action["digest"], "message": "请手动登录"}).status_code == 200
    assert service.next() is None
    assert client.post(f"/api/boss-actions/{action['id']}/resume", headers=bridge, json=ref).status_code == 401
    assert client.post(f"/api/boss-actions/{action['id']}/resume", headers=main, json=ref).status_code == 200
    permit(env, action)
    service.actions.transition(action["id"], "EXECUTING", "EXECUTING",
        execution_started_at=datetime.now(UTC) - timedelta(seconds=91))
    restored = BossContactService(service.actions, service.runs, service.tracker, tmp_path)
    assert restored.next() is None
    assert restored.actions.get(action["id"]).status == "UNCERTAIN"
    assert permit(env, action).status_code == 409
    assert client.post(f"/api/actions/{action['id']}/resolve", headers=main,
        json={"digest": action["digest"], "sent": False, "note": "我已核查没有发起沟通"}).json()["status"] == "REJECTED"
    assert restored.next()["id"] != action["id"]


def test_uncertain_receipt_blocks_queue_and_tracker_recovers(contact_env, monkeypatch):
    env = contact_env
    client, service, _, main, bridge = env
    actions = prepare(env)
    decide(env, actions)
    action = next(a for a in actions if a["id"] == service.next()["id"])
    ticket = permit(env, action).json()
    path = f"/api/boss/contacts/{action['id']}/receipt"
    assert client.post(path, headers=bridge, json={"token": ticket["token"], "confirmed": False}).json()["status"] == "UNCERTAIN"
    assert service.next() is None
    # 模拟动作结果已落盘，但进程尚未来得及更新 Tracker 就退出。
    original = service.sync_tracker
    monkeypatch.setattr(service, "sync_tracker", lambda action: None)
    client.post(f"/api/actions/{action['id']}/resolve", headers=main,
        json={"digest": action["digest"], "sent": True, "note": "人工核查已显示继续沟通"})
    assert service.tracker.list_applications() == []
    monkeypatch.setattr(service, "sync_tracker", original)
    service.list()
    assert service.tracker.list_applications()[0].status == "CONTACTED"


def test_same_job_in_another_run_is_not_contacted_twice(contact_env):
    _, service, run_id, _, _ = contact_env
    prepare(contact_env, ("boss-0",))
    original = service.runs.get(run_id)
    second_id = str(uuid4())
    service.runs.create(second_id, {"source": "boss", "snapshot": original["snapshot"]})
    service.runs.update(second_id, "COMPLETED")
    result = service.prepare(second_id, ["boss-0", "boss-2"])
    assert [a.payload.job.id for a in result["actions"]] == ["boss-2"]
    assert result["skipped"][0]["job_id"] == "boss-0"


def test_old_message_payload_keeps_its_persisted_digest(candidate, make_job):
    old = {"kind": "send_message", "candidate": candidate.model_dump(mode="json"), "job": make_job().model_dump(mode="json"),
           "content": "旧版虚构草稿", "evidence_ids": [], "simulated": True}
    digest = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    payload = ActionPayload.model_validate(old)
    assert payload.kind == "send_message"
    assert payload.digest() == digest
    assert payload.model_copy(update={"kind": "boss_start_chat"}).digest() != digest


def test_two_helpers_cannot_claim_the_same_approval(contact_env):
    actions = prepare(contact_env, ("boss-0",))
    decide(contact_env, actions)
    action = actions[0]
    job = action["payload"]["job"]
    observed = ObservedContact(job_id=job["source_job_id"], title=job["title"], company=job["company"], button="立即沟通")
    barrier = Barrier(2)

    def claim(owner):
        barrier.wait(timeout=5)
        try:
            contact_env[1].authorize(action["id"], action["digest"], owner, observed)
            return "permitted"
        except ConfirmationRequiredError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, ["helper-a", "helper-b"])) == ["blocked", "permitted"]
