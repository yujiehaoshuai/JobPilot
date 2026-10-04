"""牛客样本是合成数据，字段结构取自公开页面核对结果。"""

from pathlib import Path
import pytest
from app.adapters.nowcoder import NowcoderAdapter
from app.browser.session import BrowserSession
from app.browser.selectors import NOWCODER


def test_nowcoder_standardizes_internship_fields(tmp_path):
    adapter = NowcoderAdapter(BrowserSession(NOWCODER, tmp_path))
    root = Path("fixtures/browser")
    assert adapter.parse_links((root / "nowcoder_search.html").read_text("utf-8")) == ["100001"]
    job = adapter.parse_detail((root / "nowcoder_detail.html").read_text("utf-8"), "100001")
    assert job.city == "上海" and job.source == "nowcoder"
    assert job.required_days_per_week == 4 and job.internship_duration_months == 3
    assert "FastAPI" in job.description and "Python" in job.description
    assert job.employment_type == "internship"
    with pytest.raises(ValueError):
        adapter.detail_url("../other")
