"""对已经启动的本机服务验收 Mock 全流程，供本地和容器共用。"""

import json
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import URLError
from app.llm.client import NoRedirect


class LocalDemoClient:
    """只连接回环地址，拒绝重定向；测试令牌不能转发给其他主机。"""

    def __init__(self, base_url: str, token: str):
        parts = urlsplit(base_url)
        if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}
                or parts.username or parts.password or parts.path not in {"", "/"}
                or parts.query or parts.fragment):
            raise ValueError("验收客户端只允许本机 HTTP 根地址")
        self.base_url, self.token = base_url.rstrip("/"), token
        self.opener = build_opener(NoRedirect)

    def call(self, path: str, body=None):
        """接口路径由脚本固定，不接收外部提供的任意 URL。"""
        request = Request(self.base_url + path, data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json", "X-JobPilot-Token": self.token})
        with self.opener.open(request, timeout=5) as response:
            return json.load(response)

    def wait_ready(self, seconds=60):
        """容器重启后只轮询健康检查，不重复创建任务或执行动作。"""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if self.call("/health")["status"] == "ok":
                    return
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.2)
        raise AssertionError("本机服务未在预期时间内就绪")

    def wait_state(self, run_id: str):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = self.call("/api/runs/" + run_id)
            if state["status"] == "FAILED":
                raise AssertionError("Mock 验收任务失败，请检查服务日志")
            if state["status"] in {"PAUSED", "COMPLETED"}:
                return state
            time.sleep(0.1)
        raise AssertionError("Mock 验收任务未按预期暂停或完成")

    def start_paused(self) -> str:
        """始终使用公开虚构资料、Mock 来源和离线模型。"""
        profile = self.call("/api/candidate-example")
        run_id = self.call("/api/runs", {"candidate": profile, "source": "mock", "mode": "offline"})["id"]
        state = self.wait_state(run_id)
        assert state["status"] == "PAUSED" and state["interrupts"][0]["kind"] == "approval"
        return run_id

    def complete(self, run_id: str):
        """模拟批准一条、拒绝其余，并验证跟踪器没有记录真实已联系。"""
        decisions = 0
        for _ in range(60):
            state = self.wait_state(run_id)
            actions = self.call("/api/actions?run_id=" + run_id)
            if state["status"] == "COMPLETED":
                assert decisions > 0
                assert sum(action["status"] == "SUCCEEDED" for action in actions) == 1
                assert all(action["status"] in {"SUCCEEDED", "REJECTED"} for action in actions)
                applications = self.call("/api/applications")
                assert applications and all(row["status"] != "CONTACTED" for row in applications)
                return {"run_id": run_id, "jobs": len(state["snapshot"]["jobs"]), "decisions": decisions}
            assert state["interrupts"][0]["kind"] == "approval"
            pending = [action for action in actions if action["status"] == "PENDING"]
            assert len(pending) == 1 and pending[0]["payload"]["simulated"] is True
            action = pending[0]
            self.call(f"/api/actions/{action['id']}/decision", {"digest": action["digest"], "approve": decisions == 0})
            self.call(f"/api/runs/{run_id}/resume", {})
            decisions += 1
        raise AssertionError("验收循环超过上限")
