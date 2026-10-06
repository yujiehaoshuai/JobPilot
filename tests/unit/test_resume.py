"""用虚构简历验证正文读取和来源约束，不接触用户真实资料。"""

from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from pydantic import ValidationError
from app.models.resume import ResumeProfileRequest
from app.services.resume_service import extract_resume, build_candidate, MAX_XML_BYTES


def docx_bytes(xml):
    """最小 DOCX 容器同时放入无关页眉，确保只读取正文。"""
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr("word/header1.xml", "页眉不应进入候选人经历")
    return stream.getvalue()


def request(**updates):
    values = dict(text="虚构同学\n在课程项目中使用 Python 编写测试。", name="虚构同学",
                  skills=[dict(skill="Python", level="project_experience", quote="在课程项目中使用 Python 编写测试。")],
                  confirmed=True)
    values.update(updates)
    return ResumeProfileRequest(**values)


def test_text_and_word_preserve_paragraphs_and_table_text():
    assert extract_resume("\ufeff虚构同学\r\nPython 项目".encode(), "txt") == "虚构同学\nPython 项目"
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body><w:p><w:r><w:t>Python</w:t></w:r><w:r><w:t> 项目</w:t></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>SQL</w:t><w:tab/><w:t>练习</w:t></w:r></w:p>'
           '</w:tc></w:tr></w:tbl></w:body></w:document>')
    assert extract_resume(docx_bytes(xml), "docx") == "Python 项目\nSQL\t练习"


@pytest.mark.parametrize("data, format", [(b"", "txt"), (b"broken", "docx"),
    (b"\xff\xfe", "txt"), (b"x\x00y", "txt"), (b"pdf", "pdf"), (b"x" * 1000001, "txt")],
    ids=["empty", "broken-docx", "encoding", "binary", "unsupported", "oversized"])
def test_invalid_resume_is_explicit_error(data, format):
    with pytest.raises(ValueError):
        extract_resume(data, format)


def test_docx_rejects_xml_entities_and_oversized_content():
    for xml in ['<!DOCTYPE root [<!ENTITY x "expansion">]><root>&x;</root>', "x" * (MAX_XML_BYTES + 1)]:
        with pytest.raises(ValueError):
            extract_resume(docx_bytes(xml), "docx")


def test_profile_uses_confirmed_quote_without_inventing_other_fields():
    candidate = build_candidate(request())
    assert candidate.skills[0].evidence == "在课程项目中使用 Python 编写测试。"
    assert candidate.education == candidate.projects == candidate.experience == []
    assert candidate.available_days_per_week is None
    with pytest.raises(ValidationError):
        request(confirmed=False)


@pytest.mark.parametrize("skill, quote", [("Python", "在大厂工作五年，精通 Python。"),
    ("Java", "使用 JavaScript 编写页面。"), ("Go", "在课程项目中使用 Python 编写测试。")])
def test_profile_rejects_fabricated_quote_and_unrelated_skill(skill, quote):
    body = request(text="使用 JavaScript 编写页面。\n在课程项目中使用 Python 编写测试。",
                   skills=[dict(skill=skill, level="professional", quote=quote)])
    with pytest.raises(ValueError):
        build_candidate(body)


def test_duplicate_skills_require_user_to_consolidate():
    body = request()
    body.skills.append(body.skills[0])
    with pytest.raises(ValueError, match="重复"):
        build_candidate(body)
