"""扩展选择器不能漂移，导出完整岗位必须能进入现有统一模型。"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.models.job import JobPosting
from scripts.build_browser_probe import probe_config


def test_extension_uses_current_central_selectors():
    path = Path(__file__).resolve().parents[2] / "extensions/boss_readonly/selectors.json"
    # 经 JSON 往返统一 tuple/list，差异说明改选择器后忘了更新扩展。
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(probe_config()))


def test_extension_job_shape_matches_existing_domain_model():
    node = shutil.which("node")
    if not node:
        pytest.skip("扩展跨语言契约验收需要现有 Node；纯 Python 环境不安装它")
    # 调用真实 JS 导出函数，再让现有 Pydantic 模型校验，避免两份手写样本自说自话。
    script = """
        import {jobFromDetail} from './extensions/boss_readonly/core.mjs';
        const job = jobFromDetail({url:'https://www.zhipin.com/job_detail/example.html',
            title:'虚构测试岗位',company:'虚构测试公司',description:'Python 开发',city:'北京'},
            '2026-10-07T00:00:00.000Z');
        process.stdout.write(JSON.stringify(job));
    """
    result = subprocess.run([node, "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[2], check=True, capture_output=True, text=True, encoding="utf-8")
    job = JobPosting.model_validate_json(result.stdout)
    assert job.source_job_id == "example"
    assert job.salary is None
