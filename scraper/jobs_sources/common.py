"""Shared helpers for the Shenzhen big-tech jobs scrapers."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable, Optional

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

DEFAULT_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

# Categories shown in the UI dropdown. Source-specific labels are mapped here
# via CATEGORY_RULES; anything that does not match falls back to "其他".
CATEGORIES = ['技术', '产品', '设计', '运营', '市场', '职能', '其他']

# Each rule: (category, list of substrings that, if found in the raw label,
# classify the job into that category). Order matters — first match wins.
CATEGORY_RULES = [
    ('技术', ['技术', '工程', '研发', '开发', '算法', '架构', '运维',
             '测试', '安全', '数据', 'AI', '机器学习', 'NLP', 'CV',
             'Engineer', 'Developer', 'SRE', 'QA', 'Tech']),
    ('产品', ['产品', 'Product', 'PM']),
    ('设计', ['设计', '视觉', '用研', 'UX', 'UI', 'Design']),
    ('运营', ['运营', '内容', '编辑', 'Operation']),
    ('市场', ['市场', '商业', '销售', '公关', '品牌', 'Marketing', 'Sales', 'BD']),
    ('职能', ['人力', '财务', '法务', '行政', '战略', '投资', '审计',
             'HR', 'Finance', 'Legal', 'Admin', 'Strategy']),
]


def normalize_category(raw: Optional[str]) -> str:
    """Map a source-specific category label to one of CATEGORIES."""
    if not raw:
        return '其他'
    text = raw
    for category, needles in CATEGORY_RULES:
        for needle in needles:
            if needle in text:
                return category
    return '其他'


SHENZHEN_TOKENS = ('深圳', 'Shenzhen', 'shenzhen', 'SZ')


def is_shenzhen(location_text: Optional[str]) -> bool:
    """True if the location string mentions Shenzhen in any common form."""
    if not location_text:
        return False
    return any(token in location_text for token in SHENZHEN_TOKENS)


def safe_get(d: Any, *path: Any, default: Any = None) -> Any:
    """Walk nested dict/list paths returning default on any miss."""
    cur: Any = d
    for key in path:
        if cur is None:
            return default
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default


def parse_date(text: Optional[str]) -> Optional[str]:
    """Extract a YYYY-MM-DD date from various source formats.

    Handles ISO-ish (2026-04-25, 2026/4/25, 2026.4.25), Chinese (2026年4月25日),
    and epoch (10- or 13-digit) inputs.
    """
    if not text:
        return None
    text = str(text)
    # ISO-ish separators
    m = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', text)
    if m:
        y, mo, d = m.groups()
        return f'{y}-{int(mo):02d}-{int(d):02d}'
    # Chinese format: 2026年4月25日 / 2026年04月25日
    m = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日?', text)
    if m:
        y, mo, d = m.groups()
        return f'{y}-{int(mo):02d}-{int(d):02d}'
    # Epoch ms or seconds
    m = re.fullmatch(r'\d{10,13}', text)
    if m:
        ts = int(text)
        if ts > 10_000_000_000:
            ts //= 1000
        return time.strftime('%Y-%m-%d', time.gmtime(ts))
    return None


@dataclass
class Job:
    id: str
    company: str          # short slug: tencent / bytedance / meituan
    company_name: str     # display name: 腾讯 / 字节跳动 / 美团
    title: str
    category: str         # one of CATEGORIES
    category_raw: str
    location: str
    department: str
    posted_date: Optional[str]
    url: str
    source: str           # host of the original posting
    description: str = '' # job responsibilities + requirements; used by resume match

    def to_dict(self) -> dict:
        return asdict(self)


def with_retries(
    fn: Callable[[], Any],
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    label: str = '',
) -> Any:
    """Call fn() up to `retries` times with exponential backoff.

    Mirrors the loop pattern in scraper/scrape_ccass.py.
    """
    last_err: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = base_delay * (2 ** attempt)
            print(f'  [{label}] attempt {attempt + 1}/{retries} failed: {exc}; '
                  f'waiting {wait:.1f}s', flush=True)
            time.sleep(wait)
    raise RuntimeError(f'{label}: all {retries} attempts failed: {last_err}')


def dedupe_jobs(jobs: Iterable[Job]) -> list[Job]:
    """Deduplicate jobs by id (last write wins)."""
    seen: dict[str, Job] = {}
    for job in jobs:
        seen[job.id] = job
    return list(seen.values())
