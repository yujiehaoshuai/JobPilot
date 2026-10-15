"""按岗位循环的 LangGraph：读取、过滤、分析、草稿、审批、执行与记账。"""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from app.exceptions import BrowserPausedError, ConfirmationRequiredError
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.analysis import MatchResult, GreetingDraft
from app.models.action import ActionPayload
from app.services.filter_service import RuleFilter
from app.services.deduplication_service import deduplicate_jobs
from app.services.normalization_service import normalize_job
from app.services.analysis_service import JobAnalyzer
from app.services.matching_service import CandidateMatcher
from app.services.greeting_service import GreetingGenerator


class AgentState(TypedDict, total=False):
    """只存可序列化的数据，不把浏览器、连接或密钥写入检查点。"""

    run_id: str
    candidate: dict
    queries: list[str]
    source: str
    mode: str
    transport: str
    analysis_only: bool
    search_limit: int | None
    discovery: dict
    rejected_jobs: list[dict]
    source_warnings: list[str]
    jobs: list[dict]
    index: int
    results: list[dict]
    analysis: dict
    match: dict
    draft: dict | None
    action_id: str | None
    outcome: str
    status: str
    usage: list[dict]
    tool_events: list[dict]
    resume_search: dict
    profile_warnings: list[str]
    ranking: bool
    review_index: int
    review_count: int
    search_coverage: dict
    discovered_jobs: list[dict]


