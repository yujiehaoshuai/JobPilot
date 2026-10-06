"""给评估结果设置明确门槛；未测量和无效数值不能被当成通过。"""

import math


def finite_number(value) -> bool:
    """拒绝布尔值、NaN 和无穷大，避免比较表达式意外放行。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def assess_report(report: dict, thresholds: dict, *, browser_required=False) -> dict:
    """按每项指标独立判定，保留失败原因；强制检查候选人证据为零幻觉。"""
    if not isinstance(thresholds, dict) or not thresholds:
        raise ValueError("评估阈值必须是非空对象")
    rules = dict(thresholds)
    # 即使自定义阈值遗漏此项，也不能关闭证据门禁。
    rules["Hallucinated Candidate Evidence Rate"] = {"max": 0.0}
    if browser_required:
        rules["Browser Action Success Rate"] = {"min": 1.0}
    checks = []
    metrics = report["metrics"]
    for name, bounds in rules.items():
        if name not in metrics or not isinstance(bounds, dict) or not bounds:
            raise ValueError("阈值包含未知指标或空规则")
        if set(bounds) - {"min", "max"} or not all(finite_number(v) for v in bounds.values()):
            raise ValueError("阈值只接受 min/max 与有限数值")
        if bounds.get("min", -math.inf) > bounds.get("max", math.inf):
            raise ValueError("指标最小阈值不能大于最大阈值")
        metric = metrics[name]
        value = metric.get("value")
        if name == "Token Usage":
            tokens = [metric.get("input_tokens"), metric.get("output_tokens")]
            value = sum(tokens) if all(finite_number(v) and v >= 0 for v in tokens) else None
        reason = "达到阈值"
        measured = finite_number(value) and value >= 0
        if "denominator" in metric:
            denominator = metric["denominator"]
            numerator = metric.get("numerator")
            # 同时核对计数和值，防止零样本、错误分母或伪造比例通过。
            measured = (measured and finite_number(denominator) and denominator > 0
                        and finite_number(numerator) and 0 <= numerator <= denominator
                        and math.isclose(value, numerator / denominator, abs_tol=1e-12))
        if not measured:
            passed, reason = False, "未测量或指标数值无效"
        else:
            passed = bounds.get("min", -math.inf) <= value <= bounds.get("max", math.inf)
            if not passed:
                reason = "未达到阈值"
        checks.append({"metric": name, "value": value, "threshold": bounds,
                       "passed": passed, "reason": reason})
    return {"passed": all(item["passed"] for item in checks), "checks": checks}
