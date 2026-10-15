"""普通浏览器与本机任务之间的只读队列，不接收简历、Cookie 或任意脚本。"""

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID
from typing import Annotated, Literal

from pydantic import Field, model_validator
from app.models.base import DomainModel
from app.exceptions import InvalidTransitionError


class BossPageDetail(DomainModel):
    """扩展只回传可见岗位文字；岗位身份由后端从受限地址中重新生成。"""

    url: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=1000)
    description: str = Field(min_length=1, max_length=30000)
    city: str = Field(default="", max_length=1000)
    salary: str = Field(default="", max_length=1000)
    extra: str = Field(default="", max_length=3000)
    closed_reason: str = Field(default="", max_length=200)
    contact_button: str = Field(default="",max_length=100)
    contact_count: int = Field(default=0,ge=0,le=30)


class ScrollSample(DomainModel):
    """岗位列表祖先的滚动尺寸；不包含正文、账号或导航参数。"""

    element: str = Field(max_length=120)
    top: int
    height: int = Field(ge=0)
    viewport: int = Field(ge=0)
    overflow: str = Field(max_length=30)


class SearchPageSample(DomainModel):
    """只保存公开岗位编号，供验证续页是否真的带来新岗位。"""

    city: str = Field(default="", max_length=40)
    query_index: int = Field(ge=0,le=4)
    page_number: int = Field(ge=1,le=20)
    ids: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")]] = Field(max_length=200)
    continuation: Literal["available","scroll","end","unknown"]
    scroll: list[ScrollSample] = Field(default_factory=list,max_length=12)


class BridgeDiagnostic(DomainModel):
    """保留读取失败的类别和标签页身份，不记录账号、完整 URL 或页面正文。"""

    outcome: str = Field(max_length=80)
    tab_id: int
    elapsed_ms: int = Field(ge=0)
    error_type: str = Field(default="", max_length=80)
    observations: int = Field(default=0, ge=0)
    body_length: int = Field(default=0, ge=0)
    listing_count: int = Field(default=0, ge=0)
    page_path: str = Field(default="", max_length=300, pattern=r"^[^?#]*$")


class BridgeUpdate(DomainModel):
    """每读完一页或一个岗位立即保存；刷新面板不会丢掉已收到的岗位。"""

    job: BossPageDetail | None = None
    skipped_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,200}$")
    pages: int = Field(default=0, ge=0, le=10000, strict=True)
    warning: str = Field(default="", max_length=300)
    paused: bool = Field(default=False, strict=True)
    finished: bool = Field(default=False, strict=True)
    complete: bool = Field(default=False, strict=True)
    limit_reached: bool = Field(default=False, strict=True)
    diagnostic: BridgeDiagnostic | None = None
    page_sample: SearchPageSample | None = None

    @model_validator(mode="after")
    def consistent_update(self):
        """一次回传不能既暂停又结束，也不能让同一岗位既成功又跳过。"""
        if self.paused and self.finished or self.job and self.skipped_id or self.complete and not self.finished:
            raise ValueError("回传状态相互冲突")
        return self


