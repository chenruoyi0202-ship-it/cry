"""Tencent careers scraper.

Hits the public JSON endpoint used by https://careers.tencent.com/ — no auth,
no CSRF. Filters server-side by cityId=2 (深圳) and attrId=1 (社会招聘),
plus a defensive client-side check on LocationName so we still work if the
city dictionary changes.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

import requests

from .common import (
    DEFAULT_HEADERS,
    Job,
    is_shenzhen,
    normalize_category,
    parse_date,
    safe_get,
    with_retries,
)

API_URL = 'https://careers.tencent.com/tencentcareer/api/post/Query'
JOB_PAGE_TEMPLATE = 'https://careers.tencent.com/jobdesc.html?postId={post_id}'

PAGE_SIZE = 100
MAX_PAGES = 50  # safety cap; Tencent SZ social currently ~10-20 pages


def _fetch_page(session: requests.Session, page_index: int) -> dict:
    params = {
        'timestamp': int(time.time() * 1000),
        'countryId': '',
        'cityId': '2',                  # Shenzhen
        'bgIds': '',
        'productId': '',
        'categoryId': '',
        'parentCategoryId': '',
        'attrId': '1',                  # 社会招聘
        'keyword': '',
        'pageIndex': page_index,
        'pageSize': PAGE_SIZE,
        'language': 'zh-cn',
        'area': 'cn',
    }
    resp = session.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get('Code') != 200:
        raise RuntimeError(f'tencent api Code={data.get("Code")} msg={data.get("Msg")}')
    return data


def _to_job(raw: dict) -> Optional[Job]:
    location = safe_get(raw, 'LocationName', default='') or ''
    if not is_shenzhen(location):
        return None
    post_id = safe_get(raw, 'PostId') or safe_get(raw, 'RecruitPostId')
    if not post_id:
        return None
    title = (safe_get(raw, 'RecruitPostName', default='') or '').strip()
    if not title:
        return None
    category_raw = safe_get(raw, 'CategoryName', default='') or ''
    department = safe_get(raw, 'BGName', default='') or ''
    product = safe_get(raw, 'ProductName', default='') or ''
    if product and product != department:
        department = f'{department} · {product}' if department else product
    url = safe_get(raw, 'PostURL') or JOB_PAGE_TEMPLATE.format(post_id=post_id)
    posted = parse_date(safe_get(raw, 'LastUpdateTime'))
    return Job(
        id=f'tencent_{post_id}',
        company='tencent',
        company_name='腾讯',
        title=title,
        category=normalize_category(category_raw or title),
        category_raw=category_raw,
        location=location,
        department=department,
        posted_date=posted,
        url=url,
        source='careers.tencent.com',
    )


def fetch() -> list[Job]:
    """Fetch all current Shenzhen social-recruit postings from Tencent."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.headers['Accept'] = 'application/json,text/plain,*/*'

    jobs: list[Job] = []
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        page_data = with_retries(
            lambda: _fetch_page(session, page),
            label=f'tencent p{page}',
        )
        posts: Iterable[dict] = safe_get(page_data, 'Data', 'Posts', default=[]) or []
        if total is None:
            total = safe_get(page_data, 'Data', 'Count', default=0) or 0
            print(f'  [tencent] reported total: {total}', flush=True)
        page_jobs = [j for j in (_to_job(p) for p in posts) if j is not None]
        jobs.extend(page_jobs)
        print(f'  [tencent] page {page}: raw={len(list(posts))} kept={len(page_jobs)} '
              f'cumulative={len(jobs)}', flush=True)
        if not posts or len(posts) < PAGE_SIZE:
            break
        if total and len(jobs) >= total:
            break
    return jobs


if __name__ == '__main__':
    out = fetch()
    print(f'tencent fetched {len(out)} jobs')
    for j in out[:3]:
        print(j.to_dict())
