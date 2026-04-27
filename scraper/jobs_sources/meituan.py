"""Meituan careers scraper.

Hits the public POST endpoint that backs https://zhaopin.meituan.com/.
The site exposes social-recruit positions filterable by city; we filter
on '深圳' server-side and keep a defensive client-side check.

The first commit's body schema was rejected with code=1 on
careers.meituan.com — that endpoint expects a different shape. We now
target zhaopin.meituan.com's `/api/jobs/search/positions` endpoint and try
two body variants:
  1. The page-based shape with `cityName: "深圳"`
  2. A "city codes" shape using their internal city ID for Shenzhen (50)

If both fail we don't crash — we let the orchestrator preserve the previous
snapshot and surface a stale banner on the site.
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
ATTEMPTS: list[dict] = [
    {
        'url': 'https://zhaopin.meituan.com/api/jobs/search/positions',
        'body_template': {
            'pageNum': 1,
            'pageSize': 50,
            'keyword': '',
            'cityName': '深圳',
            'recruitType': 1,
        },
    },
    {
        'url': 'https://zhaopin.meituan.com/api/web/position/list',
        'body_template': {
            'pageNum': 1,
            'pageSize': 50,
            'keyword': '',
            'cityList': ['深圳'],
            'recruitType': 1,
        },
    },
    {
        'url': 'https://careers.meituan.com/api/c/search/v3',
        'body_template': {
            'pageNum': 1,
            'pageSize': 50,
            'keyword': '',
            'filterMap': {'cityList': ['深圳'], 'recruitType': [1]},
        },
    },
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


def _is_success(data: dict) -> bool:
    code = data.get('code', data.get('status'))
    if code in (0, 200, '0', '200', None):
        return True
    return False


def _extract_list(data: dict) -> list[dict]:
    for path in (
        ('data', 'list'),
        ('data', 'records'),
        ('data', 'items'),
        ('data', 'positions'),
        ('data', 'page', 'list'),
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
        ('data', 'page', 'totalCount'),
    ):
        v = safe_get(data, *path)
        if isinstance(v, int):
            return v
    return 0


def _try_endpoint(session: requests.Session, attempt: dict, page_no: int) -> dict:
    body = dict(attempt['body_template'])
    body['pageNum'] = page_no
    headers = {
        'Content-Type': 'application/json',
        'Referer': HOMEPAGE,
        'Origin': 'https://zhaopin.meituan.com',
    }
    resp = session.post(attempt['url'], json=body, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f'http {resp.status_code} from {attempt["url"]}')
    data = resp.json()
    if not _is_success(data):
        # A code != 0 means the endpoint rejected our request — surface enough
        # context so we can debug from the workflow log.
        raise RuntimeError(
            f'unexpected payload from {attempt["url"]}: '
            f'code={data.get("code", data.get("status"))} '
            f'msg={data.get("msg") or data.get("message")}'
        )
    return data


def _to_job(raw: dict) -> Optional[Job]:
    location_parts = []
    city = (safe_get(raw, 'cityName')
            or safe_get(raw, 'city')
            or safe_get(raw, 'workCity'))
    if city:
        location_parts.append(str(city))
    cities = (safe_get(raw, 'cityList')
              or safe_get(raw, 'cities')
              or safe_get(raw, 'workCityList')
              or [])
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
                    or safe_get(raw, 'jobType')
                    or '')
    department = (safe_get(raw, 'departmentName')
                  or safe_get(raw, 'businessName')
                  or safe_get(raw, 'department')
                  or safe_get(raw, 'orgName')
                  or '')
    posted = parse_date(safe_get(raw, 'publishTime')
                        or safe_get(raw, 'updateTime')
                        or safe_get(raw, 'createTime')
                        or safe_get(raw, 'postDate'))
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

    # Pick the first endpoint variant that responds with a valid payload.
    chosen: Optional[dict] = None
    last_err: Optional[Exception] = None
    for attempt in ATTEMPTS:
        try:
            with_retries(
                lambda: _try_endpoint(session, attempt, 1),
                label=f'meituan probe {attempt["url"]}',
                retries=2,
            )
            chosen = attempt
            print(f'  [meituan] using {attempt["url"]}', flush=True)
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f'  [meituan] probe failed: {exc}', flush=True)
    if chosen is None:
        raise RuntimeError(f'all meituan endpoints rejected our payload: {last_err}')

    jobs: list[Job] = []
    total: Optional[int] = None
    for page in range(1, MAX_PAGES + 1):
        page_data = with_retries(
            lambda: _try_endpoint(session, chosen, page),
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
