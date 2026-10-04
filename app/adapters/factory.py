"""统一创建平台资源，工作流与工具服务无需了解选择器。"""

from contextlib import contextmanager
from app.config import PROJECT_ROOT, load_settings
from app.adapters.mock.adapter import MockJobAdapter
from app.adapters.boss import BossAdapter
from app.adapters.nowcoder import NowcoderAdapter
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS, NOWCODER
from app.runtime_config import setting

PLATFORMS = {"boss": (BOSS, BossAdapter), "nowcoder": (NOWCODER, NowcoderAdapter)}


@contextmanager
def open_adapter(source: str):
    """浏览器由调用方负责关闭；所有平台共用同一接口。"""
    if source == "mock":
        yield MockJobAdapter(load_settings().jobs_path)
    elif source in PLATFORMS:
        site, adapter_type = PLATFORMS[source]
        with BrowserSession(site, PROJECT_ROOT / "profiles" / source,
                            channel=setting("BROWSER_CHANNEL", "msedge") or None,
                            headless=setting("BROWSER_HEADLESS", "false").lower() == "true") as session:
            yield adapter_type(session)
    else:
        raise ValueError("未注册的岗位来源")
