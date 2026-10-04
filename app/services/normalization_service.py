"""按固定规则清理不同来源的岗位，使后续筛选和去重使用一致的数据。"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.job import JobPosting

# 这些已知参数只用于来源追踪，去掉后可减少同一岗位的重复链接。
TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "spm"})


def canonicalize_url(url: str) -> str:
    """生成用于比较的岗位链接，去掉已知追踪参数和页面锚点。

    保留 id、job_id、source、ref 等可能影响岗位身份的查询参数。
    统一协议和主机的大小写，并按查询参数排序，减少格式差异。
    路径大小写和末尾斜杠保持原样，因为服务器可能把它们视为不同地址。
    """
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in TRACKING_PARAMETERS
    ]
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path,
            urlencode(sorted(query)),
            "",
        )
    )


def normalize_job(job: JobPosting) -> JobPosting:
    """返回清理后的岗位副本，不修改适配器传入的原对象。

    去掉字符串首尾空白，整理展示字段中的多余空格，统一来源名称和链接。
    最后重新校验，确保清理后的数据仍满足 JobPosting 的要求。
    """
    cleaned = job.model_dump()
    for name, value in cleaned.items():
        if isinstance(value, str):
            cleaned[name] = value.strip()
    for name in ("title", "company", "city", "salary", "hr_activity"):
        if cleaned.get(name):
            cleaned[name] = " ".join(cleaned[name].split())
    cleaned["source"] = cleaned["source"].casefold()
    # 岗位描述保留换行结构，只清理每行末尾和全文首尾的空白。
    cleaned["description"] = "\n".join(
        line.rstrip() for line in cleaned["description"].splitlines()
    ).strip()
    cleaned["url"] = canonicalize_url(cleaned["url"])
    return JobPosting.model_validate(cleaned)
