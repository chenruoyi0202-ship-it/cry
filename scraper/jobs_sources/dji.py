"""DJI (大疆) careers scraper.

DJI is headquartered in 深圳南山. The Chinese career portal at we.dji.com
exposes a JSON list endpoint. Field names below are best-effort; if the
shape changes, the safe_get fallbacks log a warning rather than crashing.
"""
from __future__ import annotations

from typing import Iterable, Optional

import requests

from .common import (
    DEFAULT_HEADERS,
    Job,
    http_error_snippet,
    is_shenzhen,
    normalize_category,
    parse_date,
    safe_get,
    with_retries,
)

HOMEPAGE = 'https://we.dji.com/zh-CN/social-recruitment'
ATTEMPTS: list[dict] = [
    {
        'url': 'https://we.dji.com/zh-CN/api/career/list/page',
        'body_template': {
            'departmentIds': [],
            'cityIds': [],
            'jobTypeIds': [],
            'experienceIds': [],
            'current': 1,
            'pageSize': 50,
            'keyword': '',
            'language': 'zh-CN',
        },
    },
    {
        'url': 'https://we.dji.com/api/career/list/page',
        'body_template': {
            'current': 1,
            'pageSize': 50,
            'keyword': '',
        },
    },
]
JOB_PAGE_TEMPLATE = 'https://we.dji.com/zh-CN/social-recruitment/{job_id}'

PAGE_SIZE = 50
MAX_PAGES = 30


def _seed_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.headers['Accept'] = 'application/json,text/plain,*/*'
    try:
        session.get(HOMEPAGE, timeout=20)
    except requests.RequestException as exc:
        print(f'  [dji] homepage seed warning: {exc}', flush=True)
    return session


def _try_endpoint(session: requests.Session, attempt: dict, page_no: int) -> dict:
    body = dict(attempt['body_template'])
    body['current'] = page_no
    body['pageNum'] = page_no
    headers = {
        'Content-Type': 'application/json',
        'Referer': HOMEPAGE,
        'Origin': 'https://we.dji.com',
    }
    resp = session.post(attempt['url'], json=body, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f'http {resp.status_code} from {attempt["url"]} :: {http_error_snippet(resp)}')
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f'non-json from {attempt["url"]} (status {resp.status_code}) :: {http_error_snippet(resp)}')
    code = data.get('code', data.get('status'))
    if code not in (0, 200, '0', '200', None):
        raise RuntimeError(f'dji {attempt["url"]} code={code} '
                           f'msg={data.get("message") or data.get("msg")}')
    return data


def _extract_list(data: dict) -> list[dict]:
    for path in (
        ('data', 'records'),
        ('data', 'list'),
        ('data', 'rows'),
        ('data', 'page', 'records'),
    ):
        v = safe_get(data, *path)
        if isinstance(v, list):
            return v
    return []


def _to_job(raw: dict) -> Optional[Job]:
    location_parts = []
    for key in ('cityName', 'city', 'workCity', 'workPlace', 'location'):
        v = safe_get(raw, key)
        if v and isinstance(v, str):
            location_parts.append(v)
    cities = safe_get(raw, 'cityList') or safe_get(raw, 'cities') or []
    if isinstance(cities, list):
        for c in cities:
            n = c.get('name') if isinstance(c, dict) else c
            if n and n not in location_parts:
                location_parts.append(str(n))
    location = ' / '.join(location_parts)
    if not is_shenzhen(location):
        return None
    job_id = (safe_get(raw, 'id') or safe_get(raw, 'jobId')
              or safe_get(raw, 'positionId'))
    if not job_id:
        return None
    title = (safe_get(raw, 'name') or safe_get(raw, 'jobName')
             or safe_get(raw, 'positionName') or '').strip()
    if not title:
        return None
    department = (safe_get(raw, 'departmentName') or safe_get(raw, 'department')
                  or safe_get(raw, 'orgName') or '')
    category_raw = (safe_get(raw, 'jobCategory') or safe_get(raw, 'category')
                    or safe_get(raw, 'jobType') or '')
    desc_parts = []
    resp_text = (safe_get(raw, 'jobDescription') or safe_get(raw, 'description')
                 or safe_get(raw, 'responsibility') or '').strip()
    req_text = (safe_get(raw, 'jobRequirement') or safe_get(raw, 'requirement')
                or safe_get(raw, 'qualification') or '').strip()
    if resp_text:
        desc_parts.append(f'岗位职责：\n{resp_text}')
    if req_text:
        desc_parts.append(f'任职要求：\n{req_text}')
    description = '\n\n'.join(desc_parts)
    posted = parse_date(safe_get(raw, 'publishTime') or safe_get(raw, 'updateTime')
                        or safe_get(raw, 'createTime'))
    url = JOB_PAGE_TEMPLATE.format(job_id=job_id)
    return Job(
        id=f'dji_{job_id}',
        company='dji',
        company_name='大疆',
        title=title,
        category=normalize_category(str(category_raw) or title),
        category_raw=str(category_raw or ''),
        location=location,
        department=str(department),
        posted_date=posted,
        url=url,
        source='we.dji.com',
        description=description,
    )


def fetch() -> list[Job]:
    session = _seed_session()
    chosen: Optional[dict] = None
    errors: list[str] = []
    for attempt in ATTEMPTS:
        try:
            with_retries(lambda: _try_endpoint(session, attempt, 1),
                         label=f'dji probe {attempt["url"]}', retries=2)
            chosen = attempt
            print(f'  [dji] using {attempt["url"]}', flush=True)
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{attempt["url"]}: {exc}')
            print(f'  [dji] probe failed: {exc}', flush=True)
    if chosen is None:
        raise RuntimeError('all dji endpoints rejected our payload :: '
                           + ' | '.join(errors))

    jobs: list[Job] = []
    for page in range(1, MAX_PAGES + 1):
        page_data = with_retries(lambda: _try_endpoint(session, chosen, page),
                                 label=f'dji p{page}')
        records = _extract_list(page_data)
        page_jobs = [j for j in (_to_job(r) for r in records) if j is not None]
        jobs.extend(page_jobs)
        print(f'  [dji] page {page}: raw={len(records)} kept={len(page_jobs)} '
              f'cumulative={len(jobs)}', flush=True)
        if not records or len(records) < PAGE_SIZE:
            break
    return jobs


if __name__ == '__main__':
    out = fetch()
    print(f'dji fetched {len(out)} jobs')
