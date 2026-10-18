"""让工作线程暂不开始，稳定复现恢复请求返回后仍显示旧暂停状态的问题。"""

from threading import Event
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from app.api.worker import WorkflowWorker
from app.storage.relational import RunStore, database_engine
from app.exceptions import InvalidTransitionError


def test_resume_is_queued_before_background_work_and_rejection_rolls_back(tmp_path):
    engine = database_engine("sqlite:///" + (tmp_path / "queue.db").as_posix(), initialize=True)
    runs = RunStore(engine)
    runs.create("r", {"source": "mock", "mode": "offline"})
    runs.update("r", "PAUSED")
    worker = WorkflowWorker(runs, tmp_path, str(engine.url))
    release = Event()
    worker.run = lambda _: release.wait(timeout=5)
    try:
        worker.submit("r")
        assert runs.get("r")["status"] == "QUEUED"
        release.set()
        worker.close()
        runs.update("r", "PAUSED")
        with pytest.raises(InvalidTransitionError, match="已停止"):
            worker.submit("r")
        assert runs.get("r")["status"] == "PAUSED"
    finally:
        release.set()
        worker.close()
        engine.dispose()


def test_pause_is_published_after_cleanup_and_can_resume_before_thread_returns(tmp_path, monkeypatch):
    """人为拉长资源关闭和线程返回的窗口，检查立即恢复与重复点击的边界。"""
    engine = database_engine("sqlite:///" + (tmp_path / "pause.db").as_posix(), initialize=True)
    runs = RunStore(engine)
    runs.create("r", {"source": "mock", "mode": "offline", "input": {}})
    worker = WorkflowWorker(runs, tmp_path, str(engine.url))
    closing, allow_close, returning, allow_return = (Event() for _ in range(4))

    class PausingGraph:
        def get_state(self, config):
            return SimpleNamespace(values={}, tasks=[], next=["await_browser"])

        def stream(self, incoming, config, stream_mode):
            yield {"status": "RUNNING"}

    @contextmanager
    def delayed_graph(*args, **kwargs):
        try:
            yield PausingGraph(), None
        finally:
            closing.set()
            assert allow_close.wait(5), "测试未允许关闭图资源"

    original_run = worker.run

    def delayed_return(run_id):
        original_run(run_id)
        returning.set()
        assert allow_return.wait(5), "测试未允许工作线程返回"

    monkeypatch.setattr("app.api.worker.open_graph", delayed_graph)
    monkeypatch.setattr(worker, "run", delayed_return)
    try:
        worker.submit("r")
        assert closing.wait(5)
        assert runs.get("r")["status"] == "RUNNING"
        with pytest.raises(InvalidTransitionError, match="正在运行"):
            worker.submit("r")
        allow_close.set()
        assert returning.wait(5)
        assert runs.get("r")["status"] == "PAUSED"
        # 线程还未返回，但图资源已经关闭，用户此时恢复必须成功。
        worker.submit("r")
        assert runs.get("r")["status"] == "QUEUED"
        with pytest.raises(InvalidTransitionError, match="正在运行"):
            worker.submit("r")
    finally:
        allow_close.set()
        allow_return.set()
        worker.close()
        engine.dispose()
