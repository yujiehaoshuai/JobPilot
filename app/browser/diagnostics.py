"""按页面身份记录只读导航和生命周期；不改变启动参数或网页行为。"""

from datetime import UTC, datetime
from importlib.metadata import version
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout
from app.browser.selectors import CHALLENGE_SELECTORS, CHALLENGE_TITLES


def diagnostic_url(value: str) -> str:
    """对照实验仅接收正常 HTTPS 地址，禁止文件、脚本及带账号密码的 URL。"""
    try:
        parts = urlsplit(value)
        if (parts.scheme == "https" and parts.hostname and not parts.username
                and not parts.password and parts.port in {None, 443}):
            return value
    except ValueError:
        pass
    raise ValueError("诊断 URL 必须是无账号密码的 HTTPS 地址，端口为默认值或 443")


def observed_url(value: str | None) -> str | None:
    """保留定位所需的协议、主机和路径；查询参数、片段和账号密码不写报告。"""
    if value is None:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme in {"http", "https", "chrome", "edge", "chrome-error"}:
            host = parts.hostname or ""
            if ":" in host:
                host = f"[{host}]"
            if parts.port is not None:
                host += f":{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, "", ""))[:2048]
        if parts.scheme == "about":
            return "about:" + parts.path
        return f"{parts.scheme or 'unknown'}:<redacted>"
    except ValueError:
        return "<invalid-url>"


def target_kind(url: str, site) -> str:
    """保留旧版类别摘要；具体页面身份和脱敏 URL 由事件字段提供。"""
    if observed_url(url) == "about:blank":
        return "blank"
    try:
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname in site.hosts:
            return "platform_page"
    except ValueError:
        pass
    return "other_page"


