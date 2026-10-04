"""用错误预测检验评分器，防止指标始终返回满分。"""

from app.evaluation.metrics import exact_set, ratio, evidence_errors
from app.evaluation.runner import evaluate
from app.models.analysis import MatchResult, MatchEvidence


def test_metric_penalizes_extra_and_missing_skills():
    assert exact_set(["python"], ["Python"])
    assert not exact_set(["Python", "Go"], ["Python"])
    assert not exact_set([], ["Python"])
    assert ratio(0, 0, "未测")["value"] is None


def test_metric_detects_fabricated_candidate_evidence(candidate):
    match = MatchResult(job_id="1", recommendation_reason="test", shortlisted=True,
                        evidence=[MatchEvidence(requirement="Python", jd_quote="Python",
                            candidate_evidence_id="skills/999", candidate_evidence="虚构工作经验", status="matched")])
    assert evidence_errors(candidate, match, None) == (1, 1)


def test_report_contains_all_metrics_and_discloses_offline_limits():
    report = evaluate(workflow=False)
    assert len(report["metrics"]) == 13
    assert report["metrics"]["Hallucinated Candidate Evidence Rate"]["value"] == 0
    assert 0 < report["metrics"]["JD Extraction Accuracy"]["value"] < 1
    assert report["metrics"]["Browser Action Success Rate"]["value"] is None
