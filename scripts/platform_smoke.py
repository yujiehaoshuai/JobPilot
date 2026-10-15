"""用真实浏览器读取指定平台的本地合成页面，验证统一 Adapter 契约。"""

import argparse
import re
from urllib.parse import urlsplit
from pathlib import Path
from tempfile import TemporaryDirectory
from app.adapters.factory import PLATFORMS
from app.browser.session import BrowserSession
from app.runtime_config import setting


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=list(PLATFORMS))
    args = parser.parse_args()
    site, adapter_type = PLATFORMS[args.source]
    with TemporaryDirectory() as folder:
        with BrowserSession(site, Path(folder), headless=True, channel=setting("BROWSER_CHANNEL", "msedge")) as session:
            def route(request):
                suffix = "detail" if re.fullmatch(site.detail_pattern, urlsplit(request.request.url).path) else "search"
                body = Path(f"fixtures/browser/{args.source}_{suffix}.html").read_text("utf-8")
                # 合成 HTML 与真实 HTTP 一样明确编码，避免浏览器猜编码产生伪乱码。
                request.fulfill(body=body, content_type="text/html; charset=utf-8")
            session.context.route("**/*", route)
            jobs = adapter_type(session, limit=1).search_jobs(["Python"])
            assert len(jobs) == 1 and jobs[0].source == args.source
            print(f"{args.source} local browser search/detail: OK")


if __name__ == "__main__":
    main()