class BossBridge:
    """SQLite 保存采集进度；短租约防止两个扩展面板同时读取同一任务。"""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "boss-bridge.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS connection (id INTEGER PRIMARY KEY, digest TEXT, created REAL, seen REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    @contextmanager
    def connection(self):
        """每次操作使用独立事务，API 线程与工作线程不会覆盖彼此的更新。"""
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def key(run_id):
        return str(UUID(run_id))

    @staticmethod
    def save(db, value):
        db.execute("INSERT OR REPLACE INTO requests VALUES (?, ?)",
                   (value["id"], json.dumps(value, ensure_ascii=False)))

    def pair(self):
        """连接凭据只允许领取 BOSS 搜索和回传岗位，不能访问主 API 或模型设置。"""
        token = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO connection VALUES (1, ?, ?, 0)",
                       (hashlib.sha256(token.encode()).hexdigest(), time.time()))
        return token

    def authenticate(self, token):
        with self.connection() as db:
            row = db.execute("SELECT digest, created FROM connection WHERE id=1").fetchone()
            if not row or time.time() - row[1] > 86400 or not secrets.compare_digest(
                    row[0], hashlib.sha256(token.encode()).hexdigest()):
                return False
            db.execute("UPDATE connection SET seen=? WHERE id=1", (time.time(),))
        return True

    def status(self):
        with self.connection() as db:
            row = db.execute("SELECT created, seen FROM connection WHERE id=1").fetchone()
        return {"connected": bool(row and time.time() - row[0] < 86400 and time.time() - row[1] < 30)}

    def ensure(self, run_id, queries, limit, cities):
        from app.adapters.cities import boss_search_cities
        search_cities = boss_search_cities(cities)
        run_id = self.key(run_id)
        with self.connection() as db:
            row = db.execute("SELECT body FROM requests WHERE id=?", (run_id,)).fetchone()
            if row:
                value = json.loads(row[0])
                if limit > value["limit"] and value["status"] == "ready":
                    # 只能由恢复中的工作流增加额度；旧岗位和尝试编号保持不动。
                    value.update(limit=limit, status="waiting", owner="", lease=0, complete=False,
                                 limit_reached=False, warnings=[], message="等待继续搜索")
                value["search_cities"] = search_cities
                self.save(db, value)
                return value
            keywords = list(dict.fromkeys(query.strip()[:80] for query in queries if query.strip()))[:5]
            if not keywords:
                raise InvalidTransitionError("请填写想找的岗位，再开始 BOSS 搜索")
            value = dict(id=run_id, queries=keywords, cities=cities, search_cities=search_cities, limit_reached=False,
                         limit=limit, status="waiting", owner="", lease=0, jobs=[], attempted=[],
                         pages=0, warnings=[], complete=False, message="等待 BOSS 助手读取岗位")
            self.save(db, value)
            return value

    def get(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT body FROM requests WHERE id=?", (self.key(run_id),)).fetchone()
        return json.loads(row[0]) if row else None

    def claim(self, owner):
        """暂停的任务必须由用户继续；租约过期只恢复已授权的只读搜索。"""
        with self.connection() as db:
            for row in db.execute("SELECT body FROM requests ORDER BY rowid"):
                value = json.loads(row[0])
                if value["status"] == "waiting" or value["status"] == "reading" and (
                        value["owner"] == owner or value["lease"] < time.time()):
                    from app.adapters.cities import boss_search_cities
                    value["search_cities"] = boss_search_cities(value.get("cities", []))
                    value.update(status="reading", owner=owner, lease=time.time() + 60)
                    self.save(db, value)
                    return value
        return None

    def update(self, run_id, owner, update: BridgeUpdate):
        from app.adapters.boss import job_from_extension
        # 先校验正文，失败时整个操作不落盘，也不消费岗位额度。
        job = job_from_extension(update.job) if update.job else None
        with self.connection() as db:
            row = db.execute("SELECT body FROM requests WHERE id=?", (self.key(run_id),)).fetchone()
            if not row:
                raise KeyError(run_id)
            value = json.loads(row[0])
            if value["status"] != "reading" or value["owner"] != owner or value["lease"] < time.time():
                raise InvalidTransitionError("本次读取已暂停或由另一面板接手，请重新连接")
            attempted_id = job.source_job_id if job else update.skipped_id
            if attempted_id and attempted_id not in value["attempted"]:
                if len(value["attempted"]) >= value["limit"]:
                    raise InvalidTransitionError("已达到本次岗位读取上限")
                value["attempted"].append(attempted_id)
                if job:
                    value["jobs"].append(job.model_dump(mode="json"))
            value["pages"] = max(value["pages"], update.pages)
            if update.warning and update.warning not in value["warnings"]:
                value["warnings"] = [*value["warnings"], update.warning][-100:]
            value.update(lease=time.time() + 60, message="浏览器助手正在读取岗位")
            if update.diagnostic:
                value["diagnostic"] = update.diagnostic.model_dump()
            if update.page_sample:
                value["page_samples"] = [*value.get("page_samples",[]),update.page_sample.model_dump()][-100:]
            if update.job:
                value.setdefault("contact_checks",{})[job.source_job_id] = dict(
                    button=update.job.contact_button,count=update.job.contact_count)
            if update.paused:
                value.update(status="paused", message=update.warning or "请在 BOSS 页面完成登录或验证，然后继续")
            elif update.finished:
                value.update(status="ready", complete=update.complete and not value["warnings"],
                             limit_reached=update.limit_reached, message="岗位已收到，正在匹配")
            self.save(db, value)
        return value

    def resume(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT body FROM requests WHERE id=?", (self.key(run_id),)).fetchone()
            if row:
                value = json.loads(row[0])
                if value["status"] == "paused":
                    value.update(status="waiting", owner="", lease=0, message="等待继续读取")
                    self.save(db, value)

    def ready_ids(self):
        with self.connection() as db:
            values = [json.loads(row[0]) for row in db.execute("SELECT body FROM requests")]
        return [value["id"] for value in values if value["status"] == "ready"]

    def paused_task(self):
        """新面板也能找到暂停入口，不依赖已关闭页面的 sessionStorage。"""
        with self.connection() as db:
            for row in db.execute("SELECT body FROM requests ORDER BY rowid"):
                value = json.loads(row[0])
                if value["status"] == "paused":
                    return value
        return None
