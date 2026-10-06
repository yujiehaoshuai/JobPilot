"""复用专属浏览器资料，保留正常登录；不绕过任何验证机制。"""

from pathlib import Path
import time
from filelock import FileLock, Timeout
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError
from app.browser.selectors import CHALLENGE_SELECTORS, CHALLENGE_TITLES, SiteSpec
from app.exceptions import BrowserPausedError, JobParseError


class BrowserSession:
    """一个任务使用一个会话；同一资料目录不能被多个进程同时打开。"""

    def __init__(self, site: SiteSpec, profile: Path, *, headless: bool = False,
                 channel: str | None = "msedge", timeout_ms: int = 15000) -> None:
        self.site, self.profile = site, Path(profile)
        self.headless, self.channel, self.timeout_ms = headless, channel, timeout_ms
        self.driver = self.context = self.page = None
        self.profile_lock = None
        self.last_navigation = 0.0

    def __enter__(self):
        self.profile.mkdir(parents=True, exist_ok=True)
        self.profile_lock = FileLock(str(self.profile / "jobpilot-session.lock"))
        try:
            self.profile_lock.acquire(timeout=0)
        except Timeout:
            raise BrowserPausedError("此平台浏览器资料正在使用，请先关闭登录窗口或其他任务") from None
        try:
            self.driver = sync_playwright().start()
            self.context = self.driver.chromium.launch_persistent_context(
                str(self.profile), headless=self.headless, channel=self.channel,
                # 显式启用 Chromium 沙箱，避免 Playwright 默认关闭沙箱。
                accept_downloads=False, chromium_sandbox=True,
            )
            self.context.set_default_timeout(self.timeout_ms)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            return self
        except Exception:
            try:
                if self.driver:
                    self.driver.stop()
            finally:
                self.profile_lock.release()
            raise

    def __exit__(self, *args):
        """用户提前关窗也释放驱动和锁；其他关闭错误仍交给调用方处理。"""
        try:
            if self.context:
                try:
                    self.context.close()
                except PlaywrightError as exc:
                    # Playwright 的公开异常基类用于识别已经关闭的窗口。
                    # 只忽略此情况，不能把真正的驱动故障也当成成功。
                    if "Target page, context or browser has been closed" not in str(exc):
                        raise
        finally:
            try:
                if self.driver:
                    self.driver.stop()
            finally:
                if self.profile_lock:
                    self.profile_lock.release()

    def validate_url(self, url: str) -> None:
        """只允许此平台的 HTTPS 页面，防止岗位链接跳到未知站点。"""
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.hostname not in self.site.hosts
                or parts.username or parts.password or parts.port not in {None, 443}):
            raise JobParseError("岗位链接不是所选平台的可信 HTTPS 地址")

    def ensure_ready(self) -> None:
        """发现登录、验证或站外跳转时立即暂停，保留持久登录资料。"""
        if self.page.is_closed():
            raise BrowserPausedError("浏览器窗口已关闭，请重新打开登录窗口后再验证")
        if self.page.url == "about:blank":
            raise BrowserPausedError("页面已变为空白页，无法确认登录状态；请人工检查，不自动重试或绕过验证")
        self.validate_url(self.page.url)
        if any(word in self.page.title() for word in CHALLENGE_TITLES):
            raise BrowserPausedError("请手动登录或完成网站验证，然后恢复任务")
        # 同一页面可能同时保留隐藏模板和可见弹窗，不能只检查第一个元素。
        if any(self.page.locator(f":is({selector}):visible").count() for selector in CHALLENGE_SELECTORS):
            raise BrowserPausedError("检测到登录或验证码界面，请人工处理后恢复")

    def read(self, url: str, ready_selector: str) -> str:
        """只导航并读取 DOM；选择器超时不会被误认为搜索结果为空。"""
        self.validate_url(url)
        # 当前会话的页面导航至少间隔一秒，不因失败或空结果快速刷请求。
        remaining = 1.0 - (time.monotonic() - self.last_navigation)
        if remaining > 0:
            time.sleep(remaining)
        self.last_navigation = time.monotonic()
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        if response and response.status in {401, 403, 429}:
            raise BrowserPausedError("平台拒绝访问或要求验证，请稍后人工检查")
        self.ensure_ready()
        try:
            # SPA 会先插入隐藏的空结果模板，再异步填充岗位。
            # 等真正可见的结果，避免把模板或导航栏当成加载完成。
            self.page.locator(f":is({ready_selector}):visible").first.wait_for(
                state="visible", timeout=self.timeout_ms)
        except PlaywrightTimeout:
            self.ensure_ready()
            raise JobParseError("页面加载超时或选择器已变化，请检查平台页面") from None
        self.ensure_ready()
        return self.page.content()
