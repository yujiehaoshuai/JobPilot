"""按岗位循环的 LangGraph：读取、过滤、分析、草稿、审批、执行与记账。"""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from app.exceptions import BrowserPausedError, ConfirmationRequiredError
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.analysis import JobAnalysis, MatchResult, GreetingDraft
from app.models.action import ActionPayload
from app.services.filter_service import RuleFilter
from app.services.deduplication_service import deduplicate_jobs
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


def build_graph(adapter, client, actions, approval, tracker, checkpointer):
    """依赖通过参数传入，因此更换平台不会改变图中的服务和边。"""
    def candidate(state):
        return CandidateProfile.model_validate(state["candidate"])

    def current_job(state):
        return JobPosting.model_validate(state["jobs"][state["index"]])

    def discover(state):
        """只读操作可在人工验证后重跑；绝不自动回答验证码。"""
        while True:
            try:
                jobs = adapter.search_jobs(state["queries"])
                break
            except BrowserPausedError as exc:
                interrupt({"kind": "browser", "message": str(exc), "source": state["source"]})
        profile = candidate(state)
        jobs = deduplicate_jobs([job for job in jobs if RuleFilter().evaluate(profile, job).passed])
        tracker.save_candidate(profile)
        tracker.save_jobs(jobs)
        normalized = []
        for job in jobs:
            job = job.model_copy(update={"id": tracker.resolve_job_id(job)})
            tracker.track(profile.id, job.id)
            normalized.append(job.model_dump(mode="json"))
        tools = getattr(adapter, "tools", adapter)
        return {"jobs": normalized, "index": 0, "results": [], "status": "RUNNING",
                "tool_events": list(getattr(tools, "events", []))}

    def analyze(state):
        """模型提取后立即核对原文，再做确定性的候选人证据匹配。"""
        usage_start = len(client.usage)
        analysis = JobAnalyzer(client).analyze(current_job(state))
        match = CandidateMatcher().match(candidate(state), current_job(state), analysis)
        return {"analysis": analysis.model_dump(mode="json"), "match": match.model_dump(mode="json"),
                "draft": None, "action_id": None, "outcome": "NOT_SHORTLISTED",
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

    def remaining(state):
        return "analyze" if state["index"] < len(state["jobs"]) else "finish"

    graph = StateGraph(AgentState)
    for name, node in {"discover": discover, "analyze": analyze, "draft": draft,
                       "prepare": prepare, "review": review, "execute": execute,
                       "advance": advance, "finish": finish}.items():
        graph.add_node(name, node)
    graph.add_edge(START, "discover")
    graph.add_conditional_edges("discover", remaining, ["analyze", "finish"])
    graph.add_conditional_edges("analyze", lambda state: "draft" if state["match"]["shortlisted"] else "advance",
                                ["draft", "advance"])
    for start, end in [("draft", "prepare"), ("prepare", "review"), ("review", "execute"),
                       ("execute", "advance"), ("finish", END)]:
        graph.add_edge(start, end)
    graph.add_conditional_edges("advance", remaining, ["analyze", "finish"])
    return graph.compile(checkpointer=checkpointer)
