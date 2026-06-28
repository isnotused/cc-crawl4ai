"""
新闻爬虫核心模块。

主要能力：
  - 基于 crawl4ai 无头浏览器抓取，按站点定制等待 / 滚动 / JS 策略
  - 指数退避重试（exponential backoff），抵抗偶发的网络抖动与超时
  - 三级抽取兜底：主 schema → 备用 baseSelector → markdown 链接解析
  - 带来源标签的结构化日志输出，便于排查每个站点的抓取情况
"""

import asyncio
import json
import logging
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

try:
    # CacheMode 在不同版本位置一致，作为可选导入以增强兼容性
    from crawl4ai import CacheMode
except Exception:  # pragma: no cover - 兼容旧版本
    CacheMode = None

from .sites import SITES, SiteConfig


# ── 日志 ──────────────────────────────────────────────────────────────────────

logger = logging.getLogger("news_aggregator.crawler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


def _log(source: str, msg: str, level: int = logging.INFO):
    """带来源标签的日志，统一格式 [站点] 信息。"""
    logger.log(level, "[%s] %s", source, msg)


# 桌面端 UA，避免部分站点返回移动版或精简版页面
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 重试参数
_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0  # 秒，指数退避基数：2s, 4s, 8s ...


# ── 链接处理 ──────────────────────────────────────────────────────────────────

def _normalize_link(link: str, base_url: str) -> str:
    """把相对链接、协议相对链接补全为绝对 URL。"""
    if not link:
        return ""
    link = link.strip()
    if link.startswith(("http://", "https://")):
        return link
    parsed = urlparse(base_url)
    if link.startswith("//"):
        return f"{parsed.scheme}:{link}"
    if link.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{link}"
    # 其余视为站内相对路径
    return f"{parsed.scheme}://{parsed.netloc}/{link.lstrip('/')}"


# ── 运行配置 ──────────────────────────────────────────────────────────────────

def _build_run_config(site: SiteConfig, schema: dict) -> CrawlerRunConfig:
    """为单个站点构造 CrawlerRunConfig，按需开启滚动 / JS 等策略。"""
    kwargs = dict(
        extraction_strategy=JsonCssExtractionStrategy(schema, verbose=False),
        wait_for=site.wait_for,
        js_code=site.js_code,
        page_timeout=site.timeout * 1000,
        # 等不到 wait_for 也不要无限阻塞，给一个稍小于总超时的等待上限
        wait_for_timeout=min(site.timeout, 20) * 1000,
        # 防止极短页面被 word_count 过滤，这里放宽阈值
        word_count_threshold=1,
        verbose=False,
    )
    if CacheMode is not None:
        # 新闻是时效性内容，始终绕过缓存拿最新数据
        kwargs["cache_mode"] = CacheMode.BYPASS
    if site.scroll:
        # 滚动到底触发懒加载
        kwargs["scan_full_page"] = True
        kwargs["scroll_delay"] = 0.4
    return CrawlerRunConfig(**kwargs)


# ── 抽取兜底 ──────────────────────────────────────────────────────────────────

def _parse_items_json(raw: str) -> list[dict]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)]


def _items_from_markdown(markdown_text: str, site: SiteConfig, max_items: int) -> list[dict]:
    """
    最后的兜底：从页面 markdown 中解析出新闻条目。

    crawl4ai 会把页面正文转成 markdown，其中链接形如 [标题](url)。
    我们提取这些链接作为候选新闻标题，过滤掉过短 / 明显是导航的条目。
    """
    if not markdown_text:
        return []

    link_pattern = re.compile(r"\[([^\]\n]+?)\]\((https?://[^)\s]+|/[^)\s]+)\)")
    seen_titles: set[str] = set()
    news: list[dict] = []
    for match in link_pattern.finditer(markdown_text):
        title = match.group(1).strip()
        link = match.group(2).strip()
        # 过滤：过短标题、纯符号、常见导航词
        if len(title) < 6:
            continue
        if title in seen_titles:
            continue
        if any(w in title for w in ("登录", "注册", "下载", "客户端", "更多", "首页", "APP")):
            continue
        seen_titles.add(title)
        news.append({
            "source": site.name,
            "title": title,
            "link": _normalize_link(link, site.url),
            "summary": "",
            "heat": "",
            "time": "",
        })
        if len(news) >= max_items:
            break
    return news


