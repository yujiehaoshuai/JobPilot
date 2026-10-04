"""集中维护平台页面结构；选择器失效时修改这里，不改业务服务。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteSpec:
    """一个平台的只读页面契约，字段名对应统一岗位模型。"""

    source: str
    home: str
    hosts: tuple[str, ...]
    search_path: str
    detail_pattern: str
    links: str
    title: str
    company: str
    description: str
    city: str
    salary: str
    empty: str


# 这些选择器需要用户登录后的真实页面验收；测试样本只证明解析契约。
BOSS = SiteSpec(
    source="boss", home="https://www.zhipin.com", hosts=("www.zhipin.com", "zhipin.com"),
    search_path="/web/geek/job?query={query}",
    detail_pattern=r"/job_detail/([A-Za-z0-9_-]+)\.html",
    links='a[href*="/job_detail/"]', title=".job-banner .name h1",
    company=".sider-company .company-info a, .company-info a",
    description=".job-sec-text", city=".job-banner .text-city", salary=".job-banner .salary",
    empty=".job-empty, .search-empty",
)

# 只识别可见验证界面，不能因为普通 JD 提到了验证码技术就判为验证页。
CHALLENGE_SELECTORS = ('iframe[src*="captcha"]', '.geetest_panel', '#captcha',
                       '.verify-wrap', '.login-dialog', '.sign-form')
CHALLENGE_TITLES = ("安全验证", "人机验证", "登录", "访问异常", "Security Verification")
