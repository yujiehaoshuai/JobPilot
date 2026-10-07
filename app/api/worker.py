"""单工作线程执行同步图，HTTP 请求不等待浏览器或模型返回。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import perf_counter
from app.observability import EventLog
from langgraph.types import Command
from app.exceptions import JobPilotError, InvalidTransitionError
from app.workflow.runtime import open_graph, graph_config


class WorkflowWorker:
    """内存线程只负责调度；状态、输入和恢复位置都存放在数据库。"""

    def __init__(self, runs, data_dir, database_url):
        self.runs, self.data_dir, self.database_url = runs, data_dir, database_url
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jobpilot")
        self.futures = {}
        self.lock = Lock()
        self.events = EventLog(data_dir / "events.jsonl")
        self.metrics = {"runs_started": 0, "runs_completed": 0, "runs_paused": 0, "runs_failed": 0}

    def submit(self, run_id):
        with self.lock:
            self.futures = {key: value for key, value in self.futures.items() if not value.done()}
            if len(self.futures) >= 20:
                raise InvalidTransitionError("任务队列已满，请等待现有任务暂停或结束")
            if run_id in self.futures and not self.futures[run_id].done():
                raise InvalidTransitionError("任务正在运行，请勿重复恢复")
            # 返回 202 前先持久化排队状态。否则客户端可能把旧 PAUSED 当成新一轮结果。
            previous = self.runs.get(run_id)
            self.runs.update(run_id, "QUEUED", error=None)
            try:
                self.futures[run_id] = self.pool.submit(self.run, run_id)
            except RuntimeError:
                # 服务关闭期间可能拒绝新任务；恢复原状态，避免留下永远排队的记录。
                self.runs.update(run_id, previous["status"], error=previous.get("error"))
                raise InvalidTransitionError("工作线程已停止，请重新启动服务后恢复") from None

    def run(self, run_id):
        """暂停和失败均保存可恢复状态；不在服务重启时擅自重放发送。"""
        data = self.runs.get(run_id)
        start = perf_counter()
        self.metrics["runs_started"] += 1
        self.events.record("run_started", run_id=run_id, source=data["source"], mode=data["mode"])
        self.runs.update(run_id, "RUNNING", error=None)
        try:
            with open_graph(self.data_dir, source=data["source"], mode=data["mode"],
                            database_url=self.database_url, transport=data.get("transport", "direct"),
                            search_limit=data["input"].get("search_limit")) as (graph, actions):
                config = graph_config(run_id)
                state = graph.get_state(config)
                if not state.values:
                    incoming = data["input"]
                else:
                    incoming = Command(resume=True) if any(t.interrupts for t in state.tasks) else None
                for snapshot in graph.stream(incoming, config, stream_mode="values"):
                    # __interrupt__ 包含 SDK 对象，不直接放进业务 JSON。
                    serializable = {key: value for key, value in snapshot.items() if key != "__interrupt__"}
                    self.runs.update(run_id, "RUNNING", snapshot=serializable)
                state = graph.get_state(config)
                interruptions = [i.value for t in state.tasks for i in t.interrupts]
                status = "PAUSED" if state.next else "COMPLETED"
                self.metrics["runs_paused" if state.next else "runs_completed"] += 1
                self.events.record("run_finished", run_id=run_id, status=status,
                                   elapsed_ms=(perf_counter() - start) * 1000)
                self.runs.update(run_id, status, snapshot=state.values, interrupts=interruptions,
                                 next=list(state.next), error=None)
        except Exception as exc:
            self.metrics["runs_failed"] += 1
            self.events.record("run_failed", run_id=run_id, error_type=type(exc).__name__,
                               elapsed_ms=(perf_counter() - start) * 1000)
            # 第三方异常可能含 URL、SQL 参数或请求正文，只记录类型。
            message = str(exc) if isinstance(exc, JobPilotError) else type(exc).__name__
            self.runs.update(run_id, "FAILED", error=message)

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=False)
        self.events.close()
