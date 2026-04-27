"""Meituan careers scraper.

Hits the public POST endpoint that backs https://zhaopin.meituan.com/.
The site exposes social-recruit positions filterable by city; we filter
on '深圳' server-side and keep a defensive client-side check.

The response shape varies slightly between deployments, so all parsing is
done with safe_get and fallbacks.
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

HOMEPAGE = 'https://zhaopin.meituan.com/web/social'
# We try multiple known endpoints; the first one that returns a JSON list wins.
API_CANDIDATES = [
    'https://zhaopin.meituan.com/api/web/position/list',
    'https://campus.meituan.com/api/web/position/list',
    'https://careers.meituan.com/api/job/list/search',
]
JOB_PAGE_TEMPLATE = 'https://zhaopin.meituan.com/web/position/{job_id}/detail'

PAGE_SIZE = 50
MAX_PAGES = 40


def _seed_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.headers['Accept'] = 'application/json,text/plain,*/*'
    try:
        session.get(HOMEPAGE, timeout=20)
    except requests.RequestException as exc:
        print(f'  [meituan] homepage seed warning: {exc}', flush=True)
    return session


def _fetch_page(session: requests.Session, page_no: int) -> dict:
    headers = {
        'Content-Type': 'application/json',
        'Referer': HOMEPAGE,
        'Origin': 'https://zhaopin.meituan.com',
    }
    body = {
        'pageNo': page_no,
        'pageSize': PAGE_SIZE,
        'keyword': '',
        'cityList': ['深圳'],
        'recruitType': 1,    # 1 = 社招
    }
    last_err: Optional[Exception] = None
    for url in API_CANDIDATES:
        try:
            resp = session.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f'http {resp.status_code}')
            data = resp.json()
            code = data.get('code', data.get('status'))
            # Accept any code that's 0/200 OR has a populated list — different
            # builds report success differently.
            list_path = (
                safe_get(data, 'data', 'list')
                or safe_get(data, 'data', 'records')
                or safe_get(data, 'data', 'items')
                or safe_get(data, 'data')
            )
            if isinstance(list_path, list):
                return data
            if code in (0, 200, '0', '200'):
                return data
            raise RuntimeError(f'unexpected payload from {url}: code={code}')
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f'  [meituan] {url} -> {exc}', flush=True)
            continue
    raise RuntimeError(f'meituan: all endpoints failed: {last_err}')


def _extract_list(data: dict) -> list[dict]:
    for path in (
        ('data', 'list'),
        ('data', 'records'),
        ('data', 'items'),
        ('data', 'positions'),
    ):
        v = safe_get(data, *path)
        if isinstance(v, list):
            return v
    v = safe_get(data, 'data')
    return v if isinstance(v, list) else []


def _extract_total(data: dict) -> int:
    for path in (
        ('data', 'totalCount'),
        ('data', 'total'),
        ('data', 'count'),
    ):
        v = safe_get(data, *path)
        if isinstance(v, int):
            return v
    return 0


def _to_job(raw: dict) -> Optional[Job]:
    location_parts = []
    city = safe_get(raw, 'cityName') or safe_get(raw, 'city')
    if city:
        location_parts.append(str(city))
    cities = safe_get(raw, 'cityList') or safe_get(raw, 'cities') or []
    if isinstance(cities, list):
        for c in cities:
            name = c.get('name') if isinstance(c, dict) else c
            if name and name not in location_parts:
                location_parts.append(str(name))
    location = ' / '.join(location_parts)
    if not is_shenzhen(location):
        return None
    job_id = (safe_get(raw, 'jobId')
              or safe_get(raw, 'positionId')
              or safe_get(raw, 'id'))
    if not job_id:
        return None
    title = (safe_get(raw, 'jobName')
             or safe_get(raw, 'positionName')
             or safe_get(raw, 'name')
             or '').strip()
    if not title:
        return None
    category_raw = (safe_get(raw, 'jobCategory')
                    or safe_get(raw, 'positionType')
                    or safe_get(raw, 'category')
                    or '')
    department = (safe_get(raw, 'departmentName')
                  or safe_get(raw, 'businessName')
                  or safe_get(raw, 'department')
                  or '')
    posted = parse_date(safe_get(raw, 'publishTime')
                        or safe_get(raw, 'updateTime')
                        or safe_get(raw, 'createTime'))
    url = JOB_PAGE_TEMPLATE.format(job_id=job_id)
    return Job(
        id=f'meituan_{job_id}',
        company='meituan',
        company_name='美团',
        title=title,
        category=normalize_category(str(category_raw) or title),
        category_raw=str(category_raw or ''),
        location=location,
        department=str(department),
        posted_date=posted,
        url=url,
        source='zhaopin.meituan.com',
    )


def fetch() -> list[Job]:
    session = _seed_session()
    jobs: list[Job] = []
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        page_data = with_retries(
            lambda: _fetch_page(session, page),
            label=f'meituan p{page}',
        )
        posts: Iterable[dict] = _extract_list(page_data)
        posts = list(posts)
        if total is None:
            total = _extract_total(page_data)
            print(f'  [meituan] reported total: {total}', flush=True)
        page_jobs = [j for j in (_to_job(p) for p in posts) if j is not None]
        jobs.extend(page_jobs)
        print(f'  [meituan] page {page}: raw={len(posts)} kept={len(page_jobs)} '
              f'cumulative={len(jobs)}', flush=True)
        if not posts or len(posts) < PAGE_SIZE:
            break
        if total and len(jobs) >= total:
            break
    return jobs


if __name__ == '__main__':
    out = fetch()
    print(f'meituan fetched {len(out)} jobs')
    for j in out[:3]:
        print(j.to_dict())
