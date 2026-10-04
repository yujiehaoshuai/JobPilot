"""验证按平台标识和网址去重时，既能合并重复岗位，也不会误删独立岗位。"""

from app.services.deduplication_service import deduplicate_jobs
from app.services.normalization_service import normalize_job


def test_repeated_platform_identity_keeps_first_seen_job(make_job) -> None:
    """同一平台岗位重复出现时保留首次记录，并保留其他独立岗位。"""
    first = make_job(id="first")
    repeated = make_job(id="repeat", url="https://jobs.example.test/jobs/another-path")
    unique = make_job(id="unique", source_job_id="job-2", url="https://jobs.example.test/jobs/2")

    result = deduplicate_jobs([first, repeated, unique])

    assert [job.id for job in result] == ["first", "unique"]


def test_identical_source_ids_on_distinct_platforms_are_distinct(make_job) -> None:
    """不同平台上的相同岗位编号应各自保留，编号只在所属平台内有效。"""
    first = make_job()
    other_source = make_job(id="second", source="another", url="https://other.example.test/jobs/1")

    assert len(deduplicate_jobs([first, other_source])) == 2


def test_tracking_query_and_fragment_do_not_create_new_job(make_job) -> None:
    """网址只在推广参数或页面锚点上不同时，应识别为同一岗位。"""
    first = make_job(url="https://jobs.example.test/detail?id=42&utm_source=search#intro")
    repeated = make_job(id="repeat", source_job_id="alias-1", url="https://jobs.example.test/detail?utm_campaign=demo&id=42")

    assert len(deduplicate_jobs([first, repeated])) == 1


def test_identity_query_parameters_are_preserved(make_job) -> None:
    """岗位编号等用于区分内容的查询参数不能移除，否则会误合并岗位。"""
    first = make_job(url="https://jobs.example.test/detail?id=42")
    second = make_job(id="second", source_job_id="job-2", url="https://jobs.example.test/detail?id=43")

    assert len(deduplicate_jobs([first, second])) == 2


def test_same_company_title_city_is_not_enough_to_drop_a_requisition(make_job) -> None:
    """公司、名称和城市相同也可能是不同招聘需求，不能仅凭这些字段去重。"""
    first = make_job()
    second = make_job(id="second", source_job_id="job-2", url="https://jobs.example.test/jobs/2")

    assert len(deduplicate_jobs([first, second])) == 2


def test_normalization_is_idempotent_and_does_not_edit_input(make_job) -> None:
    """标准化应整理多余空格、不修改原对象，重复处理也应得到相同结果。"""
    original = make_job(title="  Agent   Engineer Intern  ", company="Example   AI")
    before = original.model_dump()

    normalized = normalize_job(original)

    assert normalized.title == "Agent Engineer Intern"
    assert normalize_job(normalized) == normalized
    assert original.model_dump() == before


def test_deduplication_handles_empty_input() -> None:
    """没有岗位时应返回空列表，不产生额外记录或异常。"""
    assert deduplicate_jobs([]) == []
