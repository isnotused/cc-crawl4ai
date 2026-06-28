"""
新闻聚合：去重、按主题分类、按多源覆盖度排序。

去重策略说明：
  原实现用 Jaccard（字符集合相似度），对中文短标题不够准确——
  例如「A股大涨」和「大涨的A股」字符集合几乎相同却语序不同，
  而「巴黎奥运开幕」和「巴黎遭遇暴雨」字符重合度也偏高。
  这里改用 difflib.SequenceMatcher，它基于最长公共子序列，
  同时考虑字符内容与顺序，对中文标题判重更稳健。
"""

import re
from collections import defaultdict
from difflib import SequenceMatcher


# ── 去重 ──────────────────────────────────────────────────────────────────────

def _normalize_title(title: str) -> str:
    """归一化标题用于比较：去空白、去常见标点/修饰，降低噪声干扰。"""
    title = title.strip()
    # 去掉热搜常见的「热」「新」「沸」「爆」等单字标记与各类标点
    title = re.sub(r"[\s　]+", "", title)
    title = re.sub(r"[，。！？、；：“”‘’\"'（）()\[\]【】#·…—\-—_~|/\\]", "", title)
    return title


def _similar(a: str, b: str) -> float:
    """两标题归一化后的 SequenceMatcher 相似度（0~1）。"""
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 一方完全包含另一方时，视为高度相似（短标题是长标题的子串很常见）
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        return max(0.85, len(shorter) / len(longer))
    return SequenceMatcher(None, na, nb).ratio()


def deduplicate(news_list: list[dict], similarity_threshold: float = 0.7) -> list[dict]:
    """
    基于 SequenceMatcher 的相似度去重：标题相似度超过阈值即视为重复，
    保留先出现的一条，并把被去重条目的来源记录到 also_in 字段，
    供后续 rank_by_coverage 统计跨源覆盖度。
    """
    kept: list[dict] = []
    for item in news_list:
        title = item.get("title", "")
        dup_of = None
        for k in kept:
            if _similar(title, k.get("title", "")) >= similarity_threshold:
                dup_of = k
                break
        if dup_of is None:
            # 初始化覆盖来源集合（含自身来源）
            item.setdefault("also_in", [])
            src = item.get("source", "")
            if src and src not in item["also_in"]:
                item["also_in"].append(src)
            kept.append(item)
        else:
            dup_of.setdefault("also_in", [dup_of.get("source", "")])
            src = item.get("source", "")
            if src and src not in dup_of["also_in"]:
                dup_of["also_in"].append(src)
    return kept


# ── 分类 ──────────────────────────────────────────────────────────────────────

# 关键词分类表，顺序即优先级（靠前的先匹配）。已较原版大幅扩充。
_CATEGORIES: list[tuple[str, list[str]]] = [
    ("国际", [
        "美国", "欧洲", "俄罗斯", "乌克兰", "中东", "日本", "韩国", "朝鲜", "英国",
        "法国", "德国", "印度", "以色列", "巴勒斯坦", "加沙", "伊朗", "BBC", "联合国",
        "NATO", "北约", "白宫", "普京", "特朗普", "拜登", "外交", "大使馆", "G7",
        "欧盟", "台海", "南海", "援助", "制裁", "签证", "海外",
    ]),
    ("科技", [
        "AI", "人工智能", "芯片", "半导体", "手机", "苹果", "iPhone", "华为", "小米",
        "字节", "腾讯", "阿里", "百度", "OpenAI", "ChatGPT", "大模型", "机器人",
        "算力", "英伟达", "特斯拉", "马斯克", "自动驾驶", "新能源车", "卫星", "航天",
        "量子", "开源", "操作系统", "鸿蒙", "元宇宙", "互联网",
    ]),
    ("财经", [
        "股市", "A股", "港股", "美股", "基金", "楼市", "房价", "经济", "GDP", "通胀",
        "美联储", "央行", "降息", "加息", "人民币", "美元", "黄金", "石油", "原油",
        "融资", "IPO", "营收", "利润", "财报", "裁员", "失业", "消费", "出口", "关税",
        "比特币", "加密货币", "债务",
    ]),
    ("社会", [
        "事故", "案件", "嫌疑人", "警方", "法院", "判决", "起诉", "救援", "地震",
        "洪水", "暴雨", "台风", "高温", "火灾", "爆炸", "坠落", "疫情", "病例", "医院",
        "学校", "高考", "中考", "招聘", "养老", "社保", "诈骗", "失踪", "遇难", "曝光",
    ]),
    ("体育", [
        "足球", "篮球", "NBA", "CBA", "奥运", "亚运", "世界杯", "欧洲杯", "冠军",
        "夺冠", "比赛", "赛事", "决赛", "运动员", "教练", "国足", "梅西", "C罗", "网球",
        "乒乓", "羽毛球", "田径", "游泳", "马拉松", "破纪录",
    ]),
    ("娱乐", [
        "电影", "明星", "综艺", "音乐", "演唱会", "票房", "剧情", "热播", "电视剧",
        "导演", "演员", "歌手", "偶像", "粉丝", "官宣", "恋情", "结婚", "离婚", "出轨",
        "塌房", "首映", "新歌", "专辑", "红毯", "颁奖",
    ]),
]


def categorize(news_list: list[dict]) -> dict[str, list[dict]]:
    """返回按分类分组的字典，未命中关键词的归入「其他」。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in news_list:
        text = item.get("title", "") + " " + item.get("summary", "")
        groups[_classify(text)].append(item)
    return dict(groups)


def _classify(text: str) -> str:
    """命中关键词最多的分类胜出；全不命中归「其他」。"""
    best_cat = "其他"
    best_score = 0
    for cat, keywords in _CATEGORIES:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


# ── 排序 ──────────────────────────────────────────────────────────────────────

def _heat_to_number(heat: str) -> int:
    """把「123.4万」「1.2亿」等热度文本粗略转成可比较的整数。"""
    if not heat:
        return 0
    m = re.search(r"([\d.]+)\s*(亿|万)?", heat)
    if not m:
        return 0
    try:
        val = float(m.group(1))
    except ValueError:
        return 0
    unit = m.group(2)
    if unit == "亿":
        val *= 1e8
    elif unit == "万":
        val *= 1e4
    return int(val)


def rank_by_coverage(news_list: list[dict]) -> list[dict]:
    """
    按「跨源覆盖度」给新闻排序：被越多来源报道的事件越重要，排得越靠前。

    打分维度（依次）：
      1. coverage —— 不同来源数量（也就是 deduplicate 累积的 also_in 大小）
      2. heat     —— 热度数值（微博/头条有热度时作为次要权重）

    会在每条上写入 coverage 字段，便于上层展示「N 家报道」。
    """
    for item in news_list:
        sources = item.get("also_in") or [item.get("source", "")]
        item["coverage"] = len({s for s in sources if s})

    return sorted(
        news_list,
        key=lambda it: (it.get("coverage", 1), _heat_to_number(it.get("heat", ""))),
        reverse=True,
    )


def top_n(news_list: list[dict], n: int = 30) -> list[dict]:
    """取前 N 条（保持传入顺序）。"""
    return news_list[:n]
