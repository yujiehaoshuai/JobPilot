"""检验结构化输出和证据边界，避免模型幻觉流入候选人描述。"""

import json
from urllib.error import HTTPError
import pytest
from app.exceptions import LLMError, StructuredOutputError
from app.llm.client import CompatibleLLMClient, strict_schema
from app.llm.offline import OfflineLLMClient
from app.models.analysis import JobAnalysis, GreetingPlan
from app.models.candidate import CandidateSkill
from app.services.analysis_service import JobAnalyzer
from app.services.matching_service import CandidateMatcher
from app.services.greeting_service import GreetingGenerator


def test_offline_analysis_match_and_greeting_are_grounded(candidate, make_job):
    """实际串联三个服务，证据必须原样来自候选人资料。"""
    candidate.skills = [CandidateSkill(skill="Python", level="project_experience", evidence="课程中编写 Python 工具"),
                        CandidateSkill(skill="RAG", level="learning", evidence="正在学习 RAG 教程")]
    job = make_job(description="需要 Python、RAG 和 Redis。")
    client = OfflineLLMClient()
    analysis = JobAnalyzer(client).analyze(job)
    match = CandidateMatcher().match(candidate, job, analysis)
    assert match.matched_skills == ["Python"]
    assert match.partial_skills == ["RAG"]
    assert match.missing_skills == ["Redis"]
    draft = GreetingGenerator(client).generate(candidate, job, match)
    assert draft.used_candidate_evidence == [item.evidence for item in candidate.skills]
    assert "Redis" not in draft.content
    assert draft.status == "DRAFT"


class FixedClient:
    """返回预设的恶意结构，用于检验证据拒绝逻辑。"""
    usage = []

    def __init__(self, result):
        self.result = result

    def complete(self, task, payload, schema):
        return schema.model_validate(self.result)


@pytest.mark.parametrize("result", [
    {"required_skills": ["Docker"], "evidence": []},
    {"required_skills": ["Docker"], "evidence": [{"skill": "Docker", "quote": "需要 Docker"}]},
    {"required_skills": ["Docker"], "evidence": [{"skill": "Docker", "quote": "需要 Python"}]},
])
def test_reject_fabricated_jd_evidence(make_job, result):
    """缺少引用、伪造引用或引用不含技能时，都不接受结果。"""
    with pytest.raises(StructuredOutputError):
        JobAnalyzer(FixedClient(result)).analyze(make_job(description="需要 Python"))


def test_reject_fabricated_candidate_evidence(candidate, make_job):
    """模型即使给出合法 JSON，也不能引用不存在的经历。"""
    candidate.skills = [CandidateSkill(skill="Python", level="learning", evidence="学习 Python")]
    job = make_job(description="需要 Python")
    match = CandidateMatcher().match(candidate, job, JobAnalyzer(OfflineLLMClient()).analyze(job))
    with pytest.raises(StructuredOutputError):
        GreetingGenerator(FixedClient({"evidence_ids": ["skills/99"]})).generate(candidate, job, match)


def test_no_overlap_refuses_greeting(candidate, make_job):
    """空技能资料不能获得编造的优势或沟通经历。"""
    job = make_job()
    client = OfflineLLMClient()
    match = CandidateMatcher().match(candidate, job, JobAnalyzer(client).analyze(job))
    with pytest.raises(StructuredOutputError):
        GreetingGenerator(client).generate(candidate, job, match)


def test_compatible_client_uses_json_schema_and_validates_response(monkeypatch):
    """不访问网络，核对实际发出的协议以及 Pydantic 校验。"""
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, size):
            return json.dumps({"choices": [{"finish_reason": "stop", "message": {
                "content": '{"evidence_ids":["skills/0"]}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
    class Opener:
        def open(self, request, timeout):
            body = json.loads(request.data)
            assert body["response_format"]["json_schema"]["strict"] is True
            assert request.get_header("Authorization") == "Bearer private-test-key"
            return Response()
    monkeypatch.setattr("app.llm.client.build_opener", lambda *args: Opener())
    client = CompatibleLLMClient("https://example.invalid/v1", "test-model", "private-test-key")
    assert client.complete("greeting", {}, GreetingPlan).evidence_ids == ["skills/0"]
    assert client.usage[0].input_tokens == 10


def test_http_error_does_not_leak_api_key(monkeypatch):
    """服务器错误内容和密钥不得进入展示给用户的错误消息。"""
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError("https://example.invalid", 401, "private-key", {}, None)
    monkeypatch.setattr("app.llm.client.build_opener", lambda *args: Opener())
    with pytest.raises(LLMError, match="401") as failure:
        CompatibleLLMClient("https://example.invalid", "test", "private-key").complete("analyze", {}, JobAnalysis)
    assert "private-key" not in str(failure.value)


def test_strict_schema_requires_nullable_fields():
    """可选字段也列入 required，但仍允许值为 null。"""
    schema = strict_schema(JobAnalysis.model_json_schema())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