class NavigationObserver:
    """保存 Page 对象与本地编号的对应关系，不用 URL 猜测页面身份。"""

    def __init__(self, session, url):
        self.session, self.context = session, session.context
        self.started = monotonic()
        self.pages, self.registered = {}, set()
        self.pending_cdp, self.clients, self.listeners = [], [], []
        self.target_pages, self.target_urls = {}, {}
        self.context_id = None
        self.context_closed = self.disconnected = False
        self.crashed_pages = set()
        self.navigation_started = False
        self.first_blank = None
        self.report = {
            "schema_version": 2, "source": session.site.source, "time": datetime.now(UTC).isoformat(),
            "diagnostic_url": observed_url(url), "playwright_version": version("playwright"),
            "launch": {"channel": session.channel, "headless": session.headless, "profile": str(session.profile)},
            "outcome": "observing", "authentication_verified": False,
            "events": [], "cdp_capabilities": [], "dropped_events": 0,
            "url_policy": "保留协议、主机和路径；移除查询参数、片段和账号密码；其他协议内容隐藏",
        }

    def page_id(self, page):
        if page not in self.pages:
            self.pages[page] = f"page-{len(self.pages) + 1}"
        return self.pages[page]

    def snapshot(self):
        """每次事件都读取此刻的 context.pages；已关闭页面另保存在最终登记表中。"""
        return [{"page_id": self.page_id(page), "url": observed_url(page.url), "is_closed": page.is_closed()}
                for page in self.context.pages]

    def listen(self, emitter, event, handler):
        emitter.on(event, handler)
        self.listeners.append((emitter, event, handler))

    def record(self, kind, page=None, *, target_url=None, is_main_frame=None, blank_candidate=False, **extra):
        """统一事件格式；浏览器级事件或未知关联使用 null，不能假装属于主页面。"""
        event = {"kind": kind, "page_id": self.page_id(page) if page is not None else None,
                 "current_url": observed_url(page.url) if page is not None else None,
                 "target_url": observed_url(target_url), "elapsed_ms": round((monotonic() - self.started) * 1000),
                 "is_main_frame": is_main_frame, "pages": self.snapshot(), **extra}
        if self.navigation_started and blank_candidate and observed_url(target_url) == "about:blank":
            if self.first_blank is None:
                self.first_blank = monotonic()
                self.report["first_blank"] = {key: event[key] for key in ("page_id", "kind", "elapsed_ms")}
                self.report["first_blank"]["target_id"] = event.get("target_id")
        if len(self.report["events"]) < 500:
            self.report["events"].append(event)
        else:
            self.report["dropped_events"] += 1
        return event

    def register(self, page, kind="page.created"):
        """事件回调仅挂监听和排队；CDP 请求留在观察循环，避免嵌套协议调用。"""
        self.page_id(page)
        if page in self.registered:
            return
        self.registered.add(page)
        self.listen(page, "close", lambda _: self.record("page.close", page))

        def crashed(_):
            self.crashed_pages.add(page)
            self.record("page.crash", page)

        self.listen(page, "crash", crashed)
        for name in ("framenavigated", "frameattached", "framedetached"):
            def frame_event(frame, name=name):
                main = frame == page.main_frame
                self.record("page." + name, page, target_url=frame.url, is_main_frame=main,
                            blank_candidate=name == "framenavigated" and main)
            self.listen(page, name, frame_event)
        self.record(kind, page, target_url=page.url, is_main_frame=True,
                    blank_candidate=kind == "page.created")
        self.pending_cdp.append(page)

    def start(self):
        """先登记已有页面，再启用浏览器级 Target 通知；不改变页面和网络响应。"""
        self.listen(self.context, "page", self.register)

        def closed(_):
            self.context_closed = True
            self.record("context.close")

        self.listen(self.context, "close", closed)
        # 主页面先分配 page-1；其他已存在页面有各自编号，绝不换绑。
        self.register(self.session.page, "page.existing")
        for page in self.context.pages:
            self.register(page, "page.existing")
        browser = self.context.browser
        if browser is None:
            self.report["cdp_capabilities"].append({"scope": "browser", "status": "unavailable"})
        else:
            def disconnected(_):
                self.disconnected = True
                self.record("browser.disconnected")
            self.listen(browser, "disconnected", disconnected)
            self.report["browser_version"] = browser.version
            try:
                client = browser.new_browser_cdp_session()
                self.clients.append(client)
                for name in ("targetCreated", "targetDestroyed", "targetInfoChanged"):
                    self.listen(client, "Target." + name, lambda params, name=name: self.target_event(name, params))
                client.send("Target.setDiscoverTargets", {"discover": True})
                self.report["cdp_capabilities"].append({"scope": "browser", "status": "enabled",
                                                       "domain": "Target"})
            except PlaywrightError as exc:
                self.report["cdp_capabilities"].append({"scope": "browser", "status": "unavailable",
                                                       "error_type": type(exc).__name__})
        self.attach_pending()
        self.report["initial_page_id"] = self.page_id(self.session.page)

    def target_event(self, name, params):
        info = params.get("targetInfo", {})
        target_id = info.get("targetId", params.get("targetId"))
        if "url" in info:
            self.target_urls[target_id] = info["url"]
        page = self.target_pages.get(target_id)
        self.record("Target." + name, page, target_url=self.target_urls.get(target_id),
                    target_id=target_id, target_type=info.get("type"), opener_target_id=info.get("openerId"),
                    browser_context_id=info.get("browserContextId"), page_id_known_at_event=page is not None,
                    blank_candidate=(info.get("type") == "page" and self.context_id is not None
                                     and info.get("browserContextId") == self.context_id))

    def attach_pending(self):
        """对每个仍存在的页面启用 CDP；不支持时保留 Playwright 生命周期事件。"""
        while self.pending_cdp and not self.context_closed:
            page = self.pending_cdp.pop(0)
            if page.is_closed() or page in self.crashed_pages:
                self.report["cdp_capabilities"].append({"scope": self.page_id(page),
                    "status": "page_unavailable_before_attach", "is_closed": page.is_closed(),
                    "crashed": page in self.crashed_pages})
                continue
            try:
                client = self.context.new_cdp_session(page)
                self.clients.append(client)
                self.attach_page(client, page)
                self.report["cdp_capabilities"].append({"scope": self.page_id(page), "status": "enabled", "domain": "Page"})
            except PlaywrightError as exc:
                self.report["cdp_capabilities"].append({"scope": self.page_id(page), "status": "unavailable",
                                                       "error_type": type(exc).__name__})

    def attach_page(self, client, page):
        """用 Target.getTargetInfo 明确建立关联，不根据相同 URL 合并页面。"""
        frame_main, frame_urls = {}, {}
        info = client.send("Target.getTargetInfo")["targetInfo"]
        target_id = info["targetId"]
        if page is self.session.page:
            self.context_id = info.get("browserContextId")
        self.target_pages[target_id] = page
        self.record("diagnostic.target_bound", page, target_id=target_id)

        def requested(params):
            reason = params.get("reason", "unknown")
            known = {"anchorClick", "formSubmissionGet", "formSubmissionPost", "httpHeaderRefresh",
                     "metaTagRefresh", "scriptInitiated", "reload", "pageBlockInterstitial"}
            self.record("Page.frameRequestedNavigation", page, target_url=params.get("url"),
                        is_main_frame=frame_main.get(params.get("frameId")), frame_id=params.get("frameId"),
                        target_id=target_id, reason=reason if reason in known else "unknown")

        def navigated(params):
            frame = params["frame"]
            main = not frame.get("parentId")
            frame_main[frame["id"]], frame_urls[frame["id"]] = main, frame.get("url")
            self.record("Page.frameNavigated", page, target_url=frame.get("url"), is_main_frame=main,
                        frame_id=frame["id"], target_id=target_id, blank_candidate=main)

        def detached(params):
            frame_id = params.get("frameId")
            self.record("Page.frameDetached", page, target_url=frame_urls.get(frame_id),
                        is_main_frame=frame_main.get(frame_id), frame_id=frame_id, target_id=target_id,
                        reason=params.get("reason") if params.get("reason") in {"remove", "swap"} else "unknown")

        def attached(params):
            frame_main[params["frameId"]] = False
            self.record("Page.frameAttached", page, is_main_frame=False, frame_id=params["frameId"],
                        parent_frame_id=params.get("parentFrameId"), target_id=target_id)

        self.listen(client, "Page.frameRequestedNavigation", requested)
        self.listen(client, "Page.frameNavigated", navigated)
        self.listen(client, "Page.frameDetached", detached)
        self.listen(client, "Page.frameAttached", attached)
        client.send("Page.enable")

        def remember(tree, main=True):
            frame = tree["frame"]
            frame_main[frame["id"]], frame_urls[frame["id"]] = main, frame.get("url")
            for child in tree.get("childFrames", []):
                remember(child, False)
        remember(client.send("Page.getFrameTree")["frameTree"])

    def stop(self, reason):
        """先终止记录再解除 CDP，避免把诊断自己的清理动作记录成故障。"""
        self.record("diagnostic.finished", reason=reason)
        for event in self.report["events"]:
            # Target 通知可能早于 context.page；仅凭真实 Target 关联补齐编号，保留当时是否已知。
            page = self.target_pages.get(event.get("target_id"))
            if page is not None and event["page_id"] is None:
                event["page_id"] = self.page_id(page)
        first = self.report.get("first_blank")
        if first and first["page_id"] is None:
            page = self.target_pages.get(first.get("target_id"))
            if page is not None:
                first["page_id"] = self.page_id(page)
        self.report["known_pages"] = [{"page_id": page_id, "url": observed_url(page.url),
                                        "is_closed": page.is_closed(), "crashed": page in self.crashed_pages}
                                       for page, page_id in self.pages.items()]
        self.report["final_pages"] = self.snapshot()
        self.report["end_reason"] = reason
        self.report["caller_cleanup_included"] = False
        self.report["blank_grace"] = {"requested_ms": 2000, "observed_ms":
            round((monotonic() - self.first_blank) * 1000) if self.first_blank is not None else None,
            "completed": self.first_blank is not None and monotonic() - self.first_blank >= 2}
        for emitter, event, handler in reversed(self.listeners):
            emitter.remove_listener(event, handler)
        for client in reversed(self.clients):
            try:
                client.detach()
            except PlaywrightError:
                pass