def build_graph(adapter, client, actions, approval, tracker, checkpointer):
    """依赖通过参数传入，因此更换平台不会改变图中的服务和边。"""
    def candidate(state):
        return CandidateProfile.model_validate(state["candidate"])

    def current_job(state):
        return JobPosting.model_validate(state["jobs"][state["index"]])

    def extract_profile(state):
        """提炼结果独立落到检查点，搜索或后续模型失败无需再次分析简历。"""
        from app.models.search import ResumeSearch
        from app.services.resume_service import analyze_resume
        start = len(client.usage)
        profile, queries, warnings = analyze_resume(client, ResumeSearch.model_validate(state["resume_search"]), state["run_id"])
        return {"candidate": profile.model_dump(mode="json"), "queries": queries, "profile_warnings": warnings,
                "usage": [item.model_dump() for item in client.usage[start:]], "status": "RUNNING"}

    def record_progress(state, target):
        """只前进自动流程的进度，不覆盖用户记录的面试、忽略或归档状态。"""
        stages = ["NEW", "ANALYZED", "SHORTLISTED", "CONTACT_READY", "CONTACTED"]
        application = tracker.track(candidate(state).id, current_job(state).id)
        if application.status not in stages:
            return
        for status in stages[stages.index(application.status) + 1:stages.index(target) + 1]:
            tracker.update_status(application.id, status, confirmed=True)

    def discover(state):
        """只读操作可在人工验证后重跑；绝不自动回答验证码。"""
        while True:
            try:
                jobs = adapter.search_jobs(state["queries"])
                break
            except BrowserPausedError as exc:
                interrupt({"kind": "browser", "message": str(exc), "source": state["source"]})
        # 扩大搜索时保留所有已读岗位（含已排除项），只为真正的新岗位调用模型。
        if state.get("ranking") and state.get("discovered_jobs"):
            existing = {job["id"]: JobPosting.model_validate(job) for job in state["discovered_jobs"]}
            existing.update({job.id: job for job in jobs})
            jobs = list(existing.values())
        discovered = [job.model_dump(mode="json") for job in jobs]
        profile = candidate(state)
        received = len(jobs)
        accepted, rejected = [], []
        for raw_job in jobs:
            job = normalize_job(raw_job)
            from app.services.ranking_service import search_filter
            decision = search_filter(profile, job) if state.get("ranking") else RuleFilter().evaluate(profile, job)
            if decision.passed:
                accepted.append(job)
            else:
                rejected.append({"job": job.model_dump(mode="json"), "reasons": decision.reasons})
        jobs = deduplicate_jobs(accepted)
        tracker.save_candidate(profile)
        tracker.save_jobs(jobs)
        normalized = []
        for job in jobs:
            job = job.model_copy(update={"id": tracker.resolve_job_id(job)})
            tracker.track(profile.id, job.id)
            normalized.append(job.model_dump(mode="json"))
        previous_results = list(state.get("results", [])) if state.get("ranking") else []
        processed = {row["job"]["id"] for row in previous_results}
        rejected_ids = {row["job"]["id"] for row in rejected}
        for row in state.get("rejected_jobs", []) if state.get("ranking") else []:
            if row["job"]["id"] not in rejected_ids:
                rejected.append(row)
                rejected_ids.add(row["job"]["id"])
        normalized = [row["job"] for row in previous_results] + [
            job for job in normalized if job["id"] not in processed and job["id"] not in rejected_ids]
        tools = getattr(adapter, "tools", adapter)
        return {"jobs": normalized, "index": len(previous_results), "results": previous_results,
                "discovered_jobs": discovered, "status": "RUNNING",
                "discovery": {"received": received, "rejected": len(rejected),
                              "duplicates": len(accepted) - len(jobs), "retained": len(jobs)},
                "rejected_jobs": rejected,
                "source_warnings": list(getattr(adapter, "read_warnings", [])),
                "search_coverage": dict(getattr(adapter, "search_coverage", {})),
                "tool_events": list(getattr(tools, "events", []))}

    def analyze(state):
        """模型提取后立即核对原文，再做确定性的候选人证据匹配。"""
        usage_start = len(client.usage)
        intent = state.get("resume_search", {}).get("intent") if state.get("ranking") else None
        analysis = JobAnalyzer(client).analyze(current_job(state), intent=intent)
        match = CandidateMatcher().match(candidate(state), current_job(state), analysis)
        if state.get("ranking"):
            from app.services.ranking_service import score_match
            match = score_match(candidate(state), current_job(state), analysis, match)
        record_progress(state, "SHORTLISTED" if match.shortlisted else "ANALYZED")
        return {"analysis": analysis.model_dump(mode="json"), "match": match.model_dump(mode="json"),
                "draft": None, "action_id": None,
                "outcome": "MATCHED" if state.get("analysis_only") and match.shortlisted else "NOT_SHORTLISTED",
                "usage": [*state.get("usage", []), *[item.model_dump() for item in client.usage[usage_start:]]]}

    def draft(state):
        usage_start = len(client.usage)
        value = GreetingGenerator(client).generate(candidate(state), current_job(state),
                                                    MatchResult.model_validate(state["match"]))
        return {"draft": value.model_dump(mode="json"),
                "usage": [*state.get("usage", []), *[item.model_dump() for item in client.usage[usage_start:]]]}

    def prepare(state):
        """草稿在上个节点已落盘，重放此节点不会再次调用模型改变正文。"""
        value = GreetingDraft.model_validate(state["draft"])
        action = actions.prepare(state["run_id"], ActionPayload(
            candidate=candidate(state), job=current_job(state), content=value.content,
            evidence_ids=value.evidence_ids, simulated=state["source"] == "mock"))
        record_progress(state, "CONTACT_READY")
        return {"action_id": action.id, "status": "WAITING_APPROVAL"}

    def review(state):
        """Resume 只让图继续；批准必须先通过审批存储的摘要核验。"""
        action = actions.get(state["action_id"])
        if action.status == "PENDING":
            interrupt({"kind": "approval", "action_id": action.id, "digest": action.digest})
            action = actions.get(action.id)
        if action.status == "PENDING":
            raise ConfirmationRequiredError("请先批准或拒绝当前草稿，再恢复任务")
        return {"status": "RUNNING"}

    def execute(state):
        while True:
            try:
                result = approval.execute(state["action_id"])
                if result.status in {"EXECUTING", "UNCERTAIN"}:
                    interrupt({"kind": "action_recovery", "action_id": result.id,
                               "message": "发送结果尚未确认，请到平台人工核查，再记录结果；禁止自动重发。"})
                    continue
                if result.status == "SUCCEEDED" and not result.payload.simulated:
                    record_progress(state, "CONTACTED")
                return {"outcome": result.status}
            except BrowserPausedError as exc:
                interrupt({"kind": "browser", "message": str(exc), "action_id": state["action_id"]})

    def advance(state):
        """每个岗位保留分析、证据和执行状态，之后处理下一个岗位。"""
        result = {"job": state["jobs"][state["index"]], "analysis": state["analysis"],
                  "match": state["match"], "draft": state.get("draft"),
                  "action_id": state.get("action_id"), "outcome": state["outcome"]}
        return {"index": state["index"] + 1, "results": [*state["results"], result],
                "analysis": {}, "match": {}, "draft": None, "action_id": None}

    def finish(state):
        return {"status": "COMPLETED"}

    def rank(state):
        """明确无关的职业留在排除记录；其余按分数排序，时间差距不淘汰。"""
        rows, rejected = [], list(state["rejected_jobs"])
        for row in state["results"]:
            if row["analysis"].get("intent_fit") == "unrelated":
                rejected.append({"job": row["job"], "reasons": ["岗位职业方向明显不同：" + row["analysis"]["intent_quote"]]})
            else:
                rows.append(row)
        rows.sort(key=lambda row: (-row["match"]["score"], row["job"]["id"]))
        discovery = dict(state["discovery"], rejected=len(rejected), retained=len(rows))
        return {"results": rows, "rejected_jobs": rejected, "discovery": discovery,
                "review_index": 0, "review_count": min(5, len(rows))}

    def refine(state):
        """每次只复核一条并保存，失败恢复不重跑已完成的其他岗位。"""
        from app.services.ranking_service import review_match
        start = len(client.usage)
        rows = list(state["results"])
        if rows[state["review_index"]].get("deep_review"):
            return {"review_index": state["review_index"] + 1}
        index = state["review_index"]
        rows[index] = {**rows[index], "deep_review": review_match(client, rows[index])}
        return {"results": rows, "review_index": index + 1,
                "usage": [*state.get("usage", []), *[item.model_dump() for item in client.usage[start:]]]}

    def remaining(state):
        return "analyze" if state["index"] < len(state["jobs"]) else "rank" if state.get("ranking") else "finish"

    graph = StateGraph(AgentState)
    for name, node in {"discover": discover, "analyze": analyze, "draft": draft,
                       "prepare": prepare, "review": review, "execute": execute,
                       "advance": advance, "extract_profile": extract_profile,
                       "rank": rank, "refine": refine, "finish": finish}.items():
        graph.add_node(name, node)
    graph.add_conditional_edges(START, lambda state: "extract_profile" if state.get("resume_search") else "discover",
                                ["extract_profile", "discover"])
    graph.add_edge("extract_profile", "discover")
    graph.add_conditional_edges("discover", remaining, ["analyze", "rank", "finish"])
    graph.add_conditional_edges("analyze", lambda state: "draft" if state["match"]["shortlisted"]
                                and not state.get("analysis_only", False) else "advance",
                                ["draft", "advance"])
    for start, end in [("draft", "prepare"), ("prepare", "review"), ("review", "execute"),
                       ("execute", "advance"), ("finish", END)]:
        graph.add_edge(start, end)
    graph.add_conditional_edges("advance", remaining, ["analyze", "rank", "finish"])
    for node in ("rank", "refine"):
        graph.add_conditional_edges(node, lambda state: "refine" if state["review_index"] < state["review_count"] else "finish",
                                    ["refine", "finish"])
    return graph.compile(checkpointer=checkpointer)
