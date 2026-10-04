"""评分逻辑独立于业务服务，输入预测与人工标签后计算指标。"""


def exact_set(predicted, expected) -> bool:
    """集合必须完全一致才算正确；额外猜出的技能也会扣分。"""
    return {v.strip().casefold() for v in predicted} == {v.strip().casefold() for v in expected}


def ratio(correct: int, total: int, scope: str):
    """分母为零表示尚未测量，不记成 0% 或 100%。"""
    return {"value": correct / total if total else None, "numerator": correct,
            "denominator": total, "scope": scope}


def evidence_errors(profile, match, draft):
    """同时核对编号和原文，防止合法编号下面夹带虚构经历。"""
    facts = {f"skills/{i}": skill.evidence for i, skill in enumerate(profile.skills)}
    claims = [(item.candidate_evidence_id, item.candidate_evidence)
              for item in match.evidence if item.candidate_evidence is not None]
    if draft:
        claims.extend(zip(draft.evidence_ids, draft.used_candidate_evidence, strict=True))
    invalid = sum(1 for key, quote in claims if key not in facts or facts[key] != quote)
    return invalid, len(claims)
