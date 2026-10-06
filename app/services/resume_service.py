"""在本机提取简历正文和校验证据，不调用模型、不猜测候选人经历。"""

from io import BytesIO
import re
from uuid import uuid4
from zipfile import ZipFile, BadZipFile
from zlib import error as ZlibError
from xml.etree import ElementTree
from app.models.candidate import CandidateProfile, CandidateSkill
from app.models.resume import ResumeProfileRequest

MAX_UPLOAD_BYTES = 1_000_000
MAX_TEXT_CHARS = 100000
MAX_XML_BYTES = 4_000_000
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_resume(data: bytes, format: str) -> str:
    """支持 UTF-8 文本和 DOCX 正文；不读取图片、链接、批注或执行宏。"""
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("简历文件为空或超过 1 MB")
    try:
        if format == "txt":
            result = data.decode("utf-8-sig")
        elif format == "docx":
            result = extract_docx(data)
        else:
            raise ValueError("当前支持 TXT、Markdown 和 DOCX；PDF 请先复制正文到文本框")
    except UnicodeDecodeError:
        raise ValueError("正文编码无法读取，请另存为 UTF-8 文本后导入") from None
    result = result.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not result or "\x00" in result:
        raise ValueError("没有可读取的正文；图片或扫描简历请先手动转成文字")
    if len(result) > MAX_TEXT_CHARS:
        raise ValueError("简历正文超过十万字，请缩短后再导入")
    return result


def extract_docx(data: bytes) -> str:
    """只在内存读取受限的 document.xml；压缩包内容永不解压到磁盘。"""
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 20_000_000:
                raise ValueError("DOCX 解压体积过大，请另存为纯文本")
            entry = archive.getinfo("word/document.xml")
            if entry.file_size > MAX_XML_BYTES:
                raise ValueError("DOCX 正文过大，请另存为纯文本")
            with archive.open(entry) as handle:
                xml = handle.read(MAX_XML_BYTES + 1)
            if len(xml) > MAX_XML_BYTES:
                raise ValueError("DOCX 正文过大，请另存为纯文本")
        source = xml.decode("utf-8-sig")
        # 禁止自定义实体，避免恶意文档在 XML 解析时膨胀。
        if "<!doctype" in source.lower() or "<!entity" in source.lower():
            raise ValueError("不支持含自定义 XML 实体的文档，请另存为纯文本")
        root = ElementTree.fromstring(source)
        paragraphs = []
        for paragraph in root.iter(WORD_NS + "p"):
            parts = []
            for node in paragraph.iter():
                if node.tag == WORD_NS + "t":
                    parts.append(node.text or "")
                elif node.tag == WORD_NS + "tab":
                    parts.append("\t")
                elif node.tag in {WORD_NS + "br", WORD_NS + "cr"}:
                    parts.append("\n")
            paragraphs.append("".join(parts))
        return "\n".join(paragraphs)
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, NotImplementedError, ZlibError, EOFError):
        raise ValueError("DOCX 已损坏、被加密或格式不受支持，请另存为纯文本") from None


def build_candidate(request: ResumeProfileRequest) -> CandidateProfile:
    """核对每条原文后生成新资料；级别由用户确认，不从语句自动推断。"""
    skills = []
    seen = set()
    for item in request.skills:
        if item.quote not in request.text:
            raise ValueError("技能证据不在简历原文中，请直接选取原文，不要改写")
        # ASCII 边界避免把 JavaScript 引用当作 Java；中文前后不要求空格。
        pattern = r"(?<![a-z0-9_])" + re.escape(item.skill.casefold()) + r"(?![a-z0-9_])"
        if not re.search(pattern, item.quote.casefold()):
            raise ValueError("引用中没有完整的技能名称，请使用原文中的名称")
        if item.skill.casefold() in seen:
            raise ValueError("技能重复，请将同一技能的证据整理在一条记录中")
        seen.add(item.skill.casefold())
        skills.append(CandidateSkill(skill=item.skill, level=item.level, evidence=item.quote))
    return CandidateProfile(id=str(uuid4()), name=request.name, skills=skills,
                            target_roles=request.target_roles, target_cities=request.target_cities)
