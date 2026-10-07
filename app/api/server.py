"""本地 API：候选人输入、任务管理、审批与有限时长的 SSE 状态流。"""

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field
from sqlalchemy import text
from app.config import PROJECT_ROOT
from app.models.base import DomainModel
from app.models.candidate import CandidateProfile
from app.runtime_config import agent_database_url, setting
from app.storage.relational import database_engine, RunStore, RelationalActionStore, RelationalTracker
from app.api.worker import WorkflowWorker
from app.exceptions import JobPilotError
from app.reliability import TokenBucket
from app.services.action_service import resolve_after_review
from app.models.resume import ResumeProfileRequest
from app.services.resume_service import extract_resume, build_candidate, MAX_UPLOAD_BYTES


class StartRun(DomainModel):
    """提交资料时立即使用领域模型校验，禁止随意传入文件路径或代码。"""

    candidate: CandidateProfile
    source: Literal["mock", "boss", "nowcoder", "shixiseng"] = "mock"
    mode: Literal["offline", "live"] = "offline"
    transport: Literal["direct", "mcp"] = "direct"
    queries: list[str] = Field(default_factory=list, max_length=5)
    analysis_only: bool = Field(default=False, strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=40, strict=True)


class Decision(DomainModel):
    """每次审批都绑定界面展示的摘要；API 不提供批量默认批准。"""

    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approve: bool = Field(strict=True)


class RecoveryDecision(DomainModel):
    """用户已在平台核对事实；这里只保存核查结果，不触发发送。"""

    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    sent: bool = Field(strict=True)
    note: str = Field(min_length=5, max_length=1000)


def local_token(data_dir: Path) -> str:
    """未配置令牌时生成本机专用令牌，保存在被 Git 忽略的 data 下。"""
    configured = setting("JOBPILOT_API_TOKEN")
    if configured:
        return configured
    path = data_dir / "api-token.txt"
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    return path.read_text("utf-8").strip()


