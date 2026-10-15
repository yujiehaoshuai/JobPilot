"""只处理搜索地点名称和网站参数；城市筛选不依赖模型猜测。"""

import json
from pathlib import Path
from urllib.parse import urlencode
from app.exceptions import JobParseError


def normalize_cities(cities):
    """允许“上海市”这样的常见写法；去重后保持用户填写的顺序。"""
    names = []
    for value in cities or []:
        name = value.strip().removesuffix("市")
        if not name or len(name) > 40 or name in {"全国", "不限", "全部"}:
            raise JobParseError("请填写具体工作城市，例如上海、杭州")
        if name not in names:
            names.append(name)
    if len(names) > 10:
        raise JobParseError("一次最多填写 10 个城市")
    return names


def boss_search_cities(cities):
    """使用网站公开城市配置的本地快照；未知名称不能退回全国搜索。"""
    codes = json.loads(Path(__file__).with_name("boss_cities.json").read_text("utf-8"))["cities"]
    result = []
    for name in normalize_cities(cities):
        if name not in codes:
            raise JobParseError(f"BOSS 暂不能识别城市“{name}”，请填写市级名称，例如上海、杭州")
        result.append({"name": name, "code": codes[name]})
    return result


def city_query(source, city):
    """使用网站原生搜索参数，绝不把城市拼入岗位关键词。"""
    if not city:
        return ""
    value = boss_search_cities([city])[0]["code"] if source == "boss" else city
    return "&" + urlencode({"city": value})
