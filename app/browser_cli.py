"""浏览器只读命令；人工登录仅在明确执行 login 时打开交互窗口。"""

import argparse
import sys
from pathlib import Path
from app.adapters.boss import BossAdapter
from app.browser.selectors import BOSS
from app.browser.session import BrowserSession
from app.exceptions import JobPilotError
from app.adapters.factory import PLATFORMS
from app.config import PROJECT_ROOT


def main() -> int:
    """登录状态留在 profiles，不输出 Cookie，也不自动解决验证码。"""
    parser = argparse.ArgumentParser(description="招聘平台只读浏览器")
    parser.add_argument("command", choices=["login", "search"])
    parser.add_argument("--query", default="Python")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--source", choices=list(PLATFORMS), default="boss")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    if args.command == "login" and args.headless:
        parser.error("人工登录必须显示浏览器窗口")
    site, adapter_type = PLATFORMS[args.source]
    try:
        with BrowserSession(site, PROJECT_ROOT / "profiles" / args.source, channel=args.channel or None,
                            headless=args.headless) as session:
            if args.command == "login":
                session.page.goto(site.home)
                input("请在浏览器中手动登录或完成验证；确认完成后按回车保存并关闭：")
                session.ensure_ready()
            else:
                for job in adapter_type(session, args.limit).search_jobs([args.query]):
                    print(job.model_dump_json())
        return 0
    except JobPilotError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
