"""只读记录导航类型，帮助区分页面脚本跳转和浏览器故障；不改变网页行为。"""

from datetime import UTC, datetime
from time import monotonic
from urllib.parse import urlsplit
from playwright.sync_api import Error as PlaywrightError
from app.exceptions import JobPilotError


def target_kind(url: str, site) -> str:
    """只输出类别，任何 URL 参数、片段或岗位编号都不进入报告。"""
    if url == "about:blank":
        return "blank"
    try:
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname in site.hosts:
            return "platform_page"
    except ValueError:
        pass
    return "other_page"


def diagnose_navigation(session, *, seconds: float = 8) -> dict:
    """只访问一次平台主页，遇到验证、空白或拒绝访问即停，不证明登录成功。"""
    if not 0 < seconds <= 15:
        raise ValueError("诊断观察时长必须在 0 到 15 秒之间")
    started = monotonic()
    report = {"source": session.site.source, "time": datetime.now(UTC).isoformat(),
              "outcome": "observing", "navigation_events": [], "authentication_verified": False}
    client = session.context.new_cdp_session(session.page)
    client.send("Page.enable")
    main_frame_id = client.send("Page.getFrameTree")["frameTree"]["frame"]["id"]

    def record(kind, url, reason=None):
        if len(report["navigation_events"]) >= 50:
            return
        event = {"kind": kind, "target": target_kind(url, session.site),
                 "elapsed_ms": round((monotonic() - started) * 1000)}
        if reason is not None:
            # 只保留协议定义的枚举；不把未知文本原样写入日志。
            known = {"anchorClick", "formSubmissionGet", "formSubmissionPost", "httpHeaderRefresh",
                     "metaTagRefresh", "scriptInitiated", "reload", "pageBlockInterstitial"}
            event["reason"] = reason if reason in known else "unknown"
        report["navigation_events"].append(event)

    def requested(params):
        if params.get("frameId") == main_frame_id:
            record("requested", params.get("url", ""), params.get("reason", "unknown"))

    def navigated(params):
        frame = params.get("frame", {})
        if frame.get("id") == main_frame_id:
            record("committed", frame.get("url", ""))

    client.on("Page.frameRequestedNavigation", requested)
    client.on("Page.frameNavigated", navigated)
    try:
        response = session.page.goto(session.site.home, wait_until="domcontentloaded", timeout=15000)
        report["http_status"] = response.status if response else None
        if report["http_status"] in {401, 403, 429}:
            report["outcome"] = "access_paused"
        else:
            deadline = monotonic() + seconds
            while monotonic() < deadline:
                session.ensure_ready()
                # 让 Playwright 正常处理导航事件；不注入脚本、不拦截响应。
                session.page.wait_for_timeout(100)
            session.ensure_ready()
            report["outcome"] = "page_observed"
    except JobPilotError as exc:
        report["outcome"] = "paused"
        report["error_type"] = type(exc).__name__
    except PlaywrightError:
        report["outcome"] = "browser_error"
    finally:
        report["final_target"] = target_kind(session.page.url, session.site)
        try:
            client.detach()
        except PlaywrightError:
            # 用户关窗时连接可能先断开；已收集的有限报告仍可保存。
            pass
    return report
