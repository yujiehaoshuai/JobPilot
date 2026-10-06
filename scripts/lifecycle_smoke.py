"""用合成页面验证多窗口身份、关闭事件和普通 HTTPS 对照入口。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import json
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS
from app.browser.diagnostics import diagnose_navigation
from app.runtime_config import setting


def main():
    """只有本地样本脚本创建弹窗；诊断本身不创建、关闭或更换网页。"""
    with TemporaryDirectory(prefix="jobpilot-lifecycle-") as folder:
        with BrowserSession(BOSS, Path(folder), headless=True,
                            channel=setting("BROWSER_CHANNEL", "msedge")) as session:
            def route(request):
                if urlsplit(request.request.url).path not in {"", "/"}:
                    body = "<title>虚构子框架</title><p>只用于本地测试</p>"
                else:
                    body = '''<title>虚构主页面</title><p>主页面保持正常</p><script>
                    setTimeout(() => {
                      const child=window.open('about:blank');
                      if(child) setTimeout(()=>child.close(),500);
                      const frame=document.createElement('iframe'); frame.src='/synthetic-frame';
                      document.body.appendChild(frame); setTimeout(()=>frame.remove(),700);
                    },200);
                    </script>'''
                request.fulfill(content_type="text/html", body=body)
            session.context.route("**/*", route)
            report = diagnose_navigation(session, seconds=3)
            events = report["events"]
            assert report["first_blank"]["page_id"] == "page-2", report
            assert report["final_target"] == "platform_page"
            assert report["blank_grace"]["completed"]
            assert any(e["kind"] == "page.close" and e["page_id"] == "page-2" for e in events)
            assert not any(e["kind"] == "page.close" and e["page_id"] == "page-1" for e in events)
            assert any(e["kind"] == "Page.frameDetached" and e["is_main_frame"] is False for e in events)
            assert any(e["kind"] == "Target.targetCreated" and e["page_id"] == "page-2" for e in events)
            assert any(e["kind"] == "Target.targetDestroyed" and e["page_id"] == "page-2" for e in events)
            assert len(report["final_pages"]) == 1
            assert {p["page_id"]: p["is_closed"] for p in report["known_pages"]} == {"page-1": False, "page-2": True}
            assert all({"page_id", "current_url", "target_url", "kind", "elapsed_ms", "is_main_frame", "pages"} <= e.keys()
                       for e in events)
            output = Path("data/diagnostics/lifecycle-smoke.json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            # 对照仅替换访问地址，仍用同一个 Session、Profile 和参数；响应也由本地提供。
            session.context.unroute("**/*", route)
            session.context.route("**/*", lambda request: request.fulfill(content_type="text/html",
                body="<title>虚构普通网页</title><p>稳定页面</p>"))
            control = diagnose_navigation(session, seconds=0.5, url="https://example.com")
            assert control["outcome"] == "page_observed", control
            assert "first_blank" not in control
            assert control["launch"] == report["launch"]
            assert all(e["kind"] != "context.close" for e in control["events"])
            print("Page identity / popup close / frame detach / Target lifecycle / control URL: OK")


if __name__ == "__main__":
    main()