def diagnose_navigation(session, *, seconds: float = 8, url: str | None = None) -> dict:
    """仅导航一次；空白后继续旁观两秒，不点击、不重试、不改动页面。"""
    if not 0 < seconds <= 15:
        raise ValueError("诊断观察时长必须在 0 到 15 秒之间")
    destination = diagnostic_url(url or session.site.home)
    observer = NavigationObserver(session, destination)
    report, reason = observer.report, "observation_timeout"
    try:
        observer.start()
        observer.navigation_started = True
        observer.record("diagnostic.goto", session.page, target_url=destination, is_main_frame=True)
        try:
            response = session.page.goto(destination, wait_until="domcontentloaded", timeout=15000)
            report["http_status"] = response.status if response else None
        except PlaywrightError as exc:
            observer.record("diagnostic.goto_error", session.page, error_type=type(exc).__name__)
            report["goto_error"] = type(exc).__name__
        deadline = monotonic() + seconds
        allowed_hosts = set(session.site.hosts) | {urlsplit(destination).hostname}
        while True:
            if observer.context_closed or observer.disconnected:
                reason = "context_closed" if observer.context_closed else "browser_disconnected"
                break
            observer.attach_pending()
            if observer.first_blank is not None:
                # 此分支只驱动事件循环，不再读取 DOM、点击、导航或重新打开页面。
                if monotonic() >= observer.first_blank + 2:
                    reason = "blank_grace_completed"
                    break
            else:
                if report.get("http_status") in {401, 403, 429}:
                    reason = "access_paused"
                    break
                if monotonic() >= deadline:
                    break
                page = session.page
                if not page.is_closed() and page not in observer.crashed_pages:
                    if observed_url(page.url) == "about:blank":
                        observer.record("diagnostic.blank_observed", page, target_url=page.url,
                                        is_main_frame=True, blank_candidate=True)
                        continue
                    try:
                        parts = urlsplit(page.url)
                        if parts.scheme != "https" or parts.hostname not in allowed_hosts:
                            reason = "unexpected_origin"
                            break
                        title = page.title()
                        if observer.first_blank is not None:
                            continue
                        if any(word in title for word in CHALLENGE_TITLES):
                            reason = "verification_paused"
                            break
                        for selector in CHALLENGE_SELECTORS:
                            if observer.first_blank is not None:
                                break
                            if page.locator(f":is({selector}):visible").count():
                                reason = "verification_paused"
                                break
                        if reason == "verification_paused" and observer.first_blank is None:
                            break
                    except PlaywrightError as exc:
                        observer.record("diagnostic.read_error", page, error_type=type(exc).__name__)
            try:
                # 不依赖某个存活 Page：即使原页面关闭，也继续收到其他页面的事件。
                with session.context.expect_event("page", predicate=lambda _: False, timeout=100):
                    pass
            except PlaywrightTimeout:
                pass
            except PlaywrightError as exc:
                observer.record("diagnostic.wait_error", error_type=type(exc).__name__)
                reason = ("context_closed" if observer.context_closed else
                          "browser_disconnected" if observer.disconnected else "observer_wait_error")
                break
        abnormal = (observer.first_blank is not None or observer.context_closed or observer.disconnected
                    or observer.crashed_pages or session.page.is_closed() or report.get("goto_error")
                    or reason != "observation_timeout")
        report["outcome"] = "paused" if abnormal else "page_observed"
    finally:
        report["final_target"] = target_kind(session.page.url, session.site)
        observer.stop(reason)
    return report
