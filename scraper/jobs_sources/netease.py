"""NetEase (网易) careers scraper.

NetEase is HQ in 杭州 with offices in 广州/北京/上海. Shenzhen presence is
limited but worth checking — filter strictly on 深圳 location.
"""
from __future__ import annotations

from typing import Optional

import requests

from .common import (
    DEFAULT_HEADERS, Job, is_shenzhen, normalize_category, parse_date,
    safe_get, with_retries,
)

HOMEPAGE = 'https://hr.163.com/'
ATTEMPTS: list[dict] = [
    {
        'url': 'https://hr.163.com/api/hr163/position/searchPosition',
        'body_template': {'page': 1, 'pageSize': 50, 'keyword': '',
                          'cityName': '深圳', 'type': ''},
    },
    {
        'url': 'https://hr.163.com/api/hr163/position/list',
        'body_template': {'pageNum': 1, 'pageSize': 50, 'cityName': '深圳'},
    },
]
JOB_PAGE_TEMPLATE = 'https://hr.163.com/position/{job_id}.html'

PAGE_SIZE = 50
MAX_PAGES = 20


def _seed_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    s.headers['Accept'] = 'application/json,text/plain,*/*'
    try:
        s.get(HOMEPAGE, timeout=20)
    except requests.RequestException:
        pass
    return s


def _try_endpoint(session: requests.Session, attempt: dict, page_no: int) -> dict:
    body = dict(attempt['body_template'])
    for k in ('page', 'pageNum', 'current'):
        if k in body:
            body[k] = page_no
    headers = {'Content-Type': 'application/json', 'Referer': HOMEPAGE,
               'Origin': 'https://hr.163.com'}
    resp = session.post(attempt['url'], json=body, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f'http {resp.status_code} from {attempt["url"]}')
    data = resp.json()
    code = data.get('code', data.get('status'))
    if code not in (0, 200, '0', '200', None):
        raise RuntimeError(f'netease {attempt["url"]} code={code} '
                           f'msg={data.get("msg") or data.get("message")}')
    return data


def _extract_list(data: dict) -> list[dict]:
    for path in (('data', 'list'), ('data', 'records'), ('data', 'positions'),
                 ('data', 'page', 'list'), ('data',)):
        v = safe_get(data, *path)
        if isinstance(v, list):
            return v
    return []


def _to_job(raw: dict) -> Optional[Job]:
    location_parts = []
    for key in ('workPlace', 'cityName', 'city', 'workCity'):
        v = safe_get(raw, key)
        if v and isinstance(v, str):
            location_parts.append(v)
    location = ' / '.join(location_parts)
    if not is_shenzhen(location):
        return None
    job_id = safe_get(raw, 'positionId') or safe_get(raw, 'id') or safe_get(raw, 'jobId')
    if not job_id:
        return None
    title = (safe_get(raw, 'positionName') or safe_get(raw, 'name')
             or safe_get(raw, 'jobName') or '').strip()
    if not title:
        return None
    department = (safe_get(raw, 'productName') or safe_get(raw, 'departmentName')
                  or safe_get(raw, 'department') or '')
    category_raw = (safe_get(raw, 'firstPostType') or safe_get(raw, 'positionType')
                    or safe_get(raw, 'category') or '')
    parts = []
    resp_text = (safe_get(raw, 'requirement') or safe_get(raw, 'description')
                 or safe_get(raw, 'positionDesc') or '').strip()
    if resp_text:
        parts.append(resp_text)
    description = '\n\n'.join(parts)
    posted = parse_date(safe_get(raw, 'updateTime') or safe_get(raw, 'publishTime')
                        or safe_get(raw, 'createTime'))
    url = JOB_PAGE_TEMPLATE.format(job_id=job_id)
    return Job(
        id=f'netease_{job_id}', company='netease', company_name='网易',
        title=title, category=normalize_category(str(category_raw) or title),
        category_raw=str(category_raw or ''), location=location,
        department=str(department), posted_date=posted, url=url,
        source='hr.163.com', description=description,
    )


def fetch() -> list[Job]:
    session = _seed_session()
    chosen: Optional[dict] = None
    last_err: Optional[Exception] = None
    for attempt in ATTEMPTS:
        try:
            with_retries(lambda: _try_endpoint(session, attempt, 1),
                         label=f'netease probe {attempt["url"]}', retries=2)
            chosen = attempt
            print(f'  [netease] using {attempt["url"]}', flush=True)
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f'  [netease] probe failed: {exc}', flush=True)
    if chosen is None:
        raise RuntimeError(f'all netease endpoints rejected our payload: {last_err}')

    jobs: list[Job] = []
    for page in range(1, MAX_PAGES + 1):
        page_data = with_retries(lambda: _try_endpoint(session, chosen, page),
                                 label=f'netease p{page}')
        records = _extract_list(page_data)
        page_jobs = [j for j in (_to_job(r) for r in records) if j is not None]
        jobs.extend(page_jobs)
        print(f'  [netease] page {page}: raw={len(records)} kept={len(page_jobs)} '
              f'cumulative={len(jobs)}', flush=True)
        if not records or len(records) < PAGE_SIZE:
            break
    return jobs


if __name__ == '__main__':
    out = fetch()
    print(f'netease fetched {len(out)} jobs')
