"""
各新闻站点的爬取配置：URL、CSS schema、等待与渲染策略。

selector 极易随站点改版失效，这里统一维护，并为每个站点提供
`fallback_selectors`（备用 baseSelector 列表）以增强抗改版能力：
当主 schema 抽取不到任何条目时，crawler 会依次尝试这些备用选择器，
仍然失败则回退到 markdown 解析。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SiteConfig:
    name: str
    url: str
    # JsonCssExtractionStrategy 的 schema（主选择器方案）
    schema: dict
    # 等待某个 CSS 元素出现后再抓（JS 渲染页面必须）
    wait_for: Optional[str] = None
    # 进入页面后执行的 JS（点击展开、加载更多等）
    js_code: Optional[str] = None
    # 超时（秒）
    timeout: int = 30
    # 是否需要桌面 UA
    desktop: bool = True
    # 是否需要滚动到底以触发懒加载（scan_full_page）
    scroll: bool = False
    # 备用 baseSelector 列表：主 schema 抽取为空时依次尝试，提升抗改版能力
    fallback_selectors: list[str] = field(default_factory=list)


SITES: list[SiteConfig] = [
    # ── 微博热搜 ──────────────────────────────────────────────────────────────
    SiteConfig(
        name="微博热搜",
        url="https://s.weibo.com/top/summary",
        wait_for="css:table.data tbody tr",
        timeout=35,
        schema={
            "name": "weibo_hot",
            "baseSelector": "table.data > tbody > tr",
            "fields": [
                {"name": "rank",  "selector": ".td-01",      "type": "text"},
                {"name": "title", "selector": ".td-02 > a",  "type": "text"},
                {"name": "link",  "selector": ".td-02 > a",  "type": "attribute", "attribute": "href"},
                {"name": "heat",  "selector": ".td-03 > span", "type": "text"},
            ],
        },
        # 备用：改版后表格类名可能变化，退化为 a 标签
        fallback_selectors=[
            "table tbody tr",
            ".data tbody tr",
        ],
    ),

    # ── 今日头条热榜 ──────────────────────────────────────────────────────────
    # 该 URL 实际返回 JSON 接口数据，页面渲染后热榜列表挂在 .hot-board-list 下；
    # 若直接访问接口域名失败，可改用 https://www.toutiao.com/ 首页。
    SiteConfig(
        name="今日头条",
        url="https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        wait_for="css:.hot-board-list .hot-board-item",
        timeout=35,
        schema={
            "name": "toutiao_hot",
            "baseSelector": ".hot-board-list .hot-board-item",
            "fields": [
                {"name": "title", "selector": ".hot-board-item-title", "type": "text"},
                {"name": "link",  "selector": "a",                     "type": "attribute", "attribute": "href"},
                {"name": "heat",  "selector": ".hot-board-item-heat",  "type": "text"},
            ],
        },
        fallback_selectors=[
            ".hot-list .item",
            "div[class*='hot-board'] div[class*='item']",
        ],
    ),

    # ── 新浪新闻 ──────────────────────────────────────────────────────────────
    SiteConfig(
        name="新浪新闻",
        url="https://news.sina.com.cn/",
        wait_for="css:.news-item-text, .ConsTit, .blk_focus",
        timeout=30,
        scroll=True,  # 首页内容多为懒加载，需滚动
        schema={
            "name": "sina_news",
            "baseSelector": ".news-item-text",
            "fields": [
                {"name": "title", "selector": "a",     "type": "text"},
                {"name": "link",  "selector": "a",     "type": "attribute", "attribute": "href"},
                {"name": "time",  "selector": ".time", "type": "text"},
            ],
        },
        # 新浪首页结构繁杂，多套容器并存，备选多个常见标题块
        fallback_selectors=[
            ".news-item h2 a, .news-item h3 a",
            ".blk_focus a",
            "h1 a[href*='news.sina'], h2 a[href*='news.sina']",
        ],
    ),

    # ── 网易新闻 ──────────────────────────────────────────────────────────────
    SiteConfig(
        name="网易新闻",
        url="https://news.163.com/",
        wait_for="css:.news_title, .titleBar, .news_default_news",
        timeout=30,
        scroll=True,
        schema={
            "name": "netease_news",
            "baseSelector": ".news_title",
            "fields": [
                {"name": "title", "selector": "a", "type": "text"},
                {"name": "link",  "selector": "a", "type": "attribute", "attribute": "href"},
            ],
        },
        fallback_selectors=[
            "#index-ba .news_title h3 a",
            ".news_default_news ul li a",
            "h3 a[href*='163.com']",
        ],
    ),

    # ── BBC 中文 ───────────────────────────────────────────────────────────────
    # BBC 多次改版，新版首页采用 Simorgh 框架，文章卡片用 data-testid 标记，
    # 常见值有 card-text-wrapper / internal-link 等；这里用宽松选择器并配多套备选。
    SiteConfig(
        name="BBC中文",
        url="https://www.bbc.com/zhongwen/simp",
        wait_for="css:main a[href*='/zhongwen/']",
        timeout=35,
        schema={
            "name": "bbc_chinese",
            # 直接锁定指向正文文章的内部链接，比依赖卡片容器更稳健
            "baseSelector": "main a[href*='/zhongwen/articles/'], main a[data-testid='internal-link']",
            "fields": [
                {"name": "title",   "selector": "h2, h3, span", "type": "text"},
                # 省略 selector → 直接读取 baseSelector 命中的 <a> 自身的 href
                {"name": "link",    "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p", "type": "text"},
            ],
        },
        # 旧版/不同布局的备用选择器
        fallback_selectors=[
            "main [data-testid='edinburgh-article']",
            "main [data-testid='card-text-wrapper']",
            "main article",
            "a[href*='/zhongwen/']",
        ],
    ),
]
