"""统一创建平台资源，工作流与工具服务无需了解选择器。"""

from contextlib import contextmanager
from app.config import PROJECT_ROOT, load_settings
from app.adapters.mock.adapter import MockJobAdapter
from app.adapters.boss import BossAdapter
from app.adapters.nowcoder import NowcoderAdapter
from app.adapters.shixiseng import ShixisengAdapter
from app.adapters.http_reader import PublicPageReader
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS, NOWCODER, SHIXISENG
from app.runtime_config import setting

PLATFORMS = {"boss": (BOSS, BossAdapter), "nowcoder": (NOWCODER, NowcoderAdapter),
             "shixiseng": (SHIXISENG, ShixisengAdapter)}


@contextmanager
def open_adapter(source: str, *, limit: int | None = None):
    """上下文退出时关闭读取资源；实习僧公开 HTML 不需要启动浏览器。"""
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 50):
        raise ValueError("岗位数量上限必须为 1 到 50 的整数")
    if source == "mock":
        yield MockJobAdapter(load_settings().jobs_path)
    elif source == "shixiseng":
        with PublicPageReader(SHIXISENG) as session:
            yield ShixisengAdapter(session, limit=limit or 5)
    elif source in PLATFORMS:
        site, adapter_type = PLATFORMS[source]
        with BrowserSession(site, PROJECT_ROOT / "profiles" / source,
                            channel=setting("BROWSER_CHANNEL", "msedge") or None,
                            headless=setting("BROWSER_HEADLESS", "false").lower() == "true") as session:
            yield adapter_type(session, limit=limit or 10)
    else:
        raise ValueError("未注册的岗位来源")
