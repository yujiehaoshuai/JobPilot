"""验证提前关窗与驱动异常时，专用浏览器锁仍能可靠释放。"""

from unittest.mock import Mock
import pytest
from playwright.sync_api import Error
from app.browser.session import BrowserSession
from app.browser.selectors import BOSS
from app.exceptions import BrowserPausedError


def test_already_closed_context_releases_driver_and_lock(tmp_path):
    session = BrowserSession(BOSS, tmp_path)
    session.context, session.driver, session.profile_lock = Mock(), Mock(), Mock()
    session.context.close.side_effect = Error("Target page, context or browser has been closed")
    session.__exit__(None, None, None)
    session.driver.stop.assert_called_once()
    session.profile_lock.release.assert_called_once()


def test_driver_failure_still_releases_lock(tmp_path):
    session = BrowserSession(BOSS, tmp_path)
    session.driver, session.profile_lock = Mock(), Mock()
    session.driver.stop.side_effect = Error("driver failure")
    with pytest.raises(Error, match="driver failure"):
        session.__exit__(None, None, None)
    session.profile_lock.release.assert_called_once()


def test_closed_page_requires_manual_reopen(tmp_path):
    session = BrowserSession(BOSS, tmp_path)
    session.page = Mock()
    session.page.is_closed.return_value = True
    with pytest.raises(BrowserPausedError, match="已关闭"):
        session.ensure_ready()
