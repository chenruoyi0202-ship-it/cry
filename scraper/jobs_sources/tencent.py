"""Tencent careers scraper.

Hits the public JSON endpoint used by https://careers.tencent.com/ — no auth,
no CSRF. Filters server-side by cityId=3 (深圳) and attrId=1 (社会招聘),
plus a defensive client-side check on LocationName so we still work if the
city dictionary changes.

Tencent's city map (observed on careers.tencent.com): 1=北京, 2=上海, 3=深圳,
4=广州, 5=成都. If cityId=3 returns 0 posts (e.g. their dictionary changed),
we transparently retry once with no city filter and rely entirely on the
client-side `is_shenzhen()` check.
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


def _fetch_page(session: requests.Session, page_index: int,
                city_id: str = '3') -> dict:
    params = {
        'timestamp': int(time.time() * 1000),
        'countryId': '',
        'cityId': city_id,              # 3 = 深圳
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
    posted = (parse_date(safe_get(raw, 'LastUpdateTime'))
              or parse_date(safe_get(raw, 'PostUpdateTime'))
              or parse_date(safe_get(raw, 'PostDate'))
              or parse_date(safe_get(raw, 'CreateTime')))
    description = (safe_get(raw, 'Responsibility', default='') or '').strip()
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
        description=description,
    )


def _crawl(session: requests.Session, city_id: str) -> list[Job]:
    jobs: list[Job] = []
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        page_data = with_retries(
            lambda: _fetch_page(session, page, city_id=city_id),
            label=f'tencent[city={city_id}] p{page}',
        )
        posts = safe_get(page_data, 'Data', 'Posts', default=[]) or []
        posts_list = list(posts)
        if total is None:
            total = safe_get(page_data, 'Data', 'Count', default=0) or 0
            print(f'  [tencent city={city_id}] reported total: {total}', flush=True)
        page_jobs = [j for j in (_to_job(p) for p in posts_list) if j is not None]
        jobs.extend(page_jobs)
        print(f'  [tencent city={city_id}] page {page}: raw={len(posts_list)} '
              f'kept={len(page_jobs)} cumulative={len(jobs)}', flush=True)
        if not posts_list or len(posts_list) < PAGE_SIZE:
            break
        if total and len(jobs) >= total:
            break
    return jobs


def fetch() -> list[Job]:
    """Fetch all current Shenzhen social-recruit postings from Tencent.

    Primary path uses cityId=3 (Shenzhen). If that yields zero, fall back to
    no city filter and rely on the client-side `is_shenzhen()` check — that
    handles the case where Tencent renumbers their city dictionary.
    """
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.headers['Accept'] = 'application/json,text/plain,*/*'

    jobs = _crawl(session, city_id='3')
    if jobs:
        return jobs
    print('  [tencent] cityId=3 returned 0 jobs; retrying without city filter',
          flush=True)
    return _crawl(session, city_id='')


if __name__ == '__main__':
    out = fetch()
    print(f'tencent fetched {len(out)} jobs')
    for j in out[:3]:
        print(j.to_dict())
