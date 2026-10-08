"""读取公开 HTML；只发有限的 GET，不加载脚本、不使用浏览器登录资料。"""

import re
import time
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.browser.selectors import CHALLENGE_TITLES, SiteSpec
from app.exceptions import UnavailableJobError, BrowserPausedError, JobParseError, SelectorChangedError


class PublicPageReader:
    """给只读 Adapter 提供 HTML，遇到访问限制立即交回人工处理。"""

    def __init__(self, site: SiteSpec, *, transport=None, min_interval: float = 1.0):
        self.site = site
        self.min_interval = max(1.0, min_interval)
        self.last_request = 0.0
        self.client = httpx.Client(
            timeout=20, follow_redirects=False, transport=transport,
            headers={"User-Agent": "JobPilot/0.1 readonly-public-pages"},
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def validate_url(self, url: str) -> None:
        """地址必须是该平台的搜索或详情页；重定向也逐次检查。"""
        try:
            value = urlsplit(url)
            allowed = (value.scheme == "https" and value.hostname in self.site.hosts
                       and value.port in (None, 443) and not value.username and not value.password
                       and not value.fragment and not any(c.isspace() for c in url)
                       and (value.path == self.site.search_path.split("?")[0]
                            or re.fullmatch(self.site.detail_pattern, value.path)))
        except ValueError:
            allowed = False
        if not allowed:
            raise JobParseError("公开页面地址超出该平台的搜索和详情范围")

    def read(self, url: str, expected_selector: str) -> str:
        """每次至多三次站内跳转、两 MB 正文；错误不能伪装成空岗位列表。"""
        for _ in range(4):
            self.validate_url(url)
            time.sleep(max(0, self.min_interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.client.stream("GET", url) as response:
                    if response.status_code in {401, 403, 429}:
                        raise BrowserPausedError(
                            f"{self.site.source} 返回 HTTP {response.status_code}，已停止读取；"
                            "请人工确认访问条件，不自动重试或绕过验证")
                    if response.is_redirect:
                        target = urljoin(url, response.headers.get("location", ""))
                        try:
                            self.validate_url(target)
                        except JobParseError:
                            raise BrowserPausedError("页面跳往登录、验证或未允许的地址，已停止读取") from None
                        url = target
                        continue
                    if response.status_code in {404, 410} and re.fullmatch(self.site.detail_pattern, urlsplit(url).path):
                        raise UnavailableJobError("岗位详情已下线")
                    if response.status_code != 200:
                        raise JobParseError(f"公开页面返回 HTTP {response.status_code}，未获得岗位数据")
                    if "text/html" not in response.headers.get("content-type", "").lower():
                        raise JobParseError("公开页面没有返回 HTML，不能解析为岗位")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            raise JobParseError("公开页面正文超过两 MB，已停止读取")
                        chunks.append(chunk)
                    # 已验收平台使用 UTF-8；严格解码，避免将替换字符保存为 JD。
                    html = b"".join(chunks).decode("utf-8")
            except (httpx.HTTPError, UnicodeDecodeError):
                raise JobParseError("公开页面读取失败，请检查网络或页面编码后再试") from None
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            if any(text.casefold() in title.casefold() for text in CHALLENGE_TITLES):
                raise BrowserPausedError("公开页面要求登录或安全验证，已停止读取，请人工处理")
            if not soup.select_one(expected_selector):
                raise SelectorChangedError("HTML 没有预期岗位字段，可能需要登录、脚本加载或页面结构已改变")
            return html
        raise JobParseError("公开页面跳转次数过多，已停止读取")
