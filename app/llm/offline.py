"""有限词表的离线替身，用于可重复演示；不宣称具备模型的语义能力。"""

import re
from typing import Any
from app.llm.base import T
from app.models.analysis import Usage
from app.exceptions import StructuredOutputError

SKILLS = ("Python", "FastAPI", "RAG", "LangGraph", "Redis", "Docker", "SQL",
          "HTTP API", "PostgreSQL", "Java", "TypeScript", "Agent Evaluation")


class OfflineLLMClient:
    """按有限规则构造同样的数据结构，确保没有密钥也能运行核心流程。"""

    def __init__(self) -> None:
        self.usage: list[Usage] = []

    def complete(self, task: str, payload: dict[str, Any], schema: type[T]) -> T:
        """生成模拟结构化结果，用量为零且明确标记为 offline。"""
        if task == "greeting":
            raw = {"evidence_ids": payload["allowed_evidence_ids"][:3]}
        elif task == "resume":
            text = payload["text"]
            skills = []
            for line in text.splitlines():
                for skill in SKILLS:
                    if re.search(r"(?<![a-zA-Z])" + re.escape(skill) + r"(?![a-zA-Z])", line, re.I):
                        skills.append({"skill": skill, "quote": line, "level": "project_experience"})
            raw = {"name": None, "skills": skills[:40], "search_queries": [payload["intent"]]}
        elif task == "deep_review":
            raw = {"points": [{"evidence_index": index,
                "aspect": {"matched":"core", "partial":"learning", "missing":"gap"}[item["status"]]}
                for index, item in enumerate(payload["evidence"][:5])], "cautions": [], "questions": ["skill_depth"]}
        elif task in {"analyze", "search_analyze"}:
            description = payload["description"]
            evidence, required, preferred = [], [], []
            for skill in SKILLS:
                match = re.search(r"(?<![a-zA-Z])" + re.escape(skill) + r"(?![a-zA-Z])", description, re.I)
                if not match:
                    continue
                # 仅演示中用邻近文本识别加分项；真实模式交给模型提取。
                following = description[match.end():match.end() + 12]
                (preferred if "加分" in following or "优先" in following else required).append(skill)
                evidence.append({"skill": skill, "quote": match.group()})
            raw = {"required_skills": required, "preferred_skills": preferred,
                   "technologies": required + preferred, "evidence": evidence,
                   "agent_related": "agent" in description.lower(),
                   "llm_related": "llm" in description.lower() or "大模型" in description,
                   "backend_related": "后端" in description or "FastAPI" in description,
                   "risks": ["离线词表演示结果，尚未执行真实 LLM 语义分析"]}
            if task == "search_analyze":
                raw.update(intent_fit="unclear", intent_quote="")
        else:
            raise StructuredOutputError("离线模式不支持该任务")
        self.usage.append(Usage(provider="offline", cost=0))
        return schema.model_validate(raw)
