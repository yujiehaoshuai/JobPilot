"""公开 HTTP 与实习僧解析的离线契约，不代替真实网站可用性验收。"""

from pathlib import Path
import httpx
import pytest

from app.adapters.http_reader import PublicPageReader
from app.adapters.shixiseng import ShixisengAdapter
from app.browser.selectors import SHIXISENG
from app.exceptions import BrowserPausedError, JobParseError, SelectorChangedError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/browser"
SEARCH = (FIXTURES / "shixiseng_search.html").read_text("utf-8")
DETAIL = (FIXTURES / "shixiseng_detail.html").read_text("utf-8")
URL = "https://www.shixiseng.com/interns?keyword=Python"


@pytest.fixture(autouse=True)
def no_network_wait(monkeypatch):
    """只缩短离线测试的节流等待，生产请求仍至少间隔一秒。"""
    monkeypatch.setattr("app.adapters.http_reader.time.sleep", lambda _: None)


def html_response(body=DETAIL, status=200, **headers):
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8", **headers})


def test_search_reads_details_not_obfuscated_list_labels():
    requests = []
    def respond(request):
        requests.append(request)
        return html_response(SEARCH if request.url.path == "/interns" else DETAIL)
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        jobs = ShixisengAdapter(reader, limit=1).search_jobs(["Python / 实习"])
    assert len(requests) == 2 and all(item.method == "GET" for item in requests)
    assert requests[0].url.params["keyword"] == "Python / 实习"
    assert requests[1].url.query == b""
    job = jobs[0]
    assert job.title == "Python 实习生（虚构）" and job.company == "合成测试公司"
    assert job.required_days_per_week == 4 and job.internship_duration_months == 6
    assert job.city == "上海" and job.publish_time is None
    assert job.source == "shixiseng" and job.employment_type == "internship"


def test_links_deduplicate_and_discard_other_hosts():
    with PublicPageReader(SHIXISENG) as reader:
        assert ShixisengAdapter(reader).parse_links(SEARCH) == ["inn_demo1", "inn_demo2"]


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_restriction_pauses_without_retry(status):
    calls = []
    def respond(request):
        calls.append(request)
        return html_response(status=status)
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        with pytest.raises(BrowserPausedError, match=str(status)):
            reader.read(URL, SHIXISENG.links)
    assert len(calls) == 1


@pytest.mark.parametrize("target", ["https://outside.invalid/", "http://127.0.0.1/", "/login", "/intern/inn_demo1#fragment"])
def test_redirect_checked_before_next_request(target):
    calls = []
    def respond(request):
        calls.append(request)
        return html_response(status=302, location=target)
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        with pytest.raises(BrowserPausedError):
            reader.read(URL, SHIXISENG.links)
    assert len(calls) == 1


def test_permitted_redirect_is_bounded():
    calls = []
    def respond(request):
        calls.append(request)
        return html_response(status=302, location=URL)
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        with pytest.raises(JobParseError, match="跳转次数"):
            reader.read(URL, SHIXISENG.links)
    assert len(calls) == 4


@pytest.mark.parametrize("html,error", [
    ("<title>安全验证</title><div>请手动验证</div>", BrowserPausedError),
    ("<title>搜索</title><div>加载中</div>", SelectorChangedError),
])
def test_gate_or_shell_never_becomes_empty_success(html, error):
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(lambda _: html_response(html))) as reader:
        with pytest.raises(error):
            reader.read(URL, SHIXISENG.links)


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="a" * 2_000_001, headers={"content-type": "text/html"}),
    httpx.Response(200, json={"error": "not html"}),
    httpx.Response(200, content=b"\xff", headers={"content-type": "text/html"}),
    httpx.Response(503),
])
def test_invalid_response_is_explicit_error(response):
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(lambda _: response)) as reader:
        with pytest.raises(JobParseError):
            reader.read(URL, SHIXISENG.links)


def test_unreadable_required_text_stops_but_optional_text_stays_unknown():
    with PublicPageReader(SHIXISENG) as reader:
        adapter = ShixisengAdapter(reader)
        with pytest.raises(JobParseError, match="无法可靠解释"):
            adapter.parse_detail(DETAIL.replace("合成测试公司", "\ue123"), "inn_demo1")
        with pytest.raises(SelectorChangedError):
            adapter.parse_detail("<h1>结构改变</h1>", "inn_demo1")
        job = adapter.parse_detail(DETAIL.replace("150-200/天", "\ue123")
                                   .replace("4天／周", "\ue123天／周"), "inn_demo1")
        assert job.salary is None and job.required_days_per_week is None


