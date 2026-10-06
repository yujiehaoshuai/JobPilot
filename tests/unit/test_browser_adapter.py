"""浏览器契约测试：这些虚构样本不代表平台当前 DOM 已经验收。"""

from pathlib import Path
import pytest
from app.adapters.boss import BossAdapter
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS
from app.exceptions import JobParseError, SelectorChangedError


@pytest.fixture
def adapter(tmp_path):
    return BossAdapter(BrowserSession(BOSS, tmp_path))


def test_boss_links_and_detail(adapter):
    """只保留可信平台链接，且可解析中文岗位字段。"""
    base = Path("fixtures/browser")
    assert adapter.parse_links((base / "boss_search.html").read_text("utf-8")) == ["demo01"]
    job = adapter.parse_detail((base / "boss_detail.html").read_text("utf-8"), "demo01")
    assert job.company == "虚构示例公司"
    assert job.city == "杭州" and "Python" in job.description


def test_missing_structure_is_not_empty_search(adapter):
    with pytest.raises(SelectorChangedError):
        adapter.parse_links("<html>加载中</html>")
    assert adapter.parse_links('<div class="job-empty">暂无职位</div>') == []
    with pytest.raises(SelectorChangedError):
        adapter.parse_detail("<h1>缺少公司</h1>", "demo01")


def test_navigation_link_is_not_a_job(adapter):
    """导航和外站链接都不能充当有效岗位；有真实详情编号时才返回。"""
    navigation = '<a href="https://www.zhipin.com/job_detail/">职位搜索</a>'
    with pytest.raises(SelectorChangedError):
        adapter.parse_links(navigation)
    assert adapter.parse_links(navigation + '<a href="/job_detail/actual01.html">Python</a>') == ["actual01"]


@pytest.mark.parametrize("url", ["http://www.zhipin.com/", "https://www.zhipin.com.evil.test/",
                                      "https://user:pass@www.zhipin.com/", "file:///etc/passwd"])
def test_navigation_rejects_untrusted_urls(adapter, url):
    with pytest.raises(JobParseError):
        adapter.session.validate_url(url)
