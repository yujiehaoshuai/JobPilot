"""读取简历正文，校验人工或 AI 提取的每条证据，不补写候选人经历。"""

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
    """核对每条原文后生成资料；级别和可用时间直接取自本次表单。"""
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
                            target_roles=request.target_roles, target_cities=request.target_cities,
                            employment_type=request.employment_type,
                            available_days_per_week=request.available_days_per_week,
                            internship_duration_months=request.internship_duration_months)


def analyze_resume(client, request, candidate_id: str):
    """AI 提炼后再逐项验真；原文中的否定、意愿和他人要求不能变成已有技能。"""
    from app.models.search import ResumeExtraction
    from app.exceptions import StructuredOutputError
    from app.enums import SkillLevel
    result = client.complete("resume", {"text": request.text, "intent": request.intent}, ResumeExtraction)
    for quote in result.education + result.projects + result.experience:
        if not quote or quote not in request.text:
            raise StructuredOutputError("AI 提取的经历不在简历原文中，请检查正文后重试")
    if result.name and result.name not in request.text:
        raise StructuredOutputError("AI 提取的姓名不在原文中，已拒绝保存")
    skills, warnings = [], []
    for item in result.skills:
        if item.quote not in request.text:
            raise StructuredOutputError("AI 提取的技能证据不在简历原文中，已拒绝保存")
        # 检查完整原句，防止模型只截取“不熟悉 Python”中的 Python。
        position = request.text.find(item.quote)
        left = max(request.text.rfind(mark, 0, position) for mark in ("\n", "。", "；")) + 1
        ends = [request.text.find(mark, position + len(item.quote)) for mark in ("\n", "。", "；")]
        right = min([end for end in ends if end >= 0] or [len(request.text)])
        sentence = request.text[left:right]
        if re.search(r"不熟悉|不会|未掌握|没有.{0,8}经验|尚未|计划学习|希望学习|岗位要求|招聘要求|同事|他人", sentence):
            warnings.append(f"{item.skill} 的原句含否定、意愿或他人要求，未计为已有技能。")
            continue
        # 只看到技能名不等于有项目或工作经历；不让 AI 自行提高经验级别。
        level = item.level
        if level == SkillLevel.PROFESSIONAL and not re.search(r"工作|任职|实习|就职", sentence):
            level = SkillLevel.PROJECT_EXPERIENCE
        if level == SkillLevel.PROJECT_EXPERIENCE and not re.search(r"项目|开发|实现|编写|搭建|构建|完成|使用", sentence):
            level = SkillLevel.LEARNING
        checked = item.model_copy(update={"level": level})
        try:
            one = build_candidate(ResumeProfileRequest(text=request.text, name="简历", skills=[checked]))
        except ValueError as exc:
            raise StructuredOutputError("AI 提取的技能名称与引用不一致，已拒绝保存") from exc
        if not any(value.skill.casefold() == one.skills[0].skill.casefold() for value in skills):
            skills.extend(one.skills)

    def available(value, quote, unit):
        if value is None:
            return None
        if not quote or quote not in request.text or not re.search(rf"{value}\s*{unit}", quote):
            raise StructuredOutputError("AI 提取的可用时间缺少原文依据，已拒绝保存")
        return value

    days = available(result.available_days_per_week, result.days_quote, "天")
    months = available(result.internship_duration_months, result.months_quote, "个月")
    candidate = CandidateProfile(id=candidate_id, name=result.name or "本次简历", skills=skills,
        education=result.education, projects=result.projects, experience=result.experience,
        target_roles=[request.intent], target_cities=request.cities, employment_type=request.employment_type,
        available_days_per_week=request.available_days_per_week if request.available_days_per_week is not None else days,
        internship_duration_months=request.internship_duration_months if request.internship_duration_months is not None else months)
    queries = list(dict.fromkeys(query[:80] for query in result.search_queries))[:3]
    # 技术名本身也是一个宽搜索词，避免模型只给“Python 后端开发实习”等狭窄组合。
    anchor = re.search(r"[A-Za-z][A-Za-z0-9+#.]*", request.intent)
    if anchor:
        queries = list(dict.fromkeys([anchor[0], *queries]))[:3]
    if not skills:
        warnings.append("简历中没有提取到可核验的技能，本轮分数只能作为有限参考。")
    return candidate, queries, warnings
