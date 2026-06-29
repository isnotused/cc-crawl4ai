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

    # ── Reuters ───────────────────────────────────────────────────────────────
    SiteConfig(
        name="Reuters",
        url="https://www.reuters.com/",
        wait_for="css:[data-testid='media-story-card']",
        timeout=40,
        scroll=True,
        schema={
            "name": "reuters",
            "baseSelector": "[data-testid='media-story-card']",
            "fields": [
                {"name": "title",   "selector": "a[data-testid='Heading'] h3, a[data-testid='Heading']", "type": "text"},
                {"name": "link",    "selector": "a[data-testid='Heading']", "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p", "type": "text"},
                {"name": "time",    "selector": "time", "type": "text"},
            ],
        },
        fallback_selectors=["article[class*='story-card']", "main article", "main h3 a"],
    ),

    # ── BBC News ──────────────────────────────────────────────────────────────
    # 直接锁定指向正文文章的内部链接（与 BBC中文 策略一致），比依赖容器类名更稳健
    SiteConfig(
        name="BBC News",
        url="https://www.bbc.com/news",
        wait_for="css:main a[href*='/news/articles/']",
        timeout=35,
        schema={
            "name": "bbc_news",
            "baseSelector": "main a[href*='/news/articles/']",
            "fields": [
                {"name": "title",   "selector": "h3, h2, p[class*='headline'], span", "type": "text"},
                {"name": "link",    "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p[data-testid='card-description']",  "type": "text"},
                {"name": "time",    "selector": "time",                                "type": "text"},
            ],
        },
        fallback_selectors=[
            "[data-testid='edinburgh-article']",
            "[data-testid='card-text-wrapper']",
            "main article",
        ],
    ),

    # ── AP News ───────────────────────────────────────────────────────────────
    SiteConfig(
        name="AP News",
        url="https://apnews.com/",
        wait_for="css:.PagePromo, .FeedCard",
        timeout=30,
        schema={
            "name": "ap_news",
            "baseSelector": ".PagePromo",
            "fields": [
                {"name": "title",   "selector": ".PagePromo-title a",        "type": "text"},
                {"name": "link",    "selector": ".PagePromo-title a",        "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": ".PagePromo-description p",  "type": "text"},
                {"name": "time",    "selector": "bsp-timestamp, .Timestamp", "type": "text"},
            ],
        },
        fallback_selectors=[".FeedCard", "article[data-key]", "main h2 a"],
    ),

    # ── Bloomberg ─────────────────────────────────────────────────────────────
    # Cloudflare 保护较强，CSS 抽取失败率高，markdown 兜底是主要路径
    SiteConfig(
        name="Bloomberg",
        url="https://www.bloomberg.com/",
        wait_for="css:[data-type='story'], main article",
        timeout=45,
        scroll=True,
        schema={
            "name": "bloomberg",
            "baseSelector": "[data-type='story']",
            "fields": [
                {"name": "title", "selector": "[class*='headline'], h3, h2", "type": "text"},
                {"name": "link",  "selector": "a", "type": "attribute", "attribute": "href"},
                {"name": "time",  "selector": "time", "type": "text"},
            ],
        },
        fallback_selectors=["[class*='story-package'] article", "[class*='story-list'] li", "main article"],
    ),

    # ── Financial Times ───────────────────────────────────────────────────────
    # 使用 Origami 设计系统，类名较稳定
    SiteConfig(
        name="Financial Times",
        url="https://www.ft.com/",
        wait_for="css:.js-stream-article, [data-trackable]",
        timeout=40,
        schema={
            "name": "financial_times",
            "baseSelector": ".js-stream-article",
            "fields": [
                {"name": "title",   "selector": ".o-teaser__heading a, h2 a",    "type": "text"},
                {"name": "link",    "selector": ".o-teaser__heading a, h2 a",    "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": ".o-teaser__standfirst, p",      "type": "text"},
                {"name": "time",    "selector": "time, .o-date",                 "type": "text"},
            ],
        },
        fallback_selectors=["[data-trackable='article-teaser']", "article[class*='teaser']", "main h2 a"],
    ),

    # ── CNBC ──────────────────────────────────────────────────────────────────
    SiteConfig(
        name="CNBC",
        url="https://www.cnbc.com/",
        wait_for="css:[class*='Card-titleContainer'], [class*='RiverHeadline']",
        timeout=35,
        scroll=True,
        schema={
            "name": "cnbc",
            "baseSelector": "[class*='Card-titleContainer']",
            "fields": [
                {"name": "title",   "selector": "a",                           "type": "text"},
                {"name": "link",    "selector": "a",                           "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "[class*='Card-description']", "type": "text"},
                {"name": "time",    "selector": "[class*='Card-time'], time",  "type": "text"},
            ],
        },
        fallback_selectors=["[class*='RiverHeadline']", "article h2 a", ".LatestNews__headline a"],
    ),

    # ── TechCrunch ────────────────────────────────────────────────────────────
    SiteConfig(
        name="TechCrunch",
        url="https://techcrunch.com/",
        wait_for="css:article.loop-card, .post-block",
        timeout=30,
        schema={
            "name": "techcrunch",
            "baseSelector": "article.loop-card",
            "fields": [
                {"name": "title",   "selector": "h2.loop-card__title a, h2 a",     "type": "text"},
                {"name": "link",    "selector": "h2.loop-card__title a, h2 a",     "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": ".loop-card__description, p",      "type": "text"},
                {"name": "time",    "selector": "time",                             "type": "text"},
            ],
        },
        fallback_selectors=["article.post-block", ".post-block", "article h2 a"],
    ),

    # ── The Verge ─────────────────────────────────────────────────────────────
    # Vox Media Chorus CMS，2022 年改版后使用 atomic CSS
    SiteConfig(
        name="The Verge",
        url="https://www.theverge.com/",
        wait_for="css:.duet--content-cards--content-card, article",
        timeout=35,
        scroll=True,
        schema={
            "name": "the_verge",
            "baseSelector": ".duet--content-cards--content-card",
            "fields": [
                {"name": "title",   "selector": "h2 a, h3 a", "type": "text"},
                {"name": "link",    "selector": "h2 a, h3 a", "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p",           "type": "text"},
                {"name": "time",    "selector": "time",        "type": "text"},
            ],
        },
        fallback_selectors=["article", "h2[class*='font-bold'] a", "main h2 a"],
    ),

    # ── Wired ─────────────────────────────────────────────────────────────────
    # Next.js + styled-components，类名含 SummaryItem 前缀
    SiteConfig(
        name="Wired",
        url="https://www.wired.com/",
        wait_for="css:[class*='SummaryItemWrapper'], [class*='SummaryItem']",
        timeout=35,
        scroll=True,
        schema={
            "name": "wired",
            "baseSelector": "[class*='SummaryItemWrapper']",
            "fields": [
                {"name": "title",   "selector": "[class*='SummaryItemHedLink'], h2 a", "type": "text"},
                {"name": "link",    "selector": "[class*='SummaryItemHedLink'], h2 a", "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "[class*='SummaryItemDek'], p",        "type": "text"},
                {"name": "time",    "selector": "time",                                 "type": "text"},
            ],
        },
        fallback_selectors=["[class*='SummaryItem']", "article", "main h2 a"],
    ),

    # ── Science Daily ─────────────────────────────────────────────────────────
    # 传统 PHP 站点，结构稳定，#latest_news 下的 .story 列表
    SiteConfig(
        name="Science Daily",
        url="https://www.sciencedaily.com/",
        wait_for="css:#latest_news .story, .latest .story",
        timeout=30,
        schema={
            "name": "science_daily",
            "baseSelector": "#latest_news .story",
            "fields": [
                {"name": "title",   "selector": "h3 a",               "type": "text"},
                {"name": "link",    "selector": "h3 a",               "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p:not(.text-muted)", "type": "text"},
                {"name": "time",    "selector": ".text-muted",        "type": "text"},
            ],
        },
        fallback_selectors=[".latest .story", "#featured_news article", "main h3 a"],
    ),

    # ── New Scientist ─────────────────────────────────────────────────────────
    SiteConfig(
        name="New Scientist",
        url="https://www.newscientist.com/",
        wait_for="css:[class*='CardBase'], article",
        timeout=35,
        schema={
            "name": "new_scientist",
            "baseSelector": "article[class*='CardBase'], article",
            "fields": [
                {"name": "title",   "selector": "h3 a, h2 a", "type": "text"},
                {"name": "link",    "selector": "h3 a, h2 a", "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p",           "type": "text"},
                {"name": "time",    "selector": "time",        "type": "text"},
            ],
        },
        fallback_selectors=["[class*='article-card']", "[class*='CardBase']", "main article h3 a"],
    ),

    # ── ESPN ──────────────────────────────────────────────────────────────────
    SiteConfig(
        name="ESPN",
        url="https://www.espn.com/",
        wait_for="css:.headlineStack__list, [class*='contentItem']",
        timeout=45,
        scroll=True,
        schema={
            "name": "espn",
            "baseSelector": ".headlineStack__list .headlineStack__item",
            "fields": [
                {"name": "title", "selector": "a", "type": "text"},
                {"name": "link",  "selector": "a", "type": "attribute", "attribute": "href"},
            ],
        },
        fallback_selectors=["[class*='contentItem']", "[class*='news__item']", "main article h2 a"],
    ),

    # ── BBC Sport ─────────────────────────────────────────────────────────────
    SiteConfig(
        name="BBC Sport",
        url="https://www.bbc.com/sport",
        wait_for="css:[data-testid='card-text-wrapper'], main article",
        timeout=35,
        schema={
            "name": "bbc_sport",
            "baseSelector": "[data-testid='card-text-wrapper']",
            "fields": [
                {"name": "title",   "selector": "h3[data-testid='card-headline'], h3",    "type": "text"},
                {"name": "link",    "selector": "a[data-testid='internal-link'], a",      "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p[data-testid='card-description'], p",  "type": "text"},
                {"name": "time",    "selector": "time",                                    "type": "text"},
            ],
        },
        fallback_selectors=["[data-testid='edinburgh-article']", "main article", "main h3 a[href*='/sport/']"],
    ),

    # ── IGN ───────────────────────────────────────────────────────────────────
    # .item 过于宽泛会匹配导航过滤按钮，改用 main 区域内的 article 语义标签
    SiteConfig(
        name="IGN",
        url="https://www.ign.com/",
        wait_for="css:main article, [class*='content-item']",
        timeout=40,
        scroll=True,
        schema={
            "name": "ign",
            "baseSelector": "main article",
            "fields": [
                {"name": "title",   "selector": "h2 a, h3 a, h4 a",  "type": "text"},
                {"name": "link",    "selector": "h2 a, h3 a, h4 a",  "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p",                   "type": "text"},
                {"name": "time",    "selector": "time",                "type": "text"},
            ],
        },
        fallback_selectors=[
            "[class*='content-item']",
            "[class*='item-body']",
            "main a[href*='/articles/']",
        ],
    ),

    # ── Kotaku ────────────────────────────────────────────────────────────────
    # G/O Media CMS 类名混淆，用语义化 article[data-id] 更稳定
    SiteConfig(
        name="Kotaku",
        url="https://kotaku.com/",
        wait_for="css:article[data-id], article",
        timeout=35,
        schema={
            "name": "kotaku",
            "baseSelector": "article[data-id]",
            "fields": [
                {"name": "title",   "selector": "h2 a, h1 a", "type": "text"},
                {"name": "link",    "selector": "h2 a, h1 a", "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": "p",           "type": "text"},
                {"name": "time",    "selector": "time",        "type": "text"},
            ],
        },
        fallback_selectors=[".js-curation-placement article", "[class*='storyWrapper']", "main h2 a"],
    ),

    # ── Polygon ───────────────────────────────────────────────────────────────
    # Vox Media Chorus CMS，.c-entry-box 是有文档记录的官方类名
    SiteConfig(
        name="Polygon",
        url="https://www.polygon.com/",
        wait_for="css:.c-entry-box, article",
        timeout=35,
        schema={
            "name": "polygon",
            "baseSelector": ".c-entry-box--compact",
            "fields": [
                {"name": "title",   "selector": "h2.c-entry-box--compact__title a, h2 a", "type": "text"},
                {"name": "link",    "selector": "h2.c-entry-box--compact__title a, h2 a", "type": "attribute", "attribute": "href"},
                {"name": "summary", "selector": ".c-entry-box--compact__dek, p",           "type": "text"},
                {"name": "time",    "selector": "time",                                     "type": "text"},
            ],
        },
        fallback_selectors=[".c-entry-box", "article", "main h2 a"],
    ),
]
