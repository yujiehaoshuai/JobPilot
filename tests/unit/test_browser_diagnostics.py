"""诊断只保留导航类别，不能把 URL 中的认证资料带入报告。"""

import pytest
from app.browser.diagnostics import target_kind
from app.browser.selectors import BOSS


@pytest.mark.parametrize("url, expected", [
    ("https://www.zhipin.com/web/geek/jobs?token=private#secret", "platform_page"),
    ("about:blank", "blank"),
    ("https://unknown.example/login?token=private", "other_page"),
    ("https://[broken", "other_page"),
])
def test_diagnostic_target_never_exposes_url(url, expected):
    assert target_kind(url, BOSS) == expected
