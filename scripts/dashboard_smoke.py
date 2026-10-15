"""使用真实本地 HTTP 服务和 Edge 完成页面操作，并保存截图供人工查看。"""

import socket
import threading
import time
import re
from copy import deepcopy
from uuid import uuid4
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.api.server import create_app
from app.runtime_config import setting
from app.models.analysis import GreetingPlan
from app.models.job import JobPosting


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
                # 示例填入唯一的正文与意向；旧技能卡和重复意向入口必须消失。
                page.locator("#example").click()
                expect(page.locator("#resume-text")).to_have_value(re.compile(".*Python.*", re.S))
                expect(page.locator("#query")).to_have_value("Python")
                assert page.locator(".layout > aside.panel").count()==1
                assert page.locator("aside section, #resume-name, #resume-roles, #resume-skills, #mode, #search-limit, #advanced").count()==0
                captured=[]
                def inspect_start(route):
                    captured.append(route.request.post_data_json)
                    route.fulfill(status=409,json={"detail":"合成检查已收到当前正文"})
                page.route("**/api/search",inspect_start)
                page.locator("#resume-text").fill("新的虚构简历：在课程项目中使用 Python。")
                page.locator("#query").fill("AI 应用开发")
                page.locator("#resume-days").select_option("3")
                page.locator("#resume-months").fill("4")
                page.locator("#resume-cities").fill("成都，杭州")
                page.locator("#source").select_option("nowcoder")
                page.locator("#start").click()
                expect(page.locator("#message")).to_contain_text("合成检查已收到当前正文")
                current=captured[-1]
                assert current["text"].startswith("新的虚构简历") and current["intent"]=="AI 应用开发"
                assert current["cities"]==["成都","杭州"] and current["available_days_per_week"]==3
                assert current["source"]=="nowcoder" and current["mode"]=="live"
                assert "candidate" not in current and "skills" not in current
                # 没有安装助手时显示中文步骤，不创建注定无法取数的 BOSS 任务。
                page.locator("#source").select_option("boss")
                expect(page.locator("#boss-setup")).to_be_visible()
                previous_count=len(captured)
                page.locator("#start").click()
                expect(page.locator("#message")).to_contain_text("需要先添加浏览器助手",timeout=10000)
                assert len(captured)==previous_count
                assert page.locator("#boss-install").get_attribute("open") is not None
                page.locator("#source").select_option("nowcoder")
                page.locator("#resume-employment").select_option("full_time")
                expect(page.locator("#availability")).to_be_hidden()
                page.locator("#start").click()
                expect(page.locator("#start")).to_be_enabled()
                assert captured[-1]["available_days_per_week"] is None
                page.unroute("**/api/search",inspect_start)
                # 一个按钮完成提炼、筛选、评分、前五名复核，没有任何发送动作。
                page.locator("#example").click()
                # 示例通过异步请求加载；等表单填好后再清空城市，避免被回填覆盖。
                expect(page.locator("#source")).to_have_value("mock")
                expect(page.locator("#query")).to_have_value("Python")
                page.locator("#resume-cities").fill("")
                page.locator("#start").click()
                assert not page.locator("#resume-cities").evaluate("el=>el.checkValidity()")
                page.locator("#resume-cities").fill("上海，北京，深圳，杭州，广州，成都")
                page.locator("#resume-days").select_option("3")
                page.locator("#start").click()
                expect(page.locator("#run-status")).to_have_text("已完成",timeout=30000)
                expect(page.locator(".profile-extract")).to_contain_text("项技能")
                expect(page.locator("#results .review")).to_have_count(5)
                assert page.locator("#results .score").count()>5
                scores=page.locator("#results .score").all_text_contents()
                values=[float(text.split("/")[0]) for text in scores]
                assert values==sorted(values,reverse=True)
                expect(page.locator("#results")).to_contain_text("保留机会")
                assert page.locator("#actions, #approval-panel").count()==0
                # PDF 上传走真实 HTTP 和解析器，中文正文填回同一输入框。
                from tests.pdf_samples import resume_pdf
                page.locator("#resume-file").set_input_files({"name":"synthetic.pdf","mimeType":"application/pdf",
                    "buffer":resume_pdf("虚构 PDF 简历：在课程项目中使用 Python 编写工具。")})
                expect(page.locator("#resume-text")).to_have_value("虚构 PDF 简历：在课程项目中使用 Python 编写工具。")
                assert "把简历里会的" not in page.locator("body").inner_text()
                assert "帮你看岗位，也帮你看差距" not in page.locator("body").inner_text()
                # 上传文件只替换正文，不再要求手填技能。随后再提交一次验证当前原文。
                page.locator("#resume-file").set_input_files({"name":"synthetic.txt","mimeType":"text/plain",
                    "buffer":"虚构导入：在课程项目中使用 Python 编写测试。".encode("utf-8")})
                expect(page.locator("#resume-text")).to_have_value("虚构导入：在课程项目中使用 Python 编写测试。")
                page.locator("#start").click()
                expect(page.locator(".profile-extract")).to_contain_text("虚构导入",timeout=30000)
                expect(page.locator("#run-status")).to_have_text("已完成",timeout=30000)
                # 只有数量上限触发继续入口；每次提交页面显示的旧额度，防止双击重复追加。
                page.evaluate("""() => {
                    const run={id:currentRun,status:'COMPLETED',source:'mock',mode:'offline',
                        input:{ranking:true,search_limit:100},snapshot:{ranking:true,results:[],
                        search_coverage:{limit_reached:true}}};
                    showState(run);
                }""")
                expanded=[]
                def inspect_expand(route):
                    expanded.append(route.request.post_data_json)
                    route.fulfill(status=409,json={"detail":"合成检查已收到追加搜索"})
                page.route("**/api/runs/*/expand",inspect_expand)
                page.locator("#search-more").click()
                expect(page.locator("#message")).to_contain_text("合成检查已收到追加搜索")
                assert expanded==[{"expected_limit":100}]
                page.unroute("**/api/runs/*/expand",inspect_expand)
                # 只在临时库构造 BOSS 结果，验证真实 UI 审批；此浏览器未加载扩展。
                synthetic = deepcopy(app.state.runs.get(page.evaluate("currentRun")))
                synthetic_id = str(uuid4())
                synthetic.pop("id"); synthetic.pop("status")
                synthetic["source"] = "boss"
                synthetic["snapshot"]["results"] = synthetic["snapshot"]["results"][:2]
                for number, row in enumerate(synthetic["snapshot"]["results"]):
                    row["job"].update(id=f"boss-ui-{number}", source="boss", source_job_id=f"synthetic{number}",
                        url=f"https://www.zhipin.com/job_detail/synthetic{number}.html")
                service = app.state.boss_contacts
                service.tracker.save_jobs([JobPosting.model_validate(row["job"]) for row in synthetic["snapshot"]["results"]])
                app.state.runs.create(synthetic_id, synthetic)
                app.state.runs.update(synthetic_id, "COMPLETED")
                page.evaluate("runId=>selectRun(runId)", synthetic_id)
                expect(page.locator("#batch-controls")).to_be_visible()
                expect(page.locator("#results .selection input:checked")).to_have_count(0)
                page.locator("#results .selection input").first.check()
                page.locator("#batch-prepare").click()
                expect(page.locator("#batch-items article")).to_have_count(1)
                expect(page.locator("#batch-items")).to_contain_text("默认招呼")
                page.locator("#batch-approve").click()
                expect(page.locator("#message")).to_contain_text("请先核对 BOSS 账号")
                assert service.next() is None
                page.locator("#batch-confirm").check()
                # 若另一个窗口加入待审批岗位，刷新会撤销旧勾选，必须重新核对列表。
                service.prepare(synthetic_id, ["boss-ui-1"])
                page.locator("#batch-refresh").click()
                expect(page.locator("#batch-items article")).to_have_count(2)
                expect(page.locator("#batch-confirm")).not_to_be_checked()
                page.route("**/api/boss/status", lambda route: route.fulfill(json={"connected": True}))
                page.locator("#batch-confirm").check()
                page.locator("#batch-approve").click()
                expect(page.locator("#batch-feedback")).to_contain_text("已批准")
                assert all(a.status == "APPROVED" for a in service.list(synthetic_id))
                page.locator("#batch-cancel").click()
                expect(page.locator("#batch-feedback")).to_contain_text("已取消")
                assert all(a.status == "REJECTED" for a in service.list(synthetic_id))
                assert service.next() is None
                Path("data").mkdir(exist_ok=True)
                page.screenshot(path="data/dashboard-smoke.png", full_page=True)
                page.set_viewport_size({"width":390,"height":844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "窄屏出现横向溢出"
                assert not errors, errors
                browser.close()
                print("Dashboard resume / scoring / batch selection / explicit approval / cancellation: OK")
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            sock.close()
            settings_patch.stop()


if __name__ == "__main__":
    main()
