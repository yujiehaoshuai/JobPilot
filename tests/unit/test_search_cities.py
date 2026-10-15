"""城市先传给网站，再在岗位层复核；续读缓存不能重复拉取已读详情。"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import pytest
from app.adapters.cities import normalize_cities, boss_search_cities
from app.adapters.shixiseng import ShixisengAdapter
from app.adapters.nowcoder import NowcoderAdapter
from app.exceptions import JobParseError


def test_city_aliases_and_boss_codes_are_explicit():
    assert normalize_cities([" 上海市 ", "上海", "杭州"]) == ["上海", "杭州"]
    assert boss_search_cities(["上海市", "杭州"]) == [
        {"name":"上海", "code":"101020100"}, {"name":"杭州", "code":"101210100"}]
    for cities in [["全国"], ["不存在的城市"], ["浙江省"]]:
        with pytest.raises(JobParseError):
            boss_search_cities(cities)


def test_city_search_uses_each_city_and_cached_details(make_job):
    seen, details = [], []
    class Reader:
        def validate_url(self,url): pass
        def read(self,url,selector):
            params = parse_qs(urlsplit(url).query)
            seen.append(params)
            city = params["city"][0]
            key = "sh" if city == "上海" else "hz"
            page = int(params.get("page", ["1"])[0])
            return f'<a href="/intern/inn_{key}{page}">岗位</a><div class="pagination-wrap"><button class="btn-next">下一页</button></div>'
    old = make_job(id="old", source_job_id="inn_sh1")
    adapter = ShixisengAdapter(Reader(), limit=4, cities=["上海市", "杭州"], known_jobs=[old])
    def detail(job_id):
        details.append(job_id)
        return make_job(id=job_id, source_job_id=job_id)
    adapter.get_job_detail = detail
    jobs = adapter.search_jobs(["Python & AI"])
    assert [job.source_job_id for job in jobs] == ["inn_sh1", "inn_sh2", "inn_sh3", "inn_hz1"]
    assert details == ["inn_sh2", "inn_sh3", "inn_hz1"]
    assert [value["city"] for value in seen] == [["上海"], ["上海"], ["上海"], ["杭州"]]
    assert all(value["keyword"] == ["Python & AI"] for value in seen)
    assert adapter.search_coverage["limit_reached"]


def test_nowcoder_resets_native_pagination_when_city_changes():
    calls = []
    class Reader:
        page = SimpleNamespace(content=lambda:"old page")
        def read(self,url,selector):
            calls.append(parse_qs(urlsplit(url).query))
            return "new page"
        def read_next(self,*args):
            calls.append("next")
            return "second page"
    adapter = NowcoderAdapter(Reader(), cities=["上海", "杭州"])
    adapter.read_search_page("Python", 1, "上海")
    adapter.read_search_page("Python", 2, "上海")
    adapter.read_search_page("Python", 2, "杭州")
    assert calls[0]["city"] == ["上海"] and calls[1] == "next"
    assert calls[2]["city"] == ["杭州"] and calls[3] == "next"


def test_expansion_counts_missing_and_unreadable_old_jobs_in_budget(make_job):
    """列表换了一批岗位时，旧额度仍算数；只允许读取新增加的 50 条。"""
    class Reader:
        def validate_url(self, url): pass
        def read(self, url, selector):
            return "".join(f'<a href="/intern/inn_new{i}">岗位</a>' for i in range(80))
    old = make_job(source_job_id="inn_old")
    adapter = ShixisengAdapter(Reader(), limit=52, cities=["上海"], known_jobs=[old],
        attempted_ids=["inn_old", "inn_unreadable"])
    downloads = []
    def detail(job_id):
        downloads.append(job_id)
        return make_job(id=job_id, source_job_id=job_id)
    adapter.get_job_detail = detail
    jobs = adapter.search_jobs(["Python"])
    assert len(downloads) == len(set(downloads)) == 50
    assert jobs[0] == old and len(jobs) == 51
    assert len(adapter.search_coverage["attempted_ids"]) == 52
    assert adapter.search_coverage["limit_reached"]
