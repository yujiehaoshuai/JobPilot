"""让工作线程暂不开始，稳定复现恢复请求返回后仍显示旧暂停状态的问题。"""

from threading import Event
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
