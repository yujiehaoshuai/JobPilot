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


def test_dynamic_paging_uses_next_button_and_restarts_when_query_changes(make_job):
    from urllib.parse import parse_qs, urlsplit
    from types import SimpleNamespace
    from app.browser.selectors import NOWCODER_NEXT
    calls=[]
    def html(job_id,next_page=True):
        disabled="" if next_page else " disabled"
        return f'<a href="/jobs/detail/{job_id}">职位</a><div class="el-pagination"><button class="btn-next"{disabled}>下一页</button></div>'
    class Session:
        def validate_url(self,url):pass
        def read(self,url,selector):
            query=parse_qs(urlsplit(url).query)["search"][0]
            calls.append(("read",query))
            self.value=html("100" if query=="Python" else "200")
            self.page=SimpleNamespace(content=lambda:self.value)
            return self.value
        def read_next(self,next_selector,active_selector,number):
            assert next_selector==NOWCODER_NEXT and number==2
            calls.append(("next",number));self.value=html("101",False)
            return self.value
    adapter=NowcoderAdapter(Session(),limit=3)
    adapter.get_job_detail=lambda job_id: make_job(id=job_id,source_job_id=job_id)
    jobs=adapter.search_jobs(["Python","后端"])
    assert [job.id for job in jobs]==["100","200","101"]
    assert calls==[("read","Python"),("read","后端"),("read","Python"),("next",2)]
    assert adapter.search_coverage["pages"]==3
