"""用虚构 BOSS 页面数据验收桥接、权限隔离和原工作流的断点恢复。"""

import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.api.server import create_app
from app.browser.bridge import BossBridge, BossPageDetail, BridgeUpdate
from app.adapters.boss import job_from_extension
from app.exceptions import InvalidTransitionError, JobParseError
from pydantic import ValidationError


def detail(job_id="fixture1"):
    return dict(url=f"https://www.zhipin.com/job_detail/{job_id}.html", title="Python 后端实习生",
                company="虚构桥接测试公司", description="需要 Python，SQL 优先。每周4天，实习6个月。",
                city="上海", salary="200元/天", extra="实习")


def wait_run(client, run_id, target):
    for _ in range(160):
        run = client.get("/api/runs/" + run_id).json()
        if run["status"] == target:
            return run
        if run["status"] == "FAILED":
            pytest.fail(str(run.get("error")))
        time.sleep(.03)
    pytest.fail(f"未到达 {target}，当前 {run['status']}")


def test_extension_returns_jobs_then_workflow_resumes_without_browser_or_repeat_extraction(tmp_path, monkeypatch):
    from app.llm.offline import OfflineLLMClient
    original = OfflineLLMClient.complete
    calls = []
    def complete(self, task, *args):
        calls.append(task)
        return original(self, task, *args)
    monkeypatch.setattr(OfflineLLMClient, "complete", complete)
    def no_browser(*args, **kwargs):
        pytest.fail("BOSS API 搜索不得启动 Playwright")
    monkeypatch.setattr("app.adapters.factory.BrowserSession", no_browser)
    app = create_app(tmp_path, token="main-test")
    with TestClient(app) as client:
        client.headers["X-JobPilot-Token"] = "main-test"
        response = client.post("/api/search", json=dict(text="虚构同学在课程项目中使用 Python 开发工具。",
            intent="Python 后端",cities=["上海"],source="boss",mode="offline",search_limit=2,available_days_per_week=3))
        assert response.status_code == 202
        run_id = response.json()["id"]
        before = wait_run(client, run_id, "PAUSED")
        assert calls.count("resume") == 1
        # 用户可能在助手尚未读完时点继续；多次暂停不能被当成完成。
        for _ in range(2):
            assert client.post(f"/api/runs/{run_id}/resume").status_code == 202
            wait_run(client, run_id, "PAUSED")
        key = client.post("/api/boss/connect").json()["connection"]
        headers = {"X-JobPilot-Bridge":key,"X-JobPilot-Reader":str(uuid4()),"Origin":"chrome-extension://abcdefgh"}
        response = client.get("/api/boss/next",headers=headers)
        assert response.status_code == 200
        task = response.json()["task"]
        assert task["id"] == run_id and "candidate" not in task and "text" not in task and "jobs" not in task
        assert client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"job":detail(),"pages":1}).status_code == 200
        # 重复回传不会产生两条岗位；主图仍停在读取节点。
        client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"job":detail(),"pages":1})
        assert client.get("/api/boss/status",params={"run_id":run_id}).json()["task"]["attempted"] == ["fixture1"]
        # 兼容已落盘的旧错误状态：有未处理中断的“完成”记录必须可以修复。
        app.state.runs.update(run_id,"COMPLETED")
        assert client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"finished":True,"complete":True,"pages":1}).status_code == 200
        # 下一次轮询也会处理“回传刚好早于主图暂停”的竞态。
        client.get("/api/boss/next",headers=headers)
        result = wait_run(client, run_id, "COMPLETED")
        assert result["snapshot"]["candidate"] == before["snapshot"]["candidate"]
        assert calls.count("resume") == 1
        row = result["snapshot"]["results"][0]
        assert row["job"]["source"] == "boss" and row["job"]["required_days_per_week"] == 4
        assert row["match"]["score"] >= 0 and row["deep_review"]
        assert client.get("/api/actions",params={"run_id":run_id}).json() == []


