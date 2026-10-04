"""使用真实本地 HTTP 服务和 Edge 完成页面操作，并保存截图供人工查看。"""

import socket
import threading
import time
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.api.server import create_app
from app.runtime_config import setting


def main():
    with TemporaryDirectory() as folder:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        app = create_app(Path(folder), token="dashboard-test-token")
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=setting("BROWSER_CHANNEL", "msedge"), headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1050})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}")
                page.locator("#token").fill("dashboard-test-token")
                page.get_by_role("button", name="载入虚构示例").click()
                expect(page.locator("#profile")).to_have_value(re.compile(r'.*"skills".*', re.S))
                page.get_by_role("button", name="开始搜索与分析").click()
                page.get_by_role("button", name="批准本条（模拟）").wait_for(timeout=20000)
                assert page.locator("#results").inner_text().find("已具备") >= 0
                Path("data").mkdir(exist_ok=True)
                page.screenshot(path="data/dashboard-smoke.png", full_page=True)
                page.get_by_role("button", name="拒绝本条").click()
                page.locator('.action[data-status="REJECTED"]').wait_for(timeout=20000)
                page.get_by_role("button", name="批准本条（模拟）").wait_for(timeout=20000)
                page.get_by_role("button", name="批准本条（模拟）").click()
                page.locator('.action[data-status="SUCCEEDED"]').wait_for(timeout=20000)
                assert not errors, errors
                browser.close()
                print("Dashboard load / evidence / reject / simulated approve: OK")
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            sock.close()


if __name__ == "__main__":
    main()
