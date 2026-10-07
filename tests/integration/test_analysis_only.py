"""公开读取、规则和证据匹配必须连通，且不得进入草稿或执行节点。"""

from contextlib import contextmanager
from pathlib import Path
import time
import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.http_reader import PublicPageReader
from app.adapters.shixiseng import ShixisengAdapter
from app.api.server import create_app
from app.browser.selectors import SHIXISENG
from app.exceptions import LLMError
from app.llm.offline import OfflineLLMClient
from app.models.candidate import CandidateProfile
from app.workflow.runtime import graph_config, open_graph


def candidate():
    return CandidateProfile(id="synthetic-http-demo", name="虚构测试候选人", target_cities=["上海"],
        skills=[{"skill": "Python", "level": "project_experience", "evidence": "虚构测试：完成 Python 课程作业"}])


@contextmanager
def adapter():
    root = Path(__file__).resolve().parents[2] / "fixtures/browser"
    def respond(request):
        filename = "shixiseng_search.html" if request.url.path == "/interns" else "shixiseng_detail.html"
        text = (root / filename).read_text("utf-8")
        if request.url.path == "/interns":
            text = text.replace("</body>", '<a href="/intern/inn_unreadable">不可读测试</a></body>')
        if request.url.path.endswith("inn_unreadable"):
            text = text.replace("合成测试公司", "\ue123")
        if request.url.path.endswith("inn_demo2"):
            text = text.replace("上海", "成都")
        return httpx.Response(200, text=text, headers={"content-type": "text/html"})
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        yield ShixisengAdapter(reader)


def test_data_to_matching_and_restart_without_any_action(tmp_path, monkeypatch):
    monkeypatch.setattr("app.adapters.http_reader.time.sleep", lambda _: None)
    class AnalyzeOnlyClient(OfflineLLMClient):
        def complete(self, task, *args):
            assert task == "analyze", "只匹配模式不得生成沟通草稿"
            return super().complete(task, *args)
    incoming = {"run_id": "readonly", "candidate": candidate().model_dump(mode="json"),
                "source": "shixiseng", "mode": "offline", "queries": ["Python"], "analysis_only": True}
    config = graph_config("readonly")
    with adapter() as source, open_graph(tmp_path, source="shixiseng", adapter=source,
                                        client=AnalyzeOnlyClient()) as (graph, actions):
        graph.invoke(incoming, config)
        state = graph.get_state(config)
        assert not state.next and state.values["status"] == "COMPLETED"
        assert state.values["discovery"] == {"received": 2, "rejected": 1, "duplicates": 0, "retained": 1}
        assert "成都" in state.values["rejected_jobs"][0]["reasons"][0]
        result = state.values["results"][0]
        assert result["match"]["matched_skills"] == ["Python"]
        assert "SQL" in result["match"]["missing_skills"]
        assert result["outcome"] == "MATCHED" and result["draft"] is None and result["action_id"] is None
        assert not actions.list()
        assert len(state.values["source_warnings"]) == 1 and "inn_unreadable" in state.values["source_warnings"][0]
    with adapter() as source, open_graph(tmp_path, source="shixiseng", adapter=source) as (graph, actions):
        assert graph.get_state(config).values["results"] == state.values["results"]
        assert not actions.list()


def test_analysis_only_survives_model_failure_and_resume(tmp_path):
    class FailOnce(OfflineLLMClient):
        def complete(self, *args, **kwargs):
            raise LLMError("测试模型失败")
    from app.config import load_settings
    from app.main import load_candidate
    config = graph_config("recover-analysis")
    initial = {"run_id": "recover-analysis", "source": "mock", "mode": "offline", "queries": [],
               "candidate": load_candidate(load_settings().candidate_path).model_dump(mode="json"), "analysis_only": True}
    with open_graph(tmp_path, client=FailOnce()) as (graph, actions):
        with pytest.raises(LLMError):
            graph.invoke(initial, config)
        assert graph.get_state(config).next == ("analyze",)
    with open_graph(tmp_path) as (graph, actions):
        graph.invoke(None, config)
        state = graph.get_state(config)
        assert not state.next and len(state.values["results"]) == 11
        assert not actions.list()


def test_api_shixiseng_analysis_only_uses_same_pipeline(tmp_path, monkeypatch):
    def open_source(source, *, limit=None):
        assert source == "shixiseng"
        assert limit is None
        return adapter()
    monkeypatch.setattr("app.adapters.factory.open_adapter", open_source)
    with TestClient(create_app(tmp_path, token="test"), headers={"X-JobPilot-Token": "test"}) as client:
        response = client.post("/api/runs", json={"candidate": candidate().model_dump(mode="json"),
                                                "source": "shixiseng", "analysis_only": True})
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(120):
            result = client.get(f"/api/runs/{run_id}").json()
            if result["status"] in {"COMPLETED", "FAILED", "PAUSED"}:
                break
            time.sleep(0.05)
        assert result["status"] == "COMPLETED", result
        assert result["snapshot"]["analysis_only"] is True
        assert len(result["snapshot"]["results"]) == 1
        assert client.get(f"/api/actions?run_id={run_id}").json() == []
