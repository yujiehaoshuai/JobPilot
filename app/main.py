"""程序入口：把读取、筛选、去重和保存串成一条清晰的数据流。

建议先阅读 run_search，再顺着函数调用查看模型、服务和存储模块。
这里负责命令行交互和流程安排，具体业务规则交给对应模块处理。
"""

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError

from app.adapters.base import JobSourceAdapter
from app.adapters.mock.adapter import MockJobAdapter
from app.config import PROJECT_ROOT, Settings, load_settings
from app.enums import ApplicationStatus
from app.exceptions import ConfigurationError, JobPilotError
from app.logging_config import configure_logging
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.services.deduplication_service import deduplicate_jobs
from app.services.filter_service import RuleFilter
from app.services.normalization_service import normalize_job
from app.storage.tracker import SQLiteTracker


def load_candidate(path: Path) -> CandidateProfile:
    """读取候选人 JSON，并转换为通过校验的 CandidateProfile。

    path 是本地文件路径；返回值包含候选人的资料和求职条件。
    校验失败时只显示出错字段，避免把完整个人资料写进错误日志。
    """
    try:
        # utf-8-sig 也能读取带 BOM 的 UTF-8 文件，兼容部分 Windows 编辑器。
        return CandidateProfile.model_validate_json(path.read_text(encoding="utf-8-sig"))
    except ValidationError as exc:
        fields = ", ".join(".".join(str(part) for part in error["loc"])
                           or "JSON" for error in exc.errors())
        raise ConfigurationError(f"候选人配置无效：{path}（字段：{fields}）") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(f"无法读取 UTF-8 候选人配置：{path}（{type(exc).__name__}）") from exc


def run_search(
    candidate: CandidateProfile,
    adapter: JobSourceAdapter,
    tracker: SQLiteTracker,
    logger: logging.LoggerAdapter,
) -> None:
    """完成一轮本地搜索：读取 → 标准化 → 筛选 → 去重 → 保存。

    candidate 提供筛选条件，adapter 提供岗位，tracker 负责保存记录。
    结果直接显示在命令行；函数不返回岗位列表，也不会发送招聘消息。
    """
    started_at = perf_counter()
    print("=" * 52)
    print("JobPilot | Phase 0 + Phase 1 | MOCK ONLY")
    print("当前不会连接真实招聘网站。内置示例候选人与岗位均为虚构。")
    print("=" * 52)
    print(f"Candidate: {candidate.name}")
    print("Target Roles:")
    for role in candidate.target_roles:
        print(f"- {role}")
    print("Target Cities:")
    for city in candidate.target_cities:
        print(f"- {city}")

    # 第一步：从统一接口获取岗位，再清理空白、来源名称和网址。
    print(f"\nLoading jobs from {type(adapter).__name__}...")
    jobs = [normalize_job(job) for job in adapter.search_jobs()]
    print(f"Jobs loaded: {len(jobs)}")
    print("\nApplying rule-based filters...")
    # 第二步：逐个检查明确的求职条件，同时记录每个拒绝原因。
    job_filter = RuleFilter()
    accepted: list[JobPosting] = []
    rejection_counts: Counter[str] = Counter()
    for job in jobs:
        result = job_filter.evaluate(candidate, job)
        logger.debug("run_id=%s node=filter job_id=%s passed=%s",
                     logger.extra["run_id"], job.id, result.passed)
        if result.passed:
            accepted.append(job)
        else:
            # 一个岗位可以违反多条规则，因此原因总数可能大于被拒绝的岗位数。
            rejection_counts.update(result.reasons)
            print(f"Rejected: {job.title} | {'; '.join(result.reasons)}")
    print(f"Rejected jobs: {len(jobs) - len(accepted)}")
    print("Rejection reasons (one job may have several):")
    for reason, count in sorted(rejection_counts.items()):
        print(f"- {reason}: {count}")
    print(f"Remaining: {len(accepted)}")

    # 第三步：合并重复岗位，保留每组中第一次出现的记录。
    print("\nDeduplicating...")
    final_jobs = deduplicate_jobs(accepted)
    print(f"Duplicates removed: {len(accepted) - len(final_jobs)}")
    print(f"Final: {len(final_jobs)}")
    for job in final_jobs:
        print(f"- {job.company} | {job.title} | {job.city or '城市未注明'}"
              f" | {job.salary or '薪资未注明'}")

    # 第四步：先保存候选人和岗位，再建立两者之间的申请记录。
    print("\nSaving jobs...")
    tracker.save_candidate(candidate)
    inserted = tracker.save_jobs(final_jobs)
    for job in final_jobs:
        # 新编号可能只是旧岗位的别名；先找到已保存的 ID，避免重置申请进度。
        tracker.track(candidate.id, tracker.resolve_job_id(job))
    print(f"New jobs saved: {inserted}")
    print(f"Applications tracked: {len(tracker.list_applications(candidate.id))}")
    print("Done.")
    logger.info("run_id=%s node=search tool=%s.search_jobs result=success "
                "loaded=%d final=%d duration_ms=%.1f",
                logger.extra["run_id"], type(adapter).__name__, len(jobs), len(final_jobs),
                (perf_counter() - started_at) * 1000)


