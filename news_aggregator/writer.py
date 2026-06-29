"""
公众号文章生成器。

支持两种模式：
  - mock:   直接用模板拼接，无需 LLM，用于测试架构
  - claude: 调用 Anthropic Claude API（需 ANTHROPIC_API_KEY）
  - openai: 调用 OpenAI API（需 OPENAI_API_KEY）
  - deepseek: 调用 DeepSeek API（需 DEEPSEEK_API_KEY）

通过 LLMWriter(mode="...") 切换。
"""

from __future__ import annotations

import os
import textwrap
from datetime import datetime


class LLMWriter:
    def __init__(self, mode: str = "mock"):
        self.mode = mode

    def generate(
        self,
        categorized_news: dict[str, list[dict]],
        date_str: str | None = None,
    ) -> str:
        date_str = date_str or datetime.now().strftime("%Y年%m月%d日")
        if self.mode == "mock":
            return _mock_article(categorized_news, date_str)
        elif self.mode == "claude":
            return _claude_article(categorized_news, date_str)
        elif self.mode == "openai":
            return _openai_article(categorized_news, date_str)
        elif self.mode == "deepseek":
            return _deepseek_article(categorized_news, date_str)
        else:
            raise ValueError(f"未知 mode: {self.mode}")


# ── Mock 模板（无需 LLM） ────────────────────────────────────────────────────

def _mock_article(news: dict[str, list[dict]], date: str) -> str:
    lines = [
        f"# {date} 热点新闻速览",
        "",
        f"> 来源：微博热搜 / 今日头条 / 新浪新闻 / 网易新闻 / BBC中文 / "
        f"Reuters / BBC News / AP News / Bloomberg / Financial Times / CNBC / "
        f"TechCrunch / The Verge / Wired / Science Daily / New Scientist / "
        f"ESPN / BBC Sport / IGN / Kotaku / Polygon",
        "",
    ]
    for cat, items in news.items():
        if not items:
            continue
        lines.append(f"## {cat}")
        for i, item in enumerate(items[:5], 1):
            link = item.get("link", "")
            title = item["title"]
            source = item.get("source", "")
            heat = item.get("heat", "")
            heat_str = f" 🔥{heat}" if heat else ""
            summary = item.get("summary", "")
            if link:
                lines.append(f"{i}. [{title}]({link}){heat_str} _({source})_")
            else:
                lines.append(f"{i}. **{title}**{heat_str} _({source})_")
            if summary:
                lines.append(f"   > {summary[:80]}...")
        lines.append("")
    lines += [
        "---",
        f"_本文由 [crawl4ai](https://github.com/unclecode/crawl4ai) 自动聚合，仅供参考。_",
    ]
    return "\n".join(lines)


# ── Claude ───────────────────────────────────────────────────────────────────

def _claude_article(news: dict[str, list[dict]], date: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise ImportError("pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("请设置环境变量 ANTHROPIC_API_KEY")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(news, date)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ── OpenAI ───────────────────────────────────────────────────────────────────

def _openai_article(news: dict[str, list[dict]], date: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("请设置环境变量 OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)
    prompt = _build_prompt(news, date)

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return resp.choices[0].message.content


# ── DeepSeek ─────────────────────────────────────────────────────────────────

def _deepseek_article(news: dict[str, list[dict]], date: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("pip install openai")

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise EnvironmentError("请设置环境变量 DEEPSEEK_API_KEY")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    prompt = _build_prompt(news, date)

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return resp.choices[0].message.content


# ── 共用 Prompt ───────────────────────────────────────────────────────────────

def _build_prompt(news: dict[str, list[dict]], date: str) -> str:
    sections = []
    for cat, items in news.items():
        block = f"【{cat}】\n"
        for item in items[:8]:
            block += f"- {item['title']}"
            if item.get("summary"):
                block += f"：{item['summary'][:60]}"
            block += "\n"
        sections.append(block)

    news_text = "\n".join(sections)

    return textwrap.dedent(f"""\
        你是一位资深新媒体编辑，擅长撰写微信公众号文章。

        今天是 {date}，以下是今日各大平台热点新闻汇总：

        {news_text}

        请根据上述新闻，撰写一篇适合微信公众号发布的热点速览文章，要求：
        1. 开头有吸引人的导语（2-3句）
        2. 按主题板块分类，每板块选 3-5 条最重要的新闻
        3. 每条新闻简要点评（1-2句话），语言生动不枯燥
        4. 结尾有简短总结语
        5. 全文 800-1200 字，markdown 格式，适合直接复制到公众号后台
        6. 不要编造细节，只基于提供的信息
    """)
