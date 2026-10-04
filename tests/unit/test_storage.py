"""验证数据库重开后的数据恢复、岗位去重，以及需要人工确认的状态修改。"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.enums import ApplicationStatus, EmploymentType
from app.exceptions import ConfirmationRequiredError, InvalidTransitionError, StorageError
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.storage.tracker import SQLiteTracker


@pytest.fixture
def candidate() -> CandidateProfile:
    """提供精简候选人资料，检查写入 JSON 后再读回是否丢失字段。"""
    return CandidateProfile(id="candidate-1", name="Demo Candidate", target_cities=["杭州"])


@pytest.fixture
def job() -> JobPosting:
    """提供含中文、可选字段和带时区日期的岗位，覆盖常见存储内容。"""
    return JobPosting(
        id="job-1",
        source="mock",
        source_job_id="platform-1",
        title="Agent Engineer 实习生",
        company="Demo Company",
        city="杭州",
        salary="200-300元/天",
        description="Python、RAG 与 Agent 应用开发。",
        url="https://example.com/jobs/1",
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
        employment_type=EmploymentType.INTERN,
        internship_duration_months=3,
        required_days_per_week=4,
    )


def test_profiles_jobs_and_application_survive_reopen(
    tmp_path: Path, candidate: CandidateProfile, job: JobPosting
) -> None:
    """关闭数据库再打开后，候选人、岗位和人工确认的申请状态都应保留。"""
    database = tmp_path / "nested" / "tracker.db"
    with SQLiteTracker(database) as tracker:
        tracker.save_candidate(candidate)
        assert tracker.save_jobs([job]) == 1
        application = tracker.track(candidate.id, job.id)
        updated = tracker.update_status(
            application.id,
            ApplicationStatus.SHORTLISTED,
            confirmed=True,
            notes="需要确认到岗时间",
        )
    with SQLiteTracker(database) as tracker:
        assert tracker.list_jobs() == [job]
        assert tracker.get_application(application.id) == updated
        assert tracker.list_applications(candidate.id) == [updated]
        assert tracker.list_applications("unknown") == []
        assert updated.created_at.tzinfo is not None
        assert updated.updated_at >= updated.created_at
    with sqlite3.connect(database) as connection:
        payload = connection.execute("SELECT data FROM candidates WHERE id = ?", (candidate.id,)).fetchone()[0]
    assert CandidateProfile.model_validate_json(payload) == candidate


def test_refresh_preserves_canonical_id_and_application_progress(
    tmp_path: Path, candidate: CandidateProfile, job: JobPosting
) -> None:
    """重新导入同一岗位时可更新内容，但不能重置进度、重复申请或断开关联。"""
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        tracker.save_candidate(candidate)
        assert tracker.save_jobs([job, job]) == 1
        application = tracker.track(candidate.id, job.id)
        updated = tracker.update_status(
            application.id, ApplicationStatus.IGNORED, confirmed=True, notes="暂不考虑"
        )
        refreshed = job.model_copy(update={"id": "regenerated-id", "title": "Updated title"})
        assert tracker.save_jobs([refreshed]) == 0
        tracker.save_candidate(candidate.model_copy(update={"name": "Updated name"}))
        persisted_job = tracker.list_jobs()[0]
        assert persisted_job.id == job.id
        assert persisted_job.title == refreshed.title
        assert tracker.track(candidate.id, persisted_job.id) == updated
        assert tracker.list_applications() == [updated]


def test_conflicting_job_id_rolls_back_entire_import(
    tmp_path: Path, job: JobPosting
) -> None:
    """同批数据出现标识冲突时应全部回滚，之前的插入和更新都不能残留。"""
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        tracker.save_jobs([job])
        new_job = job.model_copy(update={"id": "job-2", "source_job_id": "platform-2"})
        updated_job = job.model_copy(update={"title": "Should roll back"})
        conflicting_job = job.model_copy(update={"source_job_id": "different-platform-id"})
        with pytest.raises(StorageError, match="different platform job"):
            tracker.save_jobs([new_job, updated_job, conflicting_job])
        assert tracker.list_jobs() == [job]


def test_same_platform_id_on_different_sources_is_distinct(
    tmp_path: Path, job: JobPosting
) -> None:
    """不同招聘来源可以使用相同的平台岗位编号，不应被当成同一岗位。"""
    other = job.model_copy(update={
        "id": "other-job",
        "source": "second-mock",
        "url": "https://second-platform.example.invalid/jobs/platform-1",
    })
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        assert tracker.save_jobs([job, other]) == 2
        assert len(tracker.list_jobs()) == 2


def test_confirmation_and_lifecycle_reject_unapproved_or_impossible_changes(
    tmp_path: Path, candidate: CandidateProfile, job: JobPosting
) -> None:
    """缺少人工确认或状态跳转不合法时应拒绝修改，并完整保留原记录。"""
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        tracker.save_candidate(candidate)
        tracker.save_jobs([job])
        application = tracker.track(candidate.id, job.id)
        with pytest.raises(ConfirmationRequiredError):
            tracker.update_status(application.id, ApplicationStatus.SHORTLISTED)
        with pytest.raises(ConfirmationRequiredError):
            tracker.update_status(application.id, ApplicationStatus.NEW, notes="no approval")
        with pytest.raises(InvalidTransitionError):
            tracker.update_status(application.id, ApplicationStatus.OFFER, confirmed=True)
        assert tracker.get_application(application.id) == application
        archived = tracker.update_status(
            application.id, ApplicationStatus.ARCHIVED, confirmed=True
        )
        with pytest.raises(InvalidTransitionError):
            tracker.update_status(application.id, ApplicationStatus.NEW, confirmed=True)
        assert tracker.get_application(application.id) == archived


def test_notes_preserved_or_cleared_and_identical_write_is_idempotent(
    tmp_path: Path, candidate: CandidateProfile, job: JobPosting
) -> None:
    """未传备注时保留原值，空字符串用于清空；重复写入相同内容不改变记录。"""
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        tracker.save_candidate(candidate)
        tracker.save_jobs([job])
        application = tracker.track(candidate.id, job.id)
        shortlisted = tracker.update_status(
            application.id, ApplicationStatus.SHORTLISTED, confirmed=True, notes="reviewed"
        )
        ready = tracker.update_status(application.id, ApplicationStatus.CONTACT_READY, confirmed=True)
        assert ready.notes == shortlisted.notes
        assert tracker.update_status(ready.id, ready.status, confirmed=True) == ready
        cleared = tracker.update_status(ready.id, ready.status, confirmed=True, notes="")
        assert cleared.notes == ""


def test_application_requires_existing_candidate_and_job(
    tmp_path: Path, candidate: CandidateProfile, job: JobPosting
) -> None:
    """候选人或岗位不存在时，外键约束应阻止创建申请并回滚失败操作。"""
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        tracker.save_candidate(candidate)
        with pytest.raises(StorageError):
            tracker.track(candidate.id, job.id)
        tracker.save_jobs([job])
        with pytest.raises(StorageError):
            tracker.track("missing-candidate", job.id)
        assert tracker.list_applications() == []
        assert tracker.track(candidate.id, job.id).status == ApplicationStatus.NEW


def test_each_candidate_has_independent_progress(
    tmp_path: Path, candidate: CandidateProfile, job: JobPosting
) -> None:
    """两位候选人可跟踪同一岗位，修改其中一人的进度不应影响另一人。"""
    second = candidate.model_copy(update={"id": "candidate-2"})
    with SQLiteTracker(tmp_path / "tracker.db") as tracker:
        tracker.save_candidate(candidate)
        tracker.save_candidate(second)
        tracker.save_jobs([job])
        first_application = tracker.track(candidate.id, job.id)
        second_application = tracker.track(second.id, job.id)
        tracker.update_status(first_application.id, ApplicationStatus.IGNORED, confirmed=True)
        assert len(tracker.list_applications()) == 2
        assert tracker.get_application(second_application.id).status == ApplicationStatus.NEW
        with pytest.raises(StorageError, match="not found"):
            tracker.get_application("unknown")