def test_bridge_credentials_cannot_read_resume_settings_or_approve(tmp_path):
    with TestClient(create_app(tmp_path,token="main")) as client:
        assert client.post("/api/boss/connect").status_code == 401
        key=client.post("/api/boss/connect",headers={"X-JobPilot-Token":"main"}).json()["connection"]
        headers={"X-JobPilot-Bridge":key,"X-JobPilot-Reader":str(uuid4())}
        assert client.get("/api/boss/next",headers=headers).status_code == 200
        for path in ("/api/runs","/api/model-settings","/api/candidate-example","/api/actions"):
            assert client.get(path,headers=headers).status_code == 401
        assert client.post("/api/actions/nope/decision",headers=headers,json={}).status_code == 401
        assert client.get("/api/boss/next",headers={**headers,"Origin":"https://www.zhipin.com"}).status_code == 403
        assert client.get("/api/boss/next",headers={**headers,"X-JobPilot-Reader":"../path"}).status_code == 422
        client.post("/api/boss/connect",headers={"X-JobPilot-Token":"main"})
        assert client.get("/api/boss/next",headers=headers).status_code == 401


def test_queue_persists_partial_results_pauses_and_excludes_other_readers(tmp_path):
    bridge=BossBridge(tmp_path)
    run_id=str(uuid4())
    bridge.ensure(run_id,["Python"],1,["上海"])
    assert bridge.claim("first")["id"]==run_id
    assert bridge.claim("second") is None
    with pytest.raises(InvalidTransitionError):bridge.update(run_id,"second",BridgeUpdate(job=BossPageDetail(**detail())))
    bridge.update(run_id,"first",BridgeUpdate(job=BossPageDetail(**detail())))
    with pytest.raises(InvalidTransitionError):bridge.update(run_id,"first",BridgeUpdate(job=BossPageDetail(**detail("excess"))))
    bridge.update(run_id,"first",BridgeUpdate(paused=True,warning="需要人工验证"))
    restored=BossBridge(tmp_path)
    assert restored.claim("second") is None
    restored.resume(run_id)
    assert restored.claim("second")["attempted"]==["fixture1"]
    restored.update(run_id,"second",BridgeUpdate(finished=True,complete=True))
    assert len(restored.get(run_id)["jobs"])==1
    assert restored.get(run_id)["complete"] is False  # 曾有中断或范围警告，不声称完整覆盖。


def test_expired_lease_can_be_recovered_but_old_reader_cannot_write(tmp_path,monkeypatch):
    bridge=BossBridge(tmp_path)
    bridge.ensure(str(uuid4()),["Python"],1,[])
    now=time.time()
    monkeypatch.setattr("app.browser.bridge.time.time",lambda:now)
    task=bridge.claim("old")
    monkeypatch.setattr("app.browser.bridge.time.time",lambda:now+61)
    assert bridge.claim("new")["id"]==task["id"]
    with pytest.raises(InvalidTransitionError):bridge.update(task["id"],"old",BridgeUpdate(finished=True))


@pytest.mark.parametrize("url",["https://evil.example/job_detail/x.html", "https://www.zhipin.com/web/geek/chat",
    "https://user@www.zhipin.com/job_detail/x.html", "https://www.zhipin.com/job_detail/x.html?token=secret",
    "http://www.zhipin.com/job_detail/x.html", "https://www.zhipin.com:443/job_detail/x.html"])
def test_only_clean_boss_detail_urls_are_accepted(url):
    with pytest.raises(JobParseError):job_from_extension(BossPageDetail(**{**detail(),"url":url}))


@pytest.mark.parametrize("body",[{"paused":True,"finished":True},{"complete":True},
    {"job":detail(),"skipped_id":"x"},{"finished":"false"}])
def test_ambiguous_progress_is_rejected(body):
    with pytest.raises(ValidationError):BridgeUpdate.model_validate(body)
