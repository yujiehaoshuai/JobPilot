"""把现有集中选择器导出给只读扩展，避免维护两套平台选择器。"""

import json
from dataclasses import asdict
from pathlib import Path

from app.browser.selectors import BOSS, CHALLENGE_SELECTORS, CHALLENGE_TITLES


def probe_config() -> dict:
    """仅导出公开页面结构，不包含登录资料、环境变量或候选人信息。"""
    return {"site": asdict(BOSS), "challenge_selectors": list(CHALLENGE_SELECTORS),
            "challenge_titles": list(CHALLENGE_TITLES)}


def main() -> None:
    """修改集中选择器后重新运行本命令；生成文件随扩展一起加载。"""
    path = Path(__file__).resolve().parents[1] / "extensions/boss_readonly/selectors.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(probe_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
