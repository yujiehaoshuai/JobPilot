"""不调用真实模型，核对 DeepSeek 协议、完整输出和本地证据校验。"""

import json
from unittest.mock import Mock

import pytest

from app.exceptions import StructuredOutputError
from app.llm.client import CompatibleLLMClient
from app.models.analysis import JobAnalysis
from app.services.analysis_service import JobAnalyzer


def response_for(content):
    """模拟服务商的完整答复，包含可选的思考项及独立用量字段。"""
    return {"status": "completed", "output": [
        {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "不应解析的内容"}]},
        {"type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": json.dumps(content)}]}],
        "usage": {"input_tokens": 100, "output_tokens": 20}}


def install_response(monkeypatch, raw):
    """记录 HTTP 请求，避免测试费用及外部网络依赖。"""
    response = Mock()
    response.read.return_value = json.dumps(raw).encode()
    opener = Mock()
    opener.open.return_value.__enter__ = Mock(return_value=response)
    opener.open.return_value.__exit__ = Mock(return_value=None)
    monkeypatch.setattr("app.llm.client.build_opener", lambda *args: opener)
    return opener


def test_deepseek_responses_and_grounded_analysis(monkeypatch, make_job):
    raw = response_for({"required_skills": ["Python"],
                        "evidence": [{"skill": "Python", "quote": "需要 Python"}]})
    opener = install_response(monkeypatch, raw)
    client = CompatibleLLMClient("https://api.deepseek.com", "deepseek-flash", "test-private-key",
                                 api_style="responses", input_price=1, output_price=2)
    assert JobAnalyzer(client).analyze(make_job(description="需要 Python")).required_skills == ["Python"]
    request = opener.open.call_args.args[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.deepseek.com/responses"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert body["reasoning"] == {"effort": "none"}
    assert body["max_output_tokens"] == 4096
    assert "messages" not in body and "response_format" not in body
    assert json.loads(body["input"][1]["content"]) == {"description": "需要 Python"}
    assert client.usage[0].input_tokens == 100 and client.usage[0].output_tokens == 20
    assert client.usage[0].cost == pytest.approx(0.00014)


@pytest.mark.parametrize("variant", ["incomplete", "failed", "refusal", "tool", "multiple", "empty", "invalid_json", "wrong_schema", "forged_quote"])
def test_deepseek_rejects_unusable_or_fabricated_output(monkeypatch, make_job, variant):
    raw = response_for({"required_skills": ["Python"], "evidence": [{"skill": "Python", "quote": "需要 Python"}]})
    if variant in {"incomplete", "failed"}:
        raw["status"] = variant
    elif variant == "refusal":
        raw["output"][1]["content"] = [{"type": "refusal", "refusal": "拒答"}]
    elif variant == "tool":
        raw["output"].append({"type": "function_call"})
    elif variant == "multiple":
        raw["output"].append(raw["output"][1])
    elif variant == "empty":
        raw["output"] = []
    else:
        raw["output"][1]["content"][0]["text"] = {
            "invalid_json": "```json\n{}\n```", "wrong_schema": '{"required_skills": 123}',
            "forged_quote": '{"required_skills":["Docker"],"evidence":[{"skill":"Docker","quote":"需要 Docker"}]}'
        }[variant]
    install_response(monkeypatch, raw)
    client = CompatibleLLMClient("https://api.deepseek.com", "deepseek-flash", "test-key", api_style="responses")
    with pytest.raises(StructuredOutputError):
        JobAnalyzer(client).analyze(make_job(description="需要 Python"))
