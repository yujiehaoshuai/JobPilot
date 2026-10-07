"""本机 DeepSeek 设置：密钥只写入忽略提交的 .env，不出现在接口响应中。"""

import os
import re
import tempfile
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from dotenv import set_key
from pydantic import SecretStr

from app.exceptions import ConfigurationError, StructuredOutputError
from app.llm import client as llm
from app.models.analysis import GreetingPlan

DEEPSEEK_MODEL = "deepseek-flash"
_save_lock = Lock()
_test_lock = Lock()


def model_status() -> dict:
    """只返回可展示的状态；保存过密钥不代表已经通过真实联网验证。"""
    try:
        client = llm.create_llm("live")
    except (ConfigurationError, ValueError):
        return {"configured": False, "provider": "DeepSeek", "model": DEEPSEEK_MODEL}
    provider = "DeepSeek" if urlsplit(client.url).hostname == "api.deepseek.com" else "已配置的 AI 服务"
    return {"configured": True, "provider": provider, "model": client.model}


def save_deepseek(api_key: SecretStr) -> dict:
    """完整写好临时文件再替换，保留其他配置；写入失败时原配置仍然有效。"""
    key = api_key.get_secret_value().strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,512}", key):
        raise ConfigurationError("服务密钥格式不正确，请完整复制，不要包含空格或换行")
    values = {"LLM_BASE_URL": "https://api.deepseek.com", "LLM_MODEL": DEEPSEEK_MODEL,
              "LLM_API_STYLE": "responses", "LLM_API_KEY": key}
    # 进程变量的优先级高于 .env；不能向用户宣称保存后生效，实际却被旧值覆盖。
    if any(name in os.environ for name in values):
        raise ConfigurationError("启动程序时已指定 AI 配置，请先移除这些进程环境变量，再用页面保存")
    path = Path(llm.LLM_SETTINGS_PATH)
    with _save_lock:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".env.", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                if path.exists():
                    handle.write(path.read_text("utf-8"))
            for name, value in values.items():
                set_key(str(temporary), name, value, quote_mode="always")
            os.replace(temporary, path)
        except OSError:
            raise ConfigurationError("无法保存本机设置，请检查项目文件夹的写入权限") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return model_status()


def test_connection() -> dict:
    """用固定的测试文字验证结构化答复，不读取或上传用户简历。"""
    if not _test_lock.acquire(blocking=False):
        raise ConfigurationError("正在测试连接，请等待本次测试结束")
    try:
        client = llm.create_llm("live")
        result = client.complete("greeting", {"allowed_evidence_ids": ["connection-test"],
            "instruction": "这是连接测试，请选择唯一的测试编号。没有任何真实候选人资料。"}, GreetingPlan)
        if result.evidence_ids != ["connection-test"]:
            raise StructuredOutputError("已收到 AI 答复，但格式校验未通过，请重试")
        return {"ok": True, "message": "连接成功，AI 已正确回答测试问题。现在可以开始分析岗位。",
                "model": client.model}
    finally:
        _test_lock.release()
