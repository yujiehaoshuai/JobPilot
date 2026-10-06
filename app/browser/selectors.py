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
    # 导航栏也有 /job_detail/ 链接，只有含 .html 的详情链接才是候选岗位。
    links='a[href*="/job_detail/"][href*=".html"]', title=".job-banner .name h1",
    company=".sider-company .company-info a, .company-info a",
    description=".job-sec-text", city=".job-banner .text-city", salary=".job-banner .salary",
    empty=".job-empty, .search-empty",
)

# 只识别可见验证界面，不能因为普通 JD 提到了验证码技术就判为验证页。
CHALLENGE_SELECTORS = ('iframe[src*="captcha"]', '.geetest_panel', '#captcha',
                       '.verify-wrap', '.login-dialog', '.sign-form')
CHALLENGE_TITLES = ("安全验证", "人机验证", "登录", "访问异常", "Security Verification")

# 2026-10-05 核对牛客公开搜索和详情页；不触碰申请或私信控件。
NOWCODER = SiteSpec(
    source="nowcoder", home="https://www.nowcoder.com", hosts=("www.nowcoder.com", "nowcoder.com"),
    search_path="/jobs/intern/center?recruitType=2&search={query}",
    detail_pattern=r"/jobs/detail/([0-9]+)", links='a[href*="/jobs/detail/"]',
    title=".job-detail-wrap h1.title", company=".company-card .fs-20",
    description=".job-detail-infos .pre-line", city=".job-detail-wrap .extra .el-tooltip",
    salary=".job-detail-wrap .salary", empty=".job-list .el-empty, .job-list-empty",
)
NOWCODER_EXTRA = ".job-detail-wrap .extra"
