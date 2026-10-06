"""验证页面身份、异常生命周期、对照入口，以及 URL 敏感字段的过滤。"""

import pytest
from app.browser.diagnostics import target_kind, diagnostic_url, observed_url, NavigationObserver
from app.browser.selectors import BOSS


@pytest.mark.parametrize("url, expected", [
    ("https://www.zhipin.com/web/geek/jobs?token=private#secret", "platform_page"),
    ("about:blank", "blank"),
    ("about:blank#fragment", "blank"),
    ("https://unknown.example/login?token=private", "other_page"),
    ("https://[broken", "other_page"),
])
def test_diagnostic_target_never_exposes_url(url, expected):
    assert target_kind(url, BOSS) == expected


@pytest.mark.parametrize("url", ["file:///C:/private.txt", "javascript:alert(1)", "http://example.com",
    "https://user:password@example.com", "https://[broken", "https://example.com:999999", "https://"])
def test_diagnostic_rejects_non_https_or_embedded_credentials(url):
    with pytest.raises(ValueError):
        diagnostic_url(url)


def test_diagnostic_url_is_not_limited_to_boss_and_report_removes_secrets():
    value = "https://example.com/path?token=private#secret"
    assert diagnostic_url(value) == value
    assert observed_url(value) == "https://example.com/path"
    assert observed_url("https://user:password@example.com/path") == "https://example.com/path"
    assert observed_url("about:blank#secret") == "about:blank"
    assert observed_url("data:text/html,secret") == "data:<redacted>"


@pytest.mark.parametrize("arguments", [["search", "--url", "https://example.com"],
                                      ["diagnose", "--url", "file:///C:/private.txt"]])
def test_invalid_url_arguments_fail_before_browser_launch(arguments, monkeypatch):
    from app import browser_cli
    from unittest.mock import Mock
    launch = Mock()
    monkeypatch.setattr(browser_cli, "BrowserSession", launch)
    monkeypatch.setattr("sys.argv", ["browser_cli", *arguments])
    with pytest.raises(SystemExit) as error:
        browser_cli.main()
    assert error.value.code == 2
    launch.assert_not_called()


def test_control_url_keeps_identical_launch_settings(tmp_path, monkeypatch):
    """两个 CLI 命令只能改变诊断目的地址，平台 Profile 与启动参数应完全一致。"""
    from unittest.mock import Mock
    from app import browser_cli
    from app.browser import diagnostics
    session = Mock()
    launch = Mock()
    launch.return_value.__enter__ = Mock(return_value=session)
    launch.return_value.__exit__ = Mock(return_value=False)
    diagnose = Mock(return_value={"outcome": "page_observed"})
    monkeypatch.setattr(browser_cli, "BrowserSession", launch)
    monkeypatch.setattr(browser_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(diagnostics, "diagnose_navigation", diagnose)
    for arguments in [[], ["--url", "https://example.com"]]:
        monkeypatch.setattr("sys.argv", ["browser_cli", "diagnose", "--source", "boss", *arguments])
        assert browser_cli.main() == 0
    assert launch.call_args_list[0] == launch.call_args_list[1]
    assert launch.call_args.args[1] == tmp_path / "profiles/boss"
    assert [call.kwargs["url"] for call in diagnose.call_args_list] == [None, "https://example.com"]


def test_closed_crashed_pages_and_context_keep_distinct_identities(tmp_path):
    """用可控事件源检查异常生命周期，不故意让本机 Edge 崩溃。"""
    from types import SimpleNamespace
    from playwright.sync_api import Error

    class Events:
        def __init__(self):
            self.handlers = {}

        def on(self, name, handler):
            self.handlers.setdefault(name, []).append(handler)

        def remove_listener(self, name, handler):
            self.handlers[name].remove(handler)

        def emit(self, name, value):
            for handler in list(self.handlers.get(name, [])):
                handler(value)

    class Page(Events):
        def __init__(self, url):
            super().__init__()
            self.url, self.closed = url, False
            self.main_frame = SimpleNamespace(url=url)

        def is_closed(self):
            return self.closed

    class Browser(Events):
        version = "synthetic-test"

        def new_browser_cdp_session(self):
            raise Error("模拟不支持 CDP")

    class Context(Events):
        def new_cdp_session(self, page):
            raise Error("模拟不支持 CDP")

    context = Context()
    context.browser = Browser()
    main = Page("https://www.zhipin.com")
    context.pages = [main]
    session = SimpleNamespace(context=context, page=main, site=BOSS, channel="msedge", headless=False, profile=tmp_path)
    observer = NavigationObserver(session, BOSS.home)
    observer.start()
    observer.navigation_started = True
    popup = Page("about:blank")
    context.pages.append(popup)
    context.emit("page", popup)
    main.emit("crash", main)
    main.closed = True
    context.pages.remove(main)
    main.emit("close", main)
    popup.closed = True
    context.pages.clear()
    context.emit("close", context)
    context.browser.emit("disconnected", context.browser)
    observer.stop("context_closed")
    report = observer.report
    assert report["first_blank"]["page_id"] == "page-2"
    assert report["known_pages"][0] == {"page_id": "page-1", "url": BOSS.home, "is_closed": True, "crashed": True}
    event = next(e for e in report["events"] if e["kind"] == "page.close")
    assert event["page_id"] == "page-1" and [p["page_id"] for p in event["pages"]] == ["page-2"]
    assert {"context.close", "browser.disconnected", "page.crash"} <= {e["kind"] for e in report["events"]}
    assert not report["blank_grace"]["completed"]
    assert not report["caller_cleanup_included"]
    before = len(report["events"])
    context.emit("close", context)
    assert len(report["events"]) == before
