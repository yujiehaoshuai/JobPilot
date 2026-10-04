"""用本地响应驱动真实浏览器，验证 DOM 解析和人工验证暂停，不连接平台。"""

import tempfile
from pathlib import Path
from app.adapters.boss import BossAdapter
from app.browser.selectors import BOSS
from app.browser.session import BrowserSession
from app.exceptions import BrowserPausedError


def main():
    """通过路由替换响应，确保测试不会访问真实招聘网站。"""
    base = Path("fixtures/browser")
    with tempfile.TemporaryDirectory(prefix="jobpilot-browser-") as profile:
        with BrowserSession(BOSS, Path(profile), headless=True) as session:
            def route(request):
                filename = "boss_detail.html" if "/job_detail/" in request.request.url else "boss_search.html"
                request.fulfill(body=(base / filename).read_text("utf-8"), content_type="text/html")
            session.context.route("**/*", route)
            jobs = BossAdapter(session).search_jobs(["Python"])
            assert len(jobs) == 1 and jobs[0].source_job_id == "demo01"
            session.page.set_content("<title>安全验证</title><div id='captcha'>请验证</div>")
            try:
                session.ensure_ready()
            except BrowserPausedError:
                print("BOSS 本地页面读取和验证码暂停验证通过")
            else:
                raise AssertionError("验证页面没有暂停")


if __name__ == "__main__":
    main()
