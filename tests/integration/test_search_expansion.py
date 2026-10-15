"""扩大搜索沿用原任务、城市与检查点；旧岗位不重复分析，审批不受影响。"""

from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.api.server import create_app
from app.adapters.shixiseng import ShixisengAdapter
from app.llm.offline import OfflineLLMClient
from tests.integration.test_boss_bridge import wait_run, detail


def body(**changes):
    result = dict(text="虚构同学在课程项目中使用 Python 开发工具。", intent="Python",
        cities=["上海市"], source="shixiseng", mode="offline", search_limit=2)
    return {**result, **changes}


@pytest.mark.parametrize("cities", [None, [], [" "], ["全国"]])
def test_city_is_required_before_starting_work(tmp_path, cities):
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        request = body(cities=cities)
        if cities is None:
            request.pop("cities")
        assert client.post("/api/search", json=request).status_code in {409, 422}
        assert client.get("/api/runs").json() == []


def test_expand_reuses_details_model_results_and_survives_service_restart(tmp_path, monkeypatch, make_job):
    downloads, calls, parameters = [], [], []
    original = OfflineLLMClient.complete
    def complete(self, task, *args):
        calls.append(task)
        return original(self, task, *args)
    monkeypatch.setattr(OfflineLLMClient, "complete", complete)
    class Reader:
        def validate_url(self, url): pass
        def read(self, url, selector):
            params = parse_qs(urlsplit(url).query)
            assert params["city"] == ["上海"]
            return "".join(f'<a href="/intern/inn_{i}">岗位</a>' for i in range(60))
    @contextmanager
    def source(name, *, limit=None, cities=None, known_jobs=None, attempted_ids=None):
        assert name == "shixiseng"
        parameters.append((limit, cities, len(known_jobs or [])))
        adapter = ShixisengAdapter(Reader(), limit, cities, known_jobs, attempted_ids)
        def get_detail(job_id):
            downloads.append(job_id)
            return make_job(id="shixiseng:"+job_id, source="shixiseng", source_job_id=job_id,
                city="上海", title="Python 实习生", description="需要 Python", url="https://www.shixiseng.com/intern/"+job_id)
        adapter.get_job_detail = get_detail
        yield adapter
    monkeypatch.setattr("app.adapters.factory.open_adapter", source)
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        run_id = client.post("/api/search", json=body()).json()["id"]
        first = wait_run(client, run_id, "COMPLETED")
        assert len(first["snapshot"]["results"]) == 2
        assert first["snapshot"]["search_coverage"]["limit_reached"]
        response = client.post(f"/api/runs/{run_id}/expand", json={"expected_limit":2})
        assert response.status_code == 202 and response.json()["search_limit"] == 52
        assert client.post(f"/api/runs/{run_id}/expand", json={"expected_limit":2}).status_code == 409
        second = wait_run(client, run_id, "COMPLETED")
        assert len(second["snapshot"]["results"]) == 52
        old = {row["job"]["id"]:row for row in first["snapshot"]["results"]}
        for row in second["snapshot"]["results"]:
            if row["job"]["id"] in old:
                assert row["analysis"] == old[row["job"]["id"]]["analysis"]
                assert row["match"] == old[row["job"]["id"]]["match"]
        # 模拟额度已保存、工作线程尚未启动就退出。新服务必须接续原检查点。
        client.app.state.runs.expand_search(run_id, 52)
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "QUEUED"
    # 新进程从原数据库和检查点继续，不使用上一个工作线程的内存缓存。
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        assert client.get(f"/api/runs/{run_id}").json()["input"]["search_limit"] == 102
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 202
        final = wait_run(client, run_id, "COMPLETED")
        assert len(final["snapshot"]["results"]) == 60
        assert not final["snapshot"]["search_coverage"]["limit_reached"]
        assert client.post(f"/api/runs/{run_id}/expand", json={"expected_limit":102}).status_code == 409
        assert client.get("/api/actions").json() == []
    assert len(downloads) == len(set(downloads)) == 60
    assert calls.count("resume") == 1 and calls.count("search_analyze") == 60
    assert parameters == [(2,["上海"],0), (52,["上海"],2), (102,["上海"],52)]


def test_boss_expansion_keeps_attempts_and_only_analyzes_new_jobs(tmp_path, monkeypatch):
    calls = []
    original = OfflineLLMClient.complete
    def complete(self, task, *args):
        calls.append(task)
        return original(self, task, *args)
    monkeypatch.setattr(OfflineLLMClient, "complete", complete)
    with TestClient(create_app(tmp_path, token="t"), headers={"X-JobPilot-Token":"t"}) as client:
        run_id = client.post("/api/search", json=body(source="boss", search_limit=1)).json()["id"]
        wait_run(client, run_id, "PAUSED")
        key = client.post("/api/boss/connect").json()["connection"]
        headers = {"X-JobPilot-Bridge":key,"X-JobPilot-Reader":str(uuid4())}
        task = client.get("/api/boss/next", headers=headers).json()["task"]
        assert task["search_cities"] == [{"name":"上海","code":"101020100"}]
        client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"job":detail(),"pages":1})
        client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"finished":True,"limit_reached":True,"pages":1})
        client.get("/api/boss/next",headers=headers)
        wait_run(client, run_id, "COMPLETED")
        assert client.post(f"/api/runs/{run_id}/expand",json={"expected_limit":1}).status_code == 202
        wait_run(client, run_id, "PAUSED")
        task = client.get("/api/boss/next",headers=headers).json()["task"]
        assert task["limit"] == 51 and task["attempted"] == ["fixture1"]
        second = {**detail(),"url":"https://www.zhipin.com/job_detail/fixture2.html"}
        client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"job":second,"pages":2})
        client.post(f"/api/boss/tasks/{run_id}",headers=headers,json={"finished":True,"complete":True,"pages":2})
        client.get("/api/boss/next",headers=headers)
        final = wait_run(client,run_id,"COMPLETED")
        assert len(final["snapshot"]["results"]) == 2
        assert calls.count("resume") == 1 and calls.count("search_analyze") == 2
        assert client.get("/api/actions").json() == []
