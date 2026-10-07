"""用本地合成状态流验证正常断流续接和有限网络重试，不等待一分钟。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import json
from playwright.sync_api import sync_playwright, expect
from app.runtime_config import setting
from scripts.recovery_smoke import temporary_server


def main():
    with TemporaryDirectory(prefix="jobpilot-stream-") as folder:
        with temporary_server(Path(folder)) as client, sync_playwright() as driver:
            browser = driver.chromium.launch(channel=setting("BROWSER_CHANNEL", "msedge"), headless=True)
            try:
                page = browser.new_page()
                errors, requests = [], []
                connections = 0
                offline = False

                def state():
                    return {"id": "synthetic-stream", "source": "mock", "mode": "offline",
                            "status": "PAUSED" if connections >= 3 else "RUNNING",
                            "snapshot": {"jobs": [], "index": 0}, "interrupts": []}

                def route_api(route):
                    nonlocal connections
                    path = urlsplit(route.request.url).path
                    requests.append(route.request.method)
                    if path.endswith("/events"):
                        connections += 1
                        if offline or connections == 2:
                            # 模拟一次网络断开；第三次连接应恢复，不能重放任何动作。
                            route.abort("failed")
                            return
                        route.fulfill(content_type="text/event-stream",
                                      body="event: state\ndata: " + json.dumps(state()) + "\n\n")
                        return
                    value = [state()] if path == "/api/runs" else ([] if path == "/api/actions" else state())
                    route.fulfill(content_type="application/json", body=json.dumps(value))

                page.route("**/api/**", route_api)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(client.base_url + "/#access=synthetic-token")
                expect(page.locator("#connection-status")).to_have_text("已连接本机")
                page.locator("#refresh").click()
                page.locator("#runs button").click()
                expect(page.locator("#run-status")).to_have_text("等待人工处理", timeout=15000)
                assert connections == 3 and set(requests) == {"GET"}
                # 连续失败三次后必须停止，并给出手动恢复提示，不能无限刷接口。
                offline, connections = True, 0
                page.locator("#runs button").click()
                expect(page.locator("#message")).to_contain_text("状态连接连续失败", timeout=15000)
                page.wait_for_timeout(1200)
                assert connections == 3 and set(requests) == {"GET"}
                assert not errors, errors
                print("SSE rotation / bounded reconnect / read-only requests: OK")
            finally:
                browser.close()


if __name__ == "__main__":
    main()
