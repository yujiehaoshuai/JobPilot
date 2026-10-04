"""真实 LangGraph 和 SQLite 检查点的跨实例恢复测试。"""

import pytest
from langgraph.types import Command
from app.config import load_settings
from app.main import load_candidate
from app.llm.offline import OfflineLLMClient
from app.workflow.runtime import open_graph, graph_config
from app.exceptions import BrowserPausedError, LLMError, ConfirmationRequiredError
from app.adapters.mock.adapter import MockJobAdapter


def initial(run_id="test-run"):
    profile = load_candidate(load_settings().candidate_path)
    return {"run_id": run_id, "candidate": profile.model_dump(mode="json"),
            "queries": ["Python"], "source": "mock", "mode": "offline"}


def test_restart_approve_reject_loop(tmp_path):
    config = graph_config("test-run")
    with open_graph(tmp_path) as (graph, actions):
        graph.invoke(initial(), config)
        assert graph.get_state(config).next == ("review",)
        assert len(actions.list()) == 1
    # 每轮重新创建图和数据库连接，证明状态来自磁盘而非内存。
    count = 0
    while True:
        with open_graph(tmp_path) as (graph, actions):
            state = graph.get_state(config)
            if not state.next:
                assert state.values["status"] == "COMPLETED"
                assert len(state.values["results"]) == len(state.values["jobs"])
                assert actions.list()[0].status == "SUCCEEDED"
                break
            action = actions.get(state.values["action_id"])
            actions.decide(action.id, action.digest, count == 0, "test-human")
            graph.invoke(Command(resume=True), config)
        count += 1
        assert count < 20


def test_resume_is_not_approval(tmp_path):
    config = graph_config("test-run")
    with open_graph(tmp_path) as (graph, actions):
        graph.invoke(initial(), config)
        with pytest.raises(ConfirmationRequiredError):
            graph.invoke(Command(resume=True), config)
        assert actions.list()[0].status == "PENDING"


def test_login_pause_and_resume(tmp_path):
    class LoginAdapter(MockJobAdapter):
        locked = True
        def search_jobs(self, queries=None):
            if self.locked:
                raise BrowserPausedError("需要登录")
            return super().search_jobs(queries)
    adapter = LoginAdapter(load_settings().jobs_path)
    config = graph_config("test-run")
    with open_graph(tmp_path, adapter=adapter) as (graph, actions):
        result = graph.invoke(initial(), config)
        assert result["__interrupt__"][0].value["kind"] == "browser"
        assert not actions.list()
        adapter.locked = False
        graph.invoke(Command(resume=True), config)
        assert graph.get_state(config).next == ("review",)


def test_failure_recovery_retries_only_failed_node(tmp_path):
    class FailingLLM(OfflineLLMClient):
        def complete(self, *args, **kwargs):
            raise LLMError("服务暂不可用")
    config = graph_config("test-run")
    with open_graph(tmp_path, client=FailingLLM()) as (graph, actions):
        with pytest.raises(LLMError):
            graph.invoke(initial(), config)
        assert graph.get_state(config).next == ("analyze",)
    with open_graph(tmp_path) as (graph, actions):
        graph.invoke(None, config)
        assert graph.get_state(config).next == ("review",)