def build_parser() -> argparse.ArgumentParser:
    """定义命令行参数，以及参数出错时显示的帮助信息。

    默认执行搜索；查看记录和修改状态只能二选一。
    修改状态还需要 --confirm，确认由后面的存储层再次检查。
    """
    parser = argparse.ArgumentParser(description="JobPilot Phase 1：本地模拟岗位筛选与跟踪")
    parser.add_argument("--candidate", type=Path, help="候选人 JSON 路径")
    parser.add_argument("--jobs", type=Path, help="Mock 岗位 JSON 目录")
    parser.add_argument("--database", type=Path, help="SQLite 文件路径")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--list-applications", action="store_true", help="查看所有本地申请记录")
    actions.add_argument("--set-status", nargs=2, metavar=("APPLICATION_ID", "STATUS"),
                         help="手动更新本地状态，必须同时提供 --confirm")
    parser.add_argument("--confirm", action="store_true", help="确认本次明确指定的本地状态修改")
    return parser


def execute_cli(args: argparse.Namespace, settings: Settings,
                logger: logging.LoggerAdapter) -> None:
    """根据参数执行搜索、查看记录或修改状态中的一种操作。

    命令行指定的路径优先于配置文件；相对路径以当前终端目录为准。
    with 语句确保操作结束或报错时，数据库连接都会关闭。
    """
    database_path = (args.database or settings.database_path).resolve()
    # 搜索前先校验候选人文件，避免配置错误时也创建一个空数据库。
    candidate = None
    if not args.list_applications and not args.set_status:
        candidate = load_candidate((args.candidate or settings.candidate_path).resolve())
    with SQLiteTracker(database_path) as tracker:
        if args.list_applications:
            for application in tracker.list_applications():
                print(f"{application.id} | candidate={application.candidate_id}"
                      f" | job={application.job_id} | {application.status.value}")
            return
        if args.set_status:
            application_id, requested_status = args.set_status
            try:
                status = ApplicationStatus(requested_status.upper())
            except ValueError as exc:
                raise ConfigurationError("无效状态，可选：" + ", ".join(ApplicationStatus)) from exc
            # --confirm 只确认这次指定的本地状态修改，不代表批准任何外部动作。
            application = tracker.update_status(application_id, status, confirmed=args.confirm)
            print(f"Updated: {application.id} → {application.status.value} (local record only)")
            return
        assert candidate is not None
        adapter = MockJobAdapter((args.jobs or settings.jobs_path).resolve())
        run_search(candidate, adapter, tracker, logger)
        print(f"Database: {database_path}")


def main(argv: list[str] | None = None) -> int:
    """启动程序，并用退出码告诉终端执行结果。

    返回 0 表示成功，返回 1 表示配置、数据或存储操作失败。
    参数格式错误由 argparse 处理，它会显示帮助并以退出码 2 结束。
    argv 不传时读取终端参数；传入列表时便于代码直接调用。
    """
    # Windows 在重定向输出时可能使用旧编码；统一 UTF-8，避免中文乱码。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.confirm and not args.set_status:
        parser.error("--confirm 必须和 --set-status 一起使用")
    if sys.version_info[:2] != (3, 12):
        print("JobPilot 要求 Python 3.12，请使用项目的 .venv。", file=sys.stderr)
        return 1
    run_id = str(uuid4())
    # 每次运行使用独立编号，方便从多次运行的日志中找出同一轮记录。
    logger = configure_logging("INFO", run_id)
    try:
        settings = load_settings(PROJECT_ROOT)
        # 配置加载成功后再使用用户指定的日志级别；默认日志用于报告配置错误。
        logger = configure_logging(settings.log_level, run_id)
        execute_cli(args, settings, logger)
    except (JobPilotError, OSError, sqlite3.Error, ValidationError, json.JSONDecodeError) as exc:
        # 原始校验错误可能包含输入数据；这里只展开业务异常，其他错误仅显示类型。
        message = str(exc) if isinstance(exc, JobPilotError) else type(exc).__name__
        logger.error("run_id=%s result=failed error=%s", run_id, message)
        return 1
    return 0


if __name__ == "__main__":
    # 直接运行模块时才启动程序；被其他模块导入时，不会自动搜索或写数据库。
    raise SystemExit(main())
