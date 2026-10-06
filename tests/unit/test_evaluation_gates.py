"""用质量下降、零样本和模型错误验证门禁不会静默通过。"""

import json
import pytest
from app.evaluation.gates import assess_report
from app.evaluation.metrics import ratio
from app.evaluation import runner
from app.exceptions import StructuredOutputError


def report():
    return {"metrics": {"JD Extraction Accuracy": ratio(4, 6, "虚构样本"),
        "Hallucinated Candidate Evidence Rate": ratio(0, 10, "虚构证据"),
        "Browser Action Success Rate": ratio(0, 0, "未测量"),
        "Cost": {"value": None}}}


def test_gate_enforces_evidence_even_when_custom_rules_omit_it():
    value = report()
    rules = {"JD Extraction Accuracy": {"min": 2 / 3}}
    assert assess_report(value, rules)["passed"]
    value["metrics"]["Hallucinated Candidate Evidence Rate"] = ratio(1, 10, "造假")
    assert not assess_report(value, rules)["passed"]


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, -1],
                         ids=["unknown", "nan", "infinity", "boolean", "negative"])
def test_unknown_or_invalid_measurement_cannot_pass(value):
    data = report()
    data["metrics"]["JD Extraction Accuracy"]["value"] = value
    assert not assess_report(data, {"JD Extraction Accuracy": {"min": 0}})["passed"]


def test_gate_requires_samples_browser_success_and_known_budget():
    data = report()
    rules = {"JD Extraction Accuracy": {"min": 2 / 3}}
    assert not assess_report(data, rules, browser_required=True)["passed"]
    assert not assess_report(data, {"Cost": {"max": 1}})["passed"]
    data["metrics"]["Hallucinated Candidate Evidence Rate"] = {"value": 0, "numerator": 0, "denominator": 0}
    assert not assess_report(data, rules)["passed"]


def test_gate_flags_regression_and_rejects_mistyped_rules():
    assert not assess_report(report(), {"JD Extraction Accuracy": {"min": 1}})["passed"]
    for rules in [{"unknown": {"min": 0}}, {"Cost": {"min": 2, "max": 1}},
                  {"Cost": {"max": float("nan")}}, {}]:
        with pytest.raises(ValueError):
            assess_report(report(), rules)


def test_failed_evaluation_replaces_stale_success_report(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text('{"status":"passed"}', encoding="utf-8")
    def fail(*args, **kwargs):
        raise StructuredOutputError("不可泄露的供应商响应")
    monkeypatch.setattr(runner, "evaluate", fail)
    monkeypatch.setattr("sys.argv", ["evaluation", "--output", str(path)])
    assert runner.main() == 1
    result = json.loads(path.read_text("utf-8"))
    assert result["status"] == "failed" and result["error_type"] == "StructuredOutputError"
    assert "不可泄露" not in path.read_text("utf-8")
