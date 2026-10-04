"""读取固定标签，保存带分母、运行模式和范围说明的 JSON 评估报告。"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from langgraph.types import Command
from app.config import PROJECT_ROOT, load_settings
from app.main import load_candidate
from app.models.job import JobPosting
from app.llm.client import create_llm
from app.llm.offline import OfflineLLMClient
from app.services.analysis_service import JobAnalyzer
from app.services.matching_service import CandidateMatcher
from app.services.greeting_service import GreetingGenerator
from app.evaluation.metrics import exact_set, evidence_errors, ratio
from app.adapters.mock.adapter import MockJobAdapter
from app.tools.jobs import ToolCallingAdapter
from app.workflow.runtime import open_graph, graph_config
from app.exceptions import LLMError


def workflow_measurement():
    """故意在模型节点失败一次，再重建图恢复；只模拟人工审批。"""
    profile = load_candidate(PROJECT_ROOT / "fixtures/candidate.example.json")
    class FailingClient(OfflineLLMClient):
        def complete(self, *args, **kwargs):
            raise LLMError("评估注入的暂时错误")
    config = graph_config("evaluation-recovery")
    interventions, failure_observed, completed = 0, False, False
    with TemporaryDirectory() as folder:
        # 显式指定临时数据库，不使用用户的生产数据库配置。
        url = "sqlite:///" + (Path(folder) / "evaluation.db").as_posix()
        with open_graph(Path(folder), client=FailingClient(), database_url=url) as (graph, actions):
            try:
                graph.invoke({"run_id": "evaluation-recovery", "source": "mock", "mode": "offline",
                              "queries": [], "candidate": profile.model_dump(mode="json")}, config)
            except LLMError:
                failure_observed = True
        with open_graph(Path(folder), database_url=url) as (graph, actions):
            graph.invoke(None, config)
            for _ in range(60):
                state = graph.get_state(config)
                if not state.next:
                    completed = state.values["status"] == "COMPLETED"
                    break
                action = actions.get(state.values["action_id"])
                actions.decide(action.id, action.digest, interventions == 0, "simulated-eval-human")
                interventions += 1
                graph.invoke(Command(resume=True), config)
            total_jobs = len(graph.get_state(config).values.get("jobs", []))
    return {"Task Completion Rate": ratio(int(completed), 1, "离线 Mock 完整任务"),
            "Human Intervention Rate": ratio(interventions, total_jobs, "模拟审批次数 / 已筛选岗位；审批是预期行为"),
            "Recovery Success Rate": ratio(int(failure_observed and completed), 1, "注入模型失败后跨实例恢复")}


def evaluate(mode="offline", *, browser=False, workflow=True):
    start = perf_counter()
    dataset = json.loads((PROJECT_ROOT / "fixtures/evaluation/gold.json").read_text("utf-8"))
    profile = load_candidate(PROJECT_ROOT / "fixtures/candidate.example.json")
    client = create_llm(mode)
    extraction = matching = missing = hallucinated = claims = 0
    rows = []
    for case in dataset["cases"]:
        job = JobPosting(id="eval:" + case["id"], source="mock", source_job_id=case["id"],
                         title="虚构评估岗位", company="虚构公司", description=case["jd"],
                         url="https://example.test/jobs/" + case["id"])
        analysis = JobAnalyzer(client).analyze(job)
        match = CandidateMatcher().match(profile, job, analysis)
        draft = GreetingGenerator(client).generate(profile, job, match) if match.shortlisted else None
        extraction_ok = exact_set(analysis.required_skills, case["required"]) and exact_set(analysis.preferred_skills, case["preferred"])
        matching_ok = exact_set(match.matched_skills, case["matched"]) and exact_set(match.partial_skills, case["partial"])
        missing_ok = exact_set(match.missing_skills, case["missing"])
        bad, total = evidence_errors(profile, match, draft)
        extraction += extraction_ok; matching += matching_ok; missing += missing_ok
        hallucinated += bad; claims += total
        rows.append({"id": case["id"], "extraction_correct": extraction_ok, "matching_correct": matching_ok,
                     "missing_correct": missing_ok, "predicted_required": analysis.required_skills,
                     "predicted_preferred": analysis.preferred_skills, "invalid_evidence": bad})
    total_cases = len(rows)
    metrics = {"JD Extraction Accuracy": ratio(extraction, total_cases, "必需/优先技能集合完全匹配；不是全部 JD 字段"),
        "Skill Matching Accuracy": ratio(matching, total_cases, "已具备及学习中技能集合完全匹配"),
        "Missing Skill Accuracy": ratio(missing, total_cases, "缺失技能集合完全匹配"),
        "Hallucinated Candidate Evidence Rate": ratio(hallucinated, claims, "匹配和草稿中的编号+原文引用"),
        "Browser Action Success Rate": ratio(0, 0, "未运行浏览器；添加 --browser 可测本地合成页面"),
        "Task Completion Rate": ratio(0, 0, "未运行工作流"),
        "Human Intervention Rate": ratio(0, 0, "未运行工作流"),
        "Recovery Success Rate": ratio(0, 0, "未运行恢复场景")}
    tool_adapter = ToolCallingAdapter(MockJobAdapter(PROJECT_ROOT / "fixtures/jobs"))
    first_job = tool_adapter.tools.adapter.search_jobs()[0]
    expectations = []
    for case in dataset["tools"]:
        if case["method"] == "search":
            tool_adapter.search_jobs(case["input"])
            expectations.append((case["expected_tool"], case["expected_arguments"]))
        else:
            tool_adapter.get_job_detail(first_job.source_job_id)
            expectations.append((case["expected_tool"], {"source_job_id": first_job.source_job_id}))
    events = tool_adapter.tools.events
    metrics["Tool Selection Accuracy"] = ratio(sum(e["tool"] == g[0] for e, g in zip(events, expectations)), len(expectations), "确定性工具路由，不代表 LLM 工具选择能力")
    metrics["Tool Argument Accuracy"] = ratio(sum(e["arguments"] == g[1] for e, g in zip(events, expectations)), len(expectations), "确定性工具参数分派")
    if workflow:
        metrics.update(workflow_measurement())
    if browser:
        from scripts.browser_smoke import main as browser_check
        browser_check()
        metrics["Browser Action Success Rate"] = ratio(2, 2, "本地合成搜索/详情页，由真实 Edge 执行；不是线上成功率")
    usage = [item.model_dump() for item in client.usage]
    metrics["Latency"] = {"value": (perf_counter()-start)*1000, "unit": "ms", "scope": "本次完整评估耗时"}
    def token_total(key):
        return sum(i[key] for i in usage) if all(i[key] is not None for i in usage) else None
    metrics["Token Usage"] = {"input_tokens": token_total("input_tokens"), "output_tokens": token_total("output_tokens"), "scope": "质量样本模型调用；供应商未返回用量时未知"}
    metrics["Cost"] = {"value": sum(i["cost"] for i in usage) if all(i["cost"] is not None for i in usage) else None,
                       "scope": "配置单价后估算；未配置则未知"}
    return {"timestamp": datetime.now(UTC).isoformat(), "mode": mode, "dataset": "synthetic-gold-v1",
            "metrics": metrics, "cases": rows, "usage": usage, "passed_evidence_gate": hallucinated == 0}


def main():
    parser = argparse.ArgumentParser(description="JobPilot Evaluation Pipeline")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/evaluations/latest.json")
    args = parser.parse_args()
    report = evaluate(args.mode, browser=args.browser)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Report: {args.output}")
    return 0 if report["passed_evidence_gate"] else 1


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
