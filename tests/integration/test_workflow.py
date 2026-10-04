"""离线运行真实命令行程序，并跨进程重开数据库，检查完整流程和持久化结果。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.enums import ApplicationStatus
from app.storage.tracker import SQLiteTracker

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_cli(database: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """用当前解释器启动独立进程，并隔离配置与数据库，避免影响用户演示数据。"""
    environment = os.environ.copy()
    environment.update({
        "DATABASE_URL": "sqlite:///data/unused-test.db",
        "LOG_LEVEL": "INFO",
        "CANDIDATE_PROFILE_PATH": str(PROJECT_ROOT / "fixtures/candidate.example.json"),
        "MOCK_JOBS_PATH": str(PROJECT_ROOT / "fixtures/jobs"),
    })
    # 不额外设置输出编码，验证命令行程序自身能处理 Windows 管道中的中文输出。
    return subprocess.run(
        [sys.executable, "-m", "app.main", "--database", str(database), *arguments],
        cwd=PROJECT_ROOT, env=environment, capture_output=True, encoding="utf-8",
        timeout=20, check=False,
    )


def test_demo_persists_and_rerun_preserves_confirmed_progress(tmp_path: Path) -> None:
    """验证完整演示、人工确认和重复运行，确保数据库不会丢进度或新增重复记录。"""
    database = tmp_path / "tracker.db"
    first = run_cli(database)
    assert first.returncode == 0, first.stderr
    for expected in ("Jobs loaded: 20", "Remaining: 13", "Duplicates removed: 2",
                     "Final: 11", "New jobs saved: 11", "Applications tracked: 11",
                     "当前不会连接真实招聘网站", "演示候选人"):
        assert expected in first.stdout
    assert "run_id=" in first.stderr and "result=success" in first.stderr
    with SQLiteTracker(database) as tracker:
        jobs = tracker.list_jobs()
        applications = tracker.list_applications()
    assert len(jobs) == len(applications) == 11
    assert all(application.status == ApplicationStatus.NEW for application in applications)
    application = applications[0]

    # 单独启动进程修改状态，确认缺少人工确认时数据库保持原样。
    unapproved = run_cli(database, "--set-status", application.id, "IGNORED")
    assert unapproved.returncode == 1
    assert "confirmation" in unapproved.stderr
    with SQLiteTracker(database) as tracker:
        assert tracker.get_application(application.id) == application

    approved = run_cli(database, "--set-status", application.id, "IGNORED", "--confirm")
    assert approved.returncode == 0, approved.stderr
    # 再次运行导入流程，检查之前进程保存的状态和申请标识仍然有效。
    second = run_cli(database)
    assert second.returncode == 0, second.stderr
    assert "New jobs saved: 0" in second.stdout
    with SQLiteTracker(database) as tracker:
        assert len(tracker.list_jobs()) == len(tracker.list_applications()) == 11
        assert tracker.get_application(application.id).status == ApplicationStatus.IGNORED
        assert {row.id for row in tracker.list_applications()} == {row.id for row in applications}
    listing = run_cli(database, "--list-applications")
    assert listing.returncode == 0
    assert application.id in listing.stdout and "IGNORED" in listing.stdout


@pytest.mark.parametrize("contents", [b'{"name":"SECRET-CANDIDATE"}', b'\xff\xfe\xff'])
def test_bad_candidate_has_actionable_error_without_private_content(
    tmp_path: Path, contents: bytes
) -> None:
    """分别检查资料字段缺失和编码错误；提示要能定位文件，但不能泄露资料内容。"""
    profile = tmp_path / "bad-candidate.json"
    profile.write_bytes(contents)
    database = tmp_path / "tracker.db"
    result = run_cli(database, "--candidate", str(profile))
    assert result.returncode == 1
    assert profile.name in result.stderr
    assert "SECRET-CANDIDATE" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not database.exists()


def test_missing_candidate_is_reported_without_creating_database(tmp_path: Path) -> None:
    """候选人文件不存在时应尽早报错，并且不创建数据库。"""
    database = tmp_path / "tracker.db"
    result = run_cli(database, "--candidate", str(tmp_path / "missing.json"))
    assert result.returncode == 1
    assert "missing.json" in result.stderr
    assert not database.exists()


def test_malformed_job_batch_does_not_save_partial_records(tmp_path: Path) -> None:
    """岗位批次解析失败时，不应留下部分岗位或申请记录。"""
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "broken.json").write_text("{broken", encoding="utf-8")
    database = tmp_path / "tracker.db"
    result = run_cli(database, "--jobs", str(jobs))
    assert result.returncode == 1
    assert "broken.json" in result.stderr and "Traceback" not in result.stderr
    with SQLiteTracker(database) as tracker:
        assert tracker.list_jobs() == []
        assert tracker.list_applications() == []


def test_confirmation_cannot_be_given_without_specific_action(tmp_path: Path) -> None:
    """只有确认参数却没有具体操作时，应报告参数错误且不创建数据库。"""
    database = tmp_path / "tracker.db"
    result = run_cli(database, "--confirm")
    assert result.returncode == 2
    assert not database.exists()


def test_url_alias_in_later_import_keeps_existing_application(tmp_path: Path) -> None:
    """分次导入同一网址但平台编号不同的岗位时，应保留原岗位及人工处理进度。"""
    first_batch, second_batch = tmp_path / "first", tmp_path / "second"
    first_batch.mkdir()
    second_batch.mkdir()
    fixtures = PROJECT_ROOT / "fixtures" / "jobs"
    (first_batch / "job.json").write_bytes((fixtures / "02_llm_application.json").read_bytes())
    (second_batch / "job.json").write_bytes((fixtures / "13_llm_url_duplicate.json").read_bytes())
    database = tmp_path / "tracker.db"
    first = run_cli(database, "--jobs", str(first_batch))
    assert first.returncode == 0, first.stderr
    with SQLiteTracker(database) as tracker:
        original_job = tracker.list_jobs()[0]
        original = tracker.list_applications()[0]
        reviewed = tracker.update_status(original.id, ApplicationStatus.IGNORED, confirmed=True)
    # 第二批在新进程中导入，确保去重依据已落库，而非只存在于内存中。
    second = run_cli(database, "--jobs", str(second_batch))
    assert second.returncode == 0, second.stderr
    assert "New jobs saved: 0" in second.stdout
    with SQLiteTracker(database) as tracker:
        assert len(tracker.list_jobs()) == 1
        assert tracker.list_jobs()[0].id == original_job.id
        assert tracker.list_applications() == [reviewed]
