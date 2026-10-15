"""BOSS 助手的连接与采集 API：独立凭据不能访问简历或批准操作。"""

import re
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from app.browser.bridge import BossBridge, BridgeUpdate
from app.exceptions import InvalidTransitionError


def install_boss_routes(app, data_dir, runs, worker, auth):
    """主页面发起连接，扩展凭独立凭据领取只读任务；不开放通配跨域权限。"""
    bridge = BossBridge(data_dir)
    app.state.boss_bridge = bridge

    def bridge_auth(request: Request):
        origin = request.headers.get("origin")
        if origin and not re.fullmatch(r"chrome-extension://[a-z0-9]+", origin):
            raise HTTPException(403, "只接受已连接的浏览器助手")
        if not bridge.authenticate(request.headers.get("X-JobPilot-Bridge", "")):
            raise HTTPException(401, "助手连接已失效，请回 JobPilot 点击连接 BOSS 助手")
        try:
            return str(UUID(request.headers.get("X-JobPilot-Reader", "")))
        except ValueError:
            raise HTTPException(422, "助手编号无效，请重新打开助手") from None

    def continue_ready():
        # 只自动继续正在等待浏览器的只读任务；模型失败和审批仍由原有流程处理。
        for run_id in bridge.ready_ids():
            run = runs.get(run_id)
            # 兼容旧版本把“再次中断但 next 为空”误标为完成的记录；中断仍在，不能丢任务。
            if (run["status"] in {"PAUSED", "COMPLETED"} and run["input"].get("analysis_only")
                    and any(item.get("kind") == "browser" for item in run.get("interrupts", []))):
                try:
                    worker.submit(run_id)
                except InvalidTransitionError:
                    pass  # 已经排队或队列暂满；下一次只读轮询再检查。

    @app.post("/api/boss/connect", dependencies=auth)
    def connect():
        return {"connection": bridge.pair()}

    @app.get("/api/boss/status", dependencies=auth)
    def status(run_id: UUID | None = None):
        value = bridge.get(str(run_id)) if run_id else None
        return {**bridge.status(), "task": public_task(value), "diagnostic": (value or {}).get("diagnostic")}

    @app.get("/api/boss/next")
    def next_task(owner: str = Depends(bridge_auth)):
        continue_ready()
        value = bridge.claim(owner)
        return {"task": public_task(value), "paused": public_task(bridge.paused_task()) if value is None else None}

    @app.post("/api/boss/tasks/{run_id}")
    def update(run_id: UUID, body: BridgeUpdate, owner: str = Depends(bridge_auth)):
        try:
            value = bridge.update(str(run_id), owner, body)
        except ValueError:
            raise HTTPException(422, "岗位内容或地址不符合 BOSS 读取格式") from None
        continue_ready()
        return {"task": public_task(value)}

    @app.post("/api/boss/tasks/{run_id}/continue")
    def resume_collection(run_id: UUID, owner: str = Depends(bridge_auth)):
        bridge.resume(str(run_id))
        return {"resumed": True}

    return bridge_auth


def public_task(value):
    """浏览器只需要搜索条件和已读编号，不发送候选人资料和模型输出。"""
    if value is None:
        return None
    return {key: value.get(key) for key in ("id", "queries", "cities", "search_cities", "limit", "status", "attempted", "pages", "message")}
