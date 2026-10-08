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
from app.models.analysis import GreetingPlan


def main():
    with TemporaryDirectory() as folder:
        settings_patch = patch("app.llm.client.LLM_SETTINGS_PATH", Path(folder) / ".env")
        settings_patch.start()
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
                page.goto(f"http://127.0.0.1:{port}/#access=dashboard-test-token")
                expect(page.locator("#connection-status")).to_have_text("已连接本机")
                assert "#" not in page.url
                # 自动连接后可刷新；模型密钥只能保存到临时目录，不能进入浏览器存储。
                page.reload()
                expect(page.locator("#connection-status")).to_have_text("已连接本机")
                page.locator("#model-key").fill("synthetic-deepseek-private-key")
                page.locator("#model-save").click()
                expect(page.locator("#model-key")).to_have_value("")
                with patch("app.llm.client.CompatibleLLMClient.complete", return_value=GreetingPlan(evidence_ids=["connection-test"])):
                    page.locator("#model-test").click()
                    expect(page.locator("#model-feedback")).to_contain_text("连接成功")
                assert "synthetic-deepseek-private-key" not in page.evaluate("JSON.stringify({...sessionStorage,...localStorage})")
                page.locator("#ai-settings summary").click()
                # 示例必须填入可见表单，不能只保存在隐藏对象里。
                page.locator("#example").click()
                expect(page.locator("#resume-name")).to_have_value("演示候选人（虚构资料）")
                expect(page.locator("#resume-text")).to_have_value(re.compile(".*Python.*", re.S))
                expect(page.locator(".resume-skill-name")).to_have_count(4)
                expect(page.locator(".resume-skill-name").first).to_have_value("Python")
                expect(page.locator("#resume-days")).to_have_value("4")
                expect(page.locator("#resume-months")).to_have_value("6")
                assert page.locator("#advanced, #profile, #token, #resume-confirm, #resume-build, #profile-apply").count() == 0
                # 修改示例后立即提交，检查实际请求使用新值，而不是示例的旧副本。
                captured = []
                def inspect_start(route):
                    if route.request.method != "POST":
                        route.continue_()
                        return
                    captured.append(route.request.post_data_json)
                    route.fulfill(status=409, json={"detail": "合成检查已收到当前表单"})
                page.route("**/api/runs", inspect_start)
                page.locator("#resume-name").fill("修改后的虚构同学")
                page.locator("#resume-days").select_option("3")
                page.locator("#resume-months").fill("4")
                page.locator("#resume-cities").fill("成都，杭州")
                page.locator(".resume-skill-level").first.select_option("learning")
                page.locator("#source").select_option("nowcoder")
                expect(page.locator("#source-hint")).to_contain_text("Edge")
                page.locator("#search-limit").select_option("20")
                page.locator("#start").click()
                expect(page.locator("#message")).to_contain_text("合成检查已收到当前表单")
                current = captured[-1]
                assert current["source"] == "nowcoder" and current["search_limit"] == 20
                assert current["candidate"]["name"] == "修改后的虚构同学"
                assert current["candidate"]["available_days_per_week"] == 3
                assert current["candidate"]["internship_duration_months"] == 4
                assert current["candidate"]["target_cities"] == ["成都", "杭州"]
                assert current["candidate"]["skills"][0]["level"] == "learning"
                assert current["analysis_only"] is True
                # 全职下隐藏的实习时间不能继续影响请求。
                page.locator("#resume-employment").select_option("full_time")
                expect(page.locator("#availability")).to_be_hidden()
                page.locator("#start").click()
                page.wait_for_function("!document.getElementById('start').disabled")
                assert captured[-1]["candidate"]["available_days_per_week"] is None
                assert captured[-1]["candidate"]["internship_duration_months"] is None
                page.unroute("**/api/runs", inspect_start)
                # 再次载入示例会覆盖每个表单字段；一个按钮即可完成真实本地工作流。
                page.locator("#example").click()
                expect(page.locator("#resume-days")).to_have_value("4")
                page.locator("#start").click()
                expect(page.locator("#run-status")).to_have_text("已完成", timeout=20000)
                expect(page.locator("#run-detail")).to_contain_text("演示候选人（虚构资料）")
                assert page.locator("#results .result").count() > 0
                assert page.locator("#actions, #approval-panel").count() == 0
                # 文件只负责读取正文；填写技能后直接搜索，不再有“生成/确认资料”。
                page.locator("#resume-file").set_input_files({"name": "synthetic.txt", "mimeType": "text/plain",
                    "buffer": "虚构导入同学\n在课程项目中使用 Python 编写测试。".encode("utf-8")})
                expect(page.locator("#resume-text")).to_have_value(re.compile(".*Python.*", re.S))
                page.locator("#resume-name").fill("虚构导入同学")
                page.get_by_label("技能名称", exact=True).fill("Python")
                page.get_by_label("技能程度", exact=True).select_option("project_experience")
                page.get_by_label("简历原文证据", exact=True).fill("在课程项目中使用 Python 编写测试。")
                page.locator("#resume-roles").fill("")
                page.locator("#resume-cities").fill("")
                page.locator("#resume-days").select_option("5")
                page.locator("#start").click()
                expect(page.locator("#run-detail")).to_contain_text("虚构导入同学", timeout=20000)
                expect(page.locator("#run-status")).to_have_text("已完成", timeout=20000)
                count_before = page.locator("#runs button").count()
                page.get_by_label("简历原文证据", exact=True).fill("不存在的 Python 五年工作经历。")
                page.locator("#start").click()
                expect(page.locator("#message")).to_contain_text("技能证据不在简历原文")
                assert page.locator("#runs button").count() == count_before
                # 截图只含虚构资料；最后换回有效原句，方便人工查看表单。
                page.get_by_label("简历原文证据", exact=True).fill("在课程项目中使用 Python 编写测试。")
                page.locator("#refresh").click()
                Path("data").mkdir(exist_ok=True)
                page.screenshot(path="data/dashboard-smoke.png", full_page=True)
                assert not errors, errors
                browser.close()
                print("Dashboard example prefill / current form / availability / one-button search / evidence: OK")
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            sock.close()
            settings_patch.stop()


if __name__ == "__main__":
    main()
