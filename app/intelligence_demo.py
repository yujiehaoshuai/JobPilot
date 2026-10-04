"""Phase 2 的离线或真实模型演示；原 Phase 1 CLI 保持可用。"""

import argparse
from app.config import load_settings
from app.main import load_candidate
from app.adapters.mock.adapter import MockJobAdapter
from app.llm.client import create_llm
from app.services.analysis_service import JobAnalyzer
from app.services.matching_service import CandidateMatcher
from app.services.greeting_service import GreetingGenerator
from app.services.filter_service import RuleFilter
from app.services.deduplication_service import deduplicate_jobs


def main() -> None:
    """只分析和生成草稿，不进行任何招聘平台操作。"""
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    args = parser.parse_args()
    settings = load_settings()
    candidate = load_candidate(settings.candidate_path)
    client = create_llm(args.mode)
    jobs = deduplicate_jobs([job for job in MockJobAdapter(settings.jobs_path).search_jobs()
                             if RuleFilter().evaluate(candidate, job).passed])
    print(f"模式：{args.mode}；岗位：{len(jobs)}")
    for job in jobs:
        analysis = JobAnalyzer(client).analyze(job)
        match = CandidateMatcher().match(candidate, job, analysis)
        print(job.title, match.model_dump_json())
        if match.shortlisted:
            print(GreetingGenerator(client).generate(candidate, job, match).content)


if __name__ == "__main__":
    main()
