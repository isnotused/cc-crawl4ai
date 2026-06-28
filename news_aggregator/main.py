"""
新闻聚合 + 公众号文章生成 入口脚本

用法：
  python -m news_aggregator.main                     # mock 模式（无需 LLM）
  python -m news_aggregator.main --llm claude        # 用 Claude 生成
  python -m news_aggregator.main --llm deepseek      # 用 DeepSeek 生成
  python -m news_aggregator.main --sites 微博热搜 BBC中文  # 只抓指定站点
  python -m news_aggregator.main --no-headless       # 显示浏览器（调试用）
  python -m news_aggregator.main --save              # 保存到 output/ 目录
"""

import asyncio
import argparse
import os
import sys
from datetime import datetime

# 确保能找到 crawl4ai 本地源码
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .sites import SITES
from .crawler import crawl_all
from .aggregator import deduplicate, rank_by_coverage, categorize, top_n
from .writer import LLMWriter


def parse_args():
    p = argparse.ArgumentParser(description="新闻聚合 & 公众号文章生成")
    p.add_argument("--llm", default="mock",
                   choices=["mock", "claude", "openai", "deepseek"],
                   help="LLM 模式（默认 mock，不调用任何 API）")
    p.add_argument("--sites", nargs="*",
                   help="只抓指定站点名称，如 '微博热搜' 'BBC中文'")
    p.add_argument("--max", type=int, default=20,
                   help="每站点最多抓取条数（默认 20）")
    p.add_argument("--top", type=int, default=40,
                   help="去重后保留的总条数（默认 40）")
    p.add_argument("--no-headless", action="store_true",
                   help="显示浏览器窗口（调试模式）")
    p.add_argument("--save", action="store_true",
                   help="将文章保存到 output/ 目录")
    return p.parse_args()


async def run(args):
    # 筛选站点
    sites = SITES
    if args.sites:
        sites = [s for s in SITES if s.name in args.sites]
        if not sites:
            print(f"未找到站点，可用：{[s.name for s in SITES]}")
            return

    print(f"开始爬取 {[s.name for s in sites]} ...")
    all_news = await crawl_all(
        sites=sites,
        max_items_per_site=args.max,
        headless=not args.no_headless,
    )
    print(f"共获取 {len(all_news)} 条原始新闻")

    if not all_news:
        print("未获取到任何新闻，请检查网络或 CSS selector 是否需要更新。")
        return

    # 聚合处理
    deduped = deduplicate(all_news)
    print(f"去重后剩余 {len(deduped)} 条")
    # 按跨源覆盖度（被多家报道的事件更重要）+ 热度排序，再截取前 N 条
    ranked = rank_by_coverage(deduped)
    selected = top_n(ranked, args.top)
    categorized = categorize(selected)

    print("分类统计：", {k: len(v) for k, v in categorized.items()})

    # 生成文章
    writer = LLMWriter(mode=args.llm)
    print(f"使用 [{args.llm}] 生成公众号文章 ...")
    article = writer.generate(categorized)

    print("\n" + "=" * 60)
    print(article)
    print("=" * 60)

    if args.save:
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        fname = datetime.now().strftime("%Y%m%d_%H%M%S") + ".md"
        path = os.path.join(output_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(article)
        print(f"\n文章已保存到: {path}")


def main():
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
