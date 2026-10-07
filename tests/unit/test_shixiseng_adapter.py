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