def test_http_failure_does_not_retry_or_expose_request():
    def respond(request):
        raise httpx.ReadTimeout("private network detail", request=request)
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        with pytest.raises(JobParseError, match="公开页面读取失败") as exc:
            reader.read(URL, SHIXISENG.links)
    assert "private" not in str(exc.value)


@pytest.mark.parametrize("style,expected_empty", [("display:;", True), ("display:none;", False),
                                                    ("visibility: hidden", False)])
def test_only_visible_empty_placeholder_counts(style, expected_empty):
    html = f'<div class="primary-content"><div style="{style}"><img src="https://static.invalid/intern_default.test.png"></div></div>'
    with PublicPageReader(SHIXISENG) as reader:
        adapter = ShixisengAdapter(reader)
        if expected_empty:
            assert adapter.parse_links(html) == []
        else:
            with pytest.raises(SelectorChangedError):
                adapter.parse_links(html)


def test_two_pages_stop_at_limit_and_fetch_each_detail_once():
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.path == "/interns":
            ids = ["inn_one", "inn_two"] if "page" not in request.url.params else ["inn_two", "inn_three", "inn_four"]
            html = ''.join(f'<a href="/intern/{job_id}">岗位链接</a>' for job_id in ids)
            return html_response(html + '<div class="pagination-wrap"><button class="btn-next">下一页</button></div>')
        return html_response()
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        jobs = ShixisengAdapter(reader, limit=3).search_jobs(["Python"])
    assert [job.source_job_id for job in jobs] == ["inn_one", "inn_two", "inn_three"]
    assert [request.url.params.get("page") for request in requests[:2]] == [None, "2"]
    assert len(requests) == 5


@pytest.mark.parametrize("repeat,disabled,empty", [(True,False,False),(False,True,False),(False,False,True)])
def test_pagination_stops_on_repeat_last_page_or_empty(repeat, disabled, empty):
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.path != "/interns":
            return html_response()
        if empty:
            return html_response('<div class="primary-content"><div style="display:;"><img src="/intern_default.test.png"></div></div>')
        marker = " disabled" if disabled else ""
        return html_response('<a href="/intern/inn_one">链接</a><div class="pagination-wrap">'
                             f'<button class="btn-next"{marker}>下一页</button></div>')
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        jobs = ShixisengAdapter(reader).search_jobs(["Python"])
    assert len(jobs) == (0 if empty else 1)
    assert sum(request.url.path == "/interns" for request in requests) == (2 if repeat else 1)


def test_verification_on_second_page_pauses_before_detail_fetch():
    requests = []
    def respond(request):
        requests.append(request)
        if "page" in request.url.params:
            return html_response(status=403)
        return html_response('<a href="/intern/inn_one">链接</a><div class="pagination-wrap"><button class="btn-next">下一页</button></div>')
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        with pytest.raises(BrowserPausedError):
            ShixisengAdapter(reader).search_jobs(["Python"])
    assert len(requests) == 2 and all(request.url.path == "/interns" for request in requests)


def test_unreadable_detail_is_reported_and_other_jobs_survive():
    from app.tools.jobs import ToolCallingAdapter
    def respond(request):
        if request.url.path == "/interns":
            return html_response(SEARCH)
        body = DETAIL.replace("合成测试公司", "\ue123") if request.url.path.endswith("inn_demo1") else DETAIL
        return html_response(body)
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        tools = ToolCallingAdapter(ShixisengAdapter(reader))
        jobs = tools.search_jobs(["Python"])
        assert [job.source_job_id for job in jobs] == ["inn_demo2"]
        assert len(tools.read_warnings) == 1 and "inn_demo1" in tools.read_warnings[0]


def test_all_unreadable_details_are_not_empty_search_success():
    def respond(request):
        return html_response(SEARCH if request.url.path == "/interns" else DETAIL.replace("合成测试公司", "\ue123"))
    with PublicPageReader(SHIXISENG, transport=httpx.MockTransport(respond)) as reader:
        with pytest.raises(JobParseError, match="全部不可读"):
            ShixisengAdapter(reader).search_jobs(["Python"])
