"""浏览器只读命令；人工登录仅在明确执行 login 时打开交互窗口。"""

import argparse
import sys
from playwright.sync_api import Error as PlaywrightError
from app.browser.session import BrowserSession
from app.exceptions import JobPilotError
from app.adapters.factory import PLATFORMS
from app.config import PROJECT_ROOT


def main() -> int:
    """登录状态留在 profiles，不输出 Cookie，也不自动解决验证码。"""
    parser = argparse.ArgumentParser(description="招聘平台只读浏览器")
    parser.add_argument("command", choices=["login", "search", "diagnose"])
    parser.add_argument("--query", default="Python")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--source", choices=list(PLATFORMS), default="boss")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--manual", action="store_true", help="用本机普通 Edge 窗口人工登录")
    parser.add_argument("--url", help="仅 diagnose：替换访问地址，复用同一平台资料和启动参数")
    args = parser.parse_args()
    if args.command == "login" and args.headless:
        parser.error("人工登录必须显示浏览器窗口")
    if args.manual and (args.command != "login" or args.channel != "msedge"):
        parser.error("--manual 仅用于本机 Edge 的 login 命令")
    if args.url is not None:
        if args.command != "diagnose":
            parser.error("--url 仅用于 diagnose 对照实验")
        from app.browser.diagnostics import diagnostic_url
        try:
            diagnostic_url(args.url)
        except ValueError as exc:
            parser.error(str(exc))
    site, adapter_type = PLATFORMS[args.source]
    try:
        if args.source == "shixiseng" and args.command == "search":
            from app.adapters.http_reader import PublicPageReader
            with PublicPageReader(site) as reader:
                adapter = adapter_type(reader, args.limit)
                for job in adapter.search_jobs([args.query]):
                    print(job.model_dump_json())
                for warning in adapter.read_warnings:
                    print(warning, file=sys.stderr)
            return 0
        if args.manual:
            from app.browser.manual_login import manual_login
            manual_login(site, PROJECT_ROOT / "profiles" / args.source)
            return 0
        with BrowserSession(site, PROJECT_ROOT / "profiles" / args.source, channel=args.channel or None,
                            headless=args.headless) as session:
            if args.command == "login":
                session.page.goto(site.home)
                input("请在浏览器中手动登录或完成验证；确认完成后按回车保存并关闭：")
                session.ensure_ready()
                print("浏览器会话已保存；登录是否可用还需通过只读搜索验证。")
            elif args.command == "diagnose":
                import json
                from uuid import uuid4
                from app.browser.diagnostics import diagnose_navigation
                report = diagnose_navigation(session, url=args.url)
                folder = PROJECT_ROOT / "data/diagnostics"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{args.source}-navigation-{uuid4().hex}.json"
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False, indent=2))
                print(f"诊断报告：{path}")
                return 0 if report["outcome"] == "page_observed" else 1
            else:
                for job in adapter_type(session, args.limit).search_jobs([args.query]):
                    print(job.model_dump_json())
        return 0
    except JobPilotError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except PlaywrightError:
        # 第三方异常可能带页面细节；显示操作建议，不输出资料或长堆栈。
        print("浏览器操作未完成，请检查窗口是否关闭、页面是否超时，再重新运行。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
