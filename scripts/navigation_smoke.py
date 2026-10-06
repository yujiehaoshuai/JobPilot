"""用本地脚本跳转样本验证导航诊断，不向招聘网站发请求。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS
from app.browser.diagnostics import diagnose_navigation
from app.runtime_config import setting


def main():
    """让合成页面自行变空白，验证报告能记录脚本发起的主框架导航。"""
    with TemporaryDirectory(prefix="jobpilot-navigation-") as folder:
        with BrowserSession(BOSS, Path(folder), headless=True,
                            channel=setting("BROWSER_CHANNEL", "msedge")) as session:
            session.context.route("**/*", lambda route: route.fulfill(content_type="text/html", body=
                '<title>虚构测试页</title><p>本地导航样本</p>'
                '<script>setTimeout(()=>location.replace("about:blank"),200)</script>'))
            report = diagnose_navigation(session, seconds=3)
            assert report["outcome"] == "paused" and report["final_target"] == "blank"
            assert any(event.get("reason") == "scriptInitiated" and event["target_url"] == "about:blank"
                       and event["page_id"] == "page-1" and event["is_main_frame"] is True
                       for event in report["events"]), report
            assert report["blank_grace"]["completed"] and report["blank_grace"]["observed_ms"] >= 2000
            assert not session.page.is_closed()
            assert not any(event["kind"] == "context.close" for event in report["events"])
            print("Local navigation identity / script redirect / 2-second observation: OK")


if __name__ == "__main__":
    main()
