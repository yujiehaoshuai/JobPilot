"""使用真实本地 HTTP 服务和 Edge 完成页面操作，并保存截图供人工查看。"""

import socket
import threading
import time
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
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
                # 先用虚构文本走简历整理表单，再继续原来的完整工作流回归。
                page.locator("#resume-builder summary").click()
                page.locator("#resume-file").set_input_files({"name": "synthetic.txt", "mimeType": "text/plain",
                    "buffer": "虚构同学\n在课程项目中使用 Python 编写测试。".encode("utf-8")})
                expect(page.locator("#resume-text")).to_have_value(re.compile(".*Python.*", re.S))
                page.locator("#resume-name").fill("虚构同学")
                page.get_by_role("button", name="添加技能证据").click()
                page.get_by_label("技能名称", exact=True).fill("Python")
                page.get_by_label("技能程度", exact=True).select_option("project_experience")
                page.get_by_label("简历原文证据", exact=True).fill("在课程项目中使用 Python 编写测试。")
                page.locator("#resume-confirm").check()
                page.get_by_role("button", name="生成新资料 JSON").click()
                expect(page.locator("#profile")).to_have_value(re.compile(".*虚构同学.*", re.S))
                Path("data").mkdir(exist_ok=True)
                page.screenshot(path="data/resume-smoke.png", full_page=True)
                page.locator("#resume-builder summary").click()
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
                # 临时故障只作用于本脚本的模拟执行器，验证人工核查表单的完整路径。
                page.get_by_role("button", name="批准本条（模拟）").wait_for(timeout=20000)
                with patch("app.services.action_service.MockActionExecutor.send", side_effect=TimeoutError("模拟超时")):
                    page.get_by_role("button", name="批准本条（模拟）").click()
                    pending = page.locator('.action[data-status="UNCERTAIN"]')
                    pending.wait_for(timeout=20000)
                action_id = pending.get_attribute("data-action-id")
                pending.get_by_label("发送结果核查依据").fill("模拟人工核对平台记录未发送")
                pending.get_by_role("button", name="确认未发送，结束此动作").click()
                page.locator(f'.action[data-action-id="{action_id}"][data-status="REJECTED"]').wait_for(timeout=20000)
                page.locator("#resume").click()
                page.get_by_role("button", name="批准本条（模拟）").wait_for(timeout=20000)
                assert not errors, errors
                browser.close()
                print("Dashboard load / evidence / reject / simulated approve / manual recovery: OK")
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            sock.close()


if __name__ == "__main__":
    main()
