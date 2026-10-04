"""浏览器只读命令；人工登录仅在明确执行 login 时打开交互窗口。"""

import argparse
import sys
from pathlib import Path
from app.adapters.boss import BossAdapter
from app.browser.selectors import BOSS
from app.browser.session import BrowserSession
from app.exceptions import JobPilotError


def main() -> int:
    """登录状态留在 profiles，不输出 Cookie，也不自动解决验证码。"""
    parser = argparse.ArgumentParser(description="BOSS 只读浏览器")
    parser.add_argument("command", choices=["login", "search"])
    parser.add_argument("--query", default="Python")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--channel", default="msedge")
    args = parser.parse_args()
    try:
        with BrowserSession(BOSS, Path("profiles/boss"), channel=args.channel or None) as session:
            if args.command == "login":
                session.page.goto(BOSS.home)
                input("请在浏览器中手动登录或完成验证；确认完成后按回车保存并关闭：")
                session.ensure_ready()
            else:
                for job in BossAdapter(session, args.limit).search_jobs([args.query]):
                    print(job.model_dump_json())
        return 0
    except JobPilotError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
