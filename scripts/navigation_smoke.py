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
            assert any(event.get("reason") == "scriptInitiated" and event["target"] == "blank"
                       for event in report["navigation_events"]), report
            print("Local navigation diagnostics / script redirect / pause: OK")


if __name__ == "__main__":
    main()