def create_app(data_dir: Path | None = None, database_url: str | None = None, token: str | None = None):
    """测试传入临时路径；生产入口使用 data/agent 与环境配置。"""
    data_dir = Path(data_dir or PROJECT_ROOT / "data/agent")
    data_dir.mkdir(parents=True, exist_ok=True)
    url = database_url or agent_database_url(data_dir)
    api_token = token or local_token(data_dir)
    if url.startswith("sqlite:"):
        from app.db_cli import upgrade
        upgrade(url)
    engine = database_engine(url)
    runs, actions, tracker = RunStore(engine), RelationalActionStore(engine), RelationalTracker(engine)
    worker = WorkflowWorker(runs, data_dir, url)
    limiter = TokenBucket()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(worker.close)
        engine.dispose()

    app = FastAPI(title="JobPilot", version="0.11.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.worker, app.state.runs = worker, runs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    async def authenticated(request: Request):
        if not secrets.compare_digest(request.headers.get("X-JobPilot-Token", ""), api_token):
            raise HTTPException(401, "请提供本机访问令牌")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "不接受跨来源操作")
        if not limiter.allow():
            raise HTTPException(429, "请求过于频繁，请稍后重试", headers={"Retry-After": "1"})

    auth = [Depends(authenticated)]

    @app.exception_handler(JobPilotError)
    async def business_error(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={"detail": "记录不存在"})

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        length = request.headers.get("content-length", "0")
        if not length.isdigit():
            return JSONResponse(status_code=400, content={"detail": "请求长度无效"})
        if int(length) > 1_000_000:
            return JSONResponse(status_code=413, content={"detail": "请求资料过大"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get("/health")
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "real_sending": "awaiting_platform_validation"}

    @app.get("/api/candidate-example", dependencies=auth)
    def example():
        return json.loads((PROJECT_ROOT / "fixtures/candidate.example.json").read_text("utf-8-sig"))

    @app.post("/api/runs", status_code=202, dependencies=auth)
    def start(body: StartRun):
        if body.mode == "live":
            from app.llm.client import create_llm
            create_llm("live")  # 仅检查配置，不发网络请求；失败时不创建任务。
        run_id = str(uuid4())
        incoming = {"run_id": run_id, **body.model_dump(mode="json")}
        runs.create(run_id, {"source": body.source, "mode": body.mode, "transport": body.transport, "input": incoming,
                             "snapshot": {}, "interrupts": [], "error": None})
        worker.submit(run_id)
        return {"id": run_id}

    @app.get("/api/runs", dependencies=auth)
    def list_runs():
        return runs.list()

    @app.post("/api/resume/extract", dependencies=auth)
    async def resume_text(request: Request, format: Literal["txt", "docx"]):
        """逐块限制上传大小，不依赖客户端声明长度；文件仅在内存处理。"""
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "简历文件不能超过 1 MB")
            data.extend(chunk)
        try:
            content = await asyncio.to_thread(extract_resume, bytes(data), format)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"text": content, "notice": "请核对正文并逐条确认技能和程度；未读取图片、页眉页脚或批注。"}

    @app.post("/api/resume/profile", dependencies=auth, response_model=CandidateProfile)
    def resume_profile(body: ResumeProfileRequest):
        """返回可编辑的新资料，不保存原始文件，不自动创建求职任务。"""
        try:
            return build_candidate(body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/runs/{run_id}", dependencies=auth)
    def get_run(run_id: str):
        return runs.get(run_id)

    @app.post("/api/runs/{run_id}/resume", status_code=202, dependencies=auth)
    def resume(run_id: str):
        value = runs.get(run_id)
        if value["status"] == "COMPLETED":
            raise HTTPException(409, "任务已完成")
        if any(action.status == "PENDING" for action in actions.list(run_id)):
            raise HTTPException(409, "请先处理当前审批")
        worker.submit(run_id)
        return {"id": run_id}

    @app.get("/api/actions", dependencies=auth)
    def list_actions(run_id: str | None = None):
        return actions.list(run_id)

    @app.post("/api/actions/{action_id}/decision", dependencies=auth)
    def decide(action_id: str, body: Decision):
        return actions.decide(action_id, body.digest, body.approve, "authenticated-local-user")

    @app.post("/api/actions/{action_id}/resolve", dependencies=auth)
    def resolve(action_id: str, body: RecoveryDecision):
        return resolve_after_review(actions, data_dir, action_id, body.digest, body.sent,
                                    body.note, "authenticated-local-user")

    @app.get("/api/applications", dependencies=auth)
    def applications():
        return tracker.list_applications()

    @app.get("/api/metrics", dependencies=auth)
    def metrics():
        return {"counters": dict(worker.metrics), "scope": "当前服务进程；持久历史见任务列表和事件日志"}

    @app.get("/api/evaluation/latest", dependencies=auth)
    def evaluation():
        path = PROJECT_ROOT / "data/evaluations/latest.json"
        if not path.exists():
            raise HTTPException(404, "尚未运行评估")
        return json.loads(path.read_text("utf-8"))

    @app.get("/api/runs/{run_id}/events", dependencies=auth)
    async def events(run_id: str, request: Request):
        runs.get(run_id)
        async def stream():
            previous = None
            # 连接定期关闭，客户端可重新连接读取最新快照，不占用永久连接。
            for _ in range(120):
                if await request.is_disconnected():
                    return
                value = await asyncio.to_thread(runs.get, run_id)
                current = json.dumps(value, ensure_ascii=False)
                if current != previous:
                    yield "event: state\ndata: " + current + "\n\n"
                    previous = current
                if value["status"] in {"PAUSED", "FAILED", "COMPLETED"}:
                    return
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream")

    # 页面和 API 同源，不需要跨域配置，也不把访问令牌嵌入网页。
    static_dir = PROJECT_ROOT / "app/web"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(static_dir / "index.html")

    @app.get("/docs", include_in_schema=False)
    def api_documentation():
        return FileResponse(static_dir / "api.html")

    return app