def _build_news(items: list[dict], site: SiteConfig, max_items: int) -> list[dict]:
    """把抽取到的原始字典统一成标准新闻结构，并做基本清洗。"""
    news: list[dict] = []
    seen: set[str] = set()
    for item in items:
        title = (item.get("title") or "").strip()
        title = re.sub(r"\s+", " ", title)
        if not title or len(title) < 2:
            continue
        if title in seen:
            continue
        seen.add(title)
        news.append({
            "source": site.name,
            "title": title,
            "link": _normalize_link(item.get("link"), site.url),
            "summary": re.sub(r"\s+", " ", (item.get("summary") or "").strip()),
            "heat": (item.get("heat") or "").strip(),
            "time": (item.get("time") or "").strip(),
        })
        if len(news) >= max_items:
            break
    return news


# ── 单站点抓取（含重试） ──────────────────────────────────────────────────────

async def _fetch_once(crawler, site: SiteConfig, schema: dict):
    """执行一次抓取，返回 crawl4ai 的 result 对象（可能抛异常）。"""
    run_cfg = _build_run_config(site, schema)
    return await crawler.arun(url=site.url, config=run_cfg)


async def _crawl_site(crawler, site: SiteConfig, max_items: int = 20) -> list[dict]:
    """
    抓取单个站点：

      1. 主 schema 抓取（带指数退避重试）
      2. 主 schema 抽取为空 → 依次尝试 fallback_selectors
      3. 仍为空 → 从 markdown 解析链接兜底
    """
    last_result = None
    last_error = None

    # —— 第一步：主 schema + 重试 ——
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = await _fetch_once(crawler, site, site.schema)
        except Exception as exc:  # 网络/浏览器异常
            last_error = exc
            _log(site.name, f"第 {attempt}/{_MAX_RETRIES} 次抓取异常: {exc}", logging.WARNING)
            result = None

        if result is not None:
            last_result = result
            if result.success:
                items = _parse_items_json(result.extracted_content)
                news = _build_news(items, site, max_items)
                if news:
                    _log(site.name, f"主 schema 获取 {len(news)} 条")
                    return news
                _log(site.name, "主 schema 抽取为空，准备尝试备用方案", logging.WARNING)
                break  # 页面已成功加载，重试同样的 selector 无意义
            else:
                last_error = result.error_message
                _log(site.name, f"第 {attempt}/{_MAX_RETRIES} 次请求未成功: {result.error_message}",
                     logging.WARNING)

        if attempt < _MAX_RETRIES:
            backoff = _BASE_BACKOFF * (2 ** (attempt - 1))
            _log(site.name, f"{backoff:.0f}s 后重试 ...")
            await asyncio.sleep(backoff)

    # —— 第二步：备用 baseSelector ——
    if last_result is not None and last_result.success and site.fallback_selectors:
        for sel in site.fallback_selectors:
            alt_schema = dict(site.schema)
            alt_schema["baseSelector"] = sel
            try:
                result = await _fetch_once(crawler, site, alt_schema)
            except Exception as exc:
                _log(site.name, f"备用选择器 '{sel}' 抓取异常: {exc}", logging.WARNING)
                continue
            if result.success:
                last_result = result
                items = _parse_items_json(result.extracted_content)
                news = _build_news(items, site, max_items)
                if news:
                    _log(site.name, f"备用选择器 '{sel}' 获取 {len(news)} 条")
                    return news

    # —— 第三步：markdown 兜底 ——
    if last_result is not None and last_result.success:
        md = last_result.markdown
        md_text = getattr(md, "raw_markdown", None) or (md if isinstance(md, str) else "")
        news = _items_from_markdown(md_text, site, max_items)
        if news:
            _log(site.name, f"markdown 兜底解析出 {len(news)} 条", logging.WARNING)
            return news

    _log(site.name, f"全部方案均未获取到新闻（最后错误: {last_error}）", logging.ERROR)
    return []


# ── 对外入口 ──────────────────────────────────────────────────────────────────

async def crawl_all(sites=SITES, max_items_per_site: int = 20, headless: bool = True) -> list[dict]:
    """
    并发抓取所有站点。单个站点失败不影响其它站点（return_exceptions=True）。

    返回：合并后的新闻列表，每条为统一结构的 dict。
    """
    browser_cfg = BrowserConfig(
        headless=headless,
        user_agent=_DESKTOP_UA,
        viewport_width=1366,
        viewport_height=900,
        verbose=False,
    )

    _log("crawler", f"启动浏览器，待抓取 {len(sites)} 个站点 (headless={headless})")
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        tasks = [_crawl_site(crawler, site, max_items_per_site) for site in sites]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_news: list[dict] = []
    for site, batch in zip(sites, results):
        if isinstance(batch, Exception):
            _log(site.name, f"任务异常被捕获: {batch}", logging.ERROR)
            continue
        all_news.extend(batch)

    _log("crawler", f"全部站点合计获取 {len(all_news)} 条原始新闻")
    return all_news
