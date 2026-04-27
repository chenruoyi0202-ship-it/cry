"""ByteDance jobs scraper.

The site at jobs.bytedance.com gates its API behind a CSRF cookie. We seed
the cookie by GETting the listing page, then echo the token back in both
the `x-csrf-token` header and (automatically via the Session) the cookie
jar. Falls back gracefully if the token isn't present.

ByteDance location codes (observed): CT_6 = 上海, CT_138 = 深圳, CT_109 =
北京. We use `CT_138` and fall back to no location filter (relying on
client-side `is_shenzhen()`) if the primary call returns zero posts.
"""
from __future__ import annotations

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

HOMEPAGE = 'https://jobs.bytedance.com/experienced/position?location=CT_138'
API_URL = 'https://jobs.bytedance.com/api/v1/search/job/posts'
JOB_PAGE_TEMPLATE = 'https://jobs.bytedance.com/experienced/position/{job_id}/detail'

PAGE_SIZE = 100
MAX_PAGES = 60  # safety cap


def _seed_session() -> tuple[requests.Session, Optional[str]]:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.headers['Accept'] = 'application/json,text/plain,*/*'
    try:
        session.get(HOMEPAGE, timeout=20)
    except requests.RequestException as exc:
        print(f'  [bytedance] homepage seed warning: {exc}', flush=True)
    csrf = session.cookies.get('atsx-csrf-token')
    return session, csrf


def _fetch_page(session: requests.Session, csrf: Optional[str], offset: int,
                location_codes: list[str]) -> dict:
    headers = {
        'Content-Type': 'application/json',
        'Referer': HOMEPAGE,
        'Origin': 'https://jobs.bytedance.com',
        'portal-platform': 'official',
        'portal-channel': 'office',
    }
    if csrf:
        headers['x-csrf-token'] = csrf
    body = {
        'keyword': '',
        'limit': PAGE_SIZE,
        'offset': offset,
        'job_category_id_list': [],
        'tag_id_list': [],
        'location_code_list': location_codes,
        'subject_id_list': [],
        'head_id_list': [],
        'sequence_id_list': [],
        'portal_type': 2,           # 社招
        'portal_entrance': 1,
    }
    resp = session.post(API_URL, json=body, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get('code') != 0:
        raise RuntimeError(f'bytedance api code={data.get("code")} '
                           f'msg={data.get("message")}')
    return data


def _location_text(raw: dict) -> str:
    parts: list[str] = []
    name = safe_get(raw, 'city_info', 'name')
    if name:
        parts.append(str(name))
    locations = safe_get(raw, 'city_list', default=[]) or []
    for loc in locations:
        n = safe_get(loc, 'name')
        if n and n not in parts:
            parts.append(str(n))
    return ' / '.join(parts)


def _to_job(raw: dict) -> Optional[Job]:
    location = _location_text(raw)
    if not is_shenzhen(location):
        return None
    job_id = safe_get(raw, 'id') or safe_get(raw, 'job_post_id')
    if not job_id:
        return None
    title = (safe_get(raw, 'title') or safe_get(raw, 'name') or '').strip()
    if not title:
        return None
    category_raw = (safe_get(raw, 'job_category', 'name')
                    or safe_get(raw, 'job_category_name')
                    or '')
    department_parts = []
    sub_dept = safe_get(raw, 'sub_department')
    department_root = safe_get(raw, 'department', 'name')
    if department_root:
        department_parts.append(str(department_root))
    if isinstance(sub_dept, dict):
        sub_name = safe_get(sub_dept, 'name')
        if sub_name and sub_name != department_root:
            department_parts.append(str(sub_name))
    department = ' · '.join(department_parts)
    url = JOB_PAGE_TEMPLATE.format(job_id=job_id)
    posted_raw = (safe_get(raw, 'publish_time')
                  or safe_get(raw, 'publish_date')
                  or safe_get(raw, 'modify_time'))
    posted = parse_date(posted_raw) if posted_raw is not None else None
    return Job(
        id=f'bytedance_{job_id}',
        company='bytedance',
        company_name='字节跳动',
        title=title,
        category=normalize_category(category_raw or title),
        category_raw=str(category_raw or ''),
        location=location,
        department=department,
        posted_date=posted,
        url=url,
        source='jobs.bytedance.com',
    )


def _crawl(session: requests.Session, csrf: Optional[str],
           location_codes: list[str]) -> list[Job]:
    jobs: list[Job] = []
    total: Optional[int] = None
    label = ','.join(location_codes) if location_codes else 'no-loc'
    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        page_data = with_retries(
            lambda: _fetch_page(session, csrf, offset, location_codes),
            label=f'bytedance[{label}] off{offset}',
        )
        posts: Iterable[dict] = safe_get(page_data, 'data', 'job_post_list', default=[]) or []
        posts = list(posts)
        if total is None:
            total = safe_get(page_data, 'data', 'count', default=0) or 0
            print(f'  [bytedance {label}] reported total: {total}', flush=True)
        page_jobs = [j for j in (_to_job(p) for p in posts) if j is not None]
        jobs.extend(page_jobs)
        print(f'  [bytedance {label}] page {page + 1}: raw={len(posts)} '
              f'kept={len(page_jobs)} cumulative={len(jobs)}', flush=True)
        if not posts or len(posts) < PAGE_SIZE:
            break
        if total and offset + len(posts) >= total:
            break
    return jobs


def fetch() -> list[Job]:
    session, csrf = _seed_session()
    if not csrf:
        print('  [bytedance] no csrf cookie present; will try without — '
              'expect failure if upstream changed', flush=True)

    jobs = _crawl(session, csrf, ['CT_138'])
    if jobs:
        return jobs
    print('  [bytedance] CT_138 returned 0 jobs; retrying without location filter',
          flush=True)
    return _crawl(session, csrf, [])


if __name__ == '__main__':
    out = fetch()
    print(f'bytedance fetched {len(out)} jobs')
    for j in out[:3]:
        print(j.to_dict())
