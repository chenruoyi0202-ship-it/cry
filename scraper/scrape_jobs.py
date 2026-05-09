#!/usr/bin/env python3
"""深圳大厂招聘数据聚合爬虫.

Fetches Shenzhen-based open jobs from Tencent / ByteDance / Meituan public
career APIs and merges them into a single JSON file consumed by jobs.html.

Per-company isolation: a failure in one source preserves the previous
snapshot for that source while still updating the others. The orchestrator
never produces an empty jobs.json if the previous run had data.

Usage:
    python scraper/scrape_jobs.py                 # all companies
    python scraper/scrape_jobs.py --company tencent
    python scraper/scrape_jobs.py --company all --dry-run   # don't write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
OUTPUT_PATH = os.path.join(DATA_DIR, 'jobs.json')

# Allow running from the repo root (`python scraper/scrape_jobs.py`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jobs_sources import (
    bytedance, byd, dji, jd, meituan, netease, oppo, tencent, vivo, xiaomi,
)  # noqa: E402
from jobs_sources.common import CATEGORIES, Job, dedupe_jobs  # noqa: E402

CST = timezone(timedelta(hours=8))


SOURCES: dict[str, dict] = {
    'tencent':   {'name': '腾讯',     'fetch': tencent.fetch},
    'bytedance': {'name': '字节跳动', 'fetch': bytedance.fetch},
    'meituan':   {'name': '美团',     'fetch': meituan.fetch},
    'dji':       {'name': '大疆',     'fetch': dji.fetch},
    'byd':       {'name': '比亚迪',   'fetch': byd.fetch},
    'jd':        {'name': '京东',     'fetch': jd.fetch},
    'netease':   {'name': '网易',     'fetch': netease.fetch},
    'xiaomi':    {'name': '小米',     'fetch': xiaomi.fetch},
    'oppo':      {'name': 'OPPO',     'fetch': oppo.fetch},
    'vivo':      {'name': 'vivo',     'fetch': vivo.fetch},
}


def load_existing() -> dict:
    if not os.path.exists(OUTPUT_PATH):
        return {'companies': {}, 'jobs': []}
    try:
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f'warn: could not load existing {OUTPUT_PATH}: {exc}',
              file=sys.stderr)
        return {'companies': {}, 'jobs': []}


def jobs_for_company(state: dict, company: str) -> list[dict]:
    return [j for j in state.get('jobs', []) if j.get('company') == company]


def run_one(company: str, fetch: Callable[[], list[Job]]) -> tuple[list[Job], dict]:
    started = int(time.time() * 1000)
    print(f'\n[{company}] start')
    try:
        jobs = fetch()
        if not jobs:
            raise RuntimeError('source returned 0 jobs')
        print(f'[{company}] ok: {len(jobs)} jobs')
        return jobs, {
            'count': len(jobs),
            'status': 'ok',
            'fetched_at': started,
            'error': None,
        }
    except Exception as exc:  # noqa: BLE001
        print(f'[{company}] FAILED: {exc}', file=sys.stderr)
        return [], {
            'count': 0,
            'status': 'error',
            'fetched_at': started,
            'error': str(exc)[:300],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--company', default='all',
                        choices=['all', *SOURCES.keys()])
    parser.add_argument('--dry-run', action='store_true',
                        help='do not write output file')
    args = parser.parse_args()

    targets = list(SOURCES.keys()) if args.company == 'all' else [args.company]

    existing = load_existing()
    previous_companies = existing.get('companies', {}) if isinstance(existing, dict) else {}

    merged_jobs: list[dict] = []
    company_states: dict[str, dict] = dict(previous_companies)

    # Carry forward all companies we are NOT scraping this run (so a partial
    # `--company tencent` invocation doesn't drop bytedance/meituan data).
    for slug in SOURCES:
        if slug not in targets:
            merged_jobs.extend(jobs_for_company(existing, slug))

    for slug in targets:
        meta = SOURCES[slug]
        new_jobs, state = run_one(slug, meta['fetch'])
        if state['status'] == 'ok':
            merged_jobs.extend(j.to_dict() for j in new_jobs)
            state['name'] = meta['name']
            company_states[slug] = state
        else:
            # Preserve previous snapshot for this company.
            kept = jobs_for_company(existing, slug)
            merged_jobs.extend(kept)
            prev = previous_companies.get(slug, {}) or {}
            company_states[slug] = {
                'name': meta['name'],
                'count': len(kept),
                'status': 'stale' if kept else 'error',
                'fetched_at': prev.get('fetched_at', 0),
                'error': state['error'],
            }
            print(f'[{slug}] kept {len(kept)} previous jobs')

    # Make sure every known company has a stub entry in `companies`.
    for slug, meta in SOURCES.items():
        if slug not in company_states:
            company_states[slug] = {
                'name': meta['name'],
                'count': 0,
                'status': 'unknown',
                'fetched_at': 0,
                'error': None,
            }
        else:
            company_states[slug].setdefault('name', meta['name'])

    merged_unique = dedupe_jobs([_dict_to_job(j) for j in merged_jobs])
    merged_dicts = [j.to_dict() for j in merged_unique]
    merged_dicts.sort(key=lambda j: (j.get('posted_date') or '', j.get('title') or ''),
                      reverse=True)

    now_ms = int(time.time() * 1000)
    output = {
        'last_updated': now_ms,
        'last_updated_iso': datetime.now(CST).strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        'companies': company_states,
        'categories': CATEGORIES,
        'jobs': merged_dicts,
    }

    summary = ', '.join(
        f'{slug}={state.get("count", 0)}({state.get("status")})'
        for slug, state in company_states.items()
    )
    print(f'\nsummary: {summary}; total {len(merged_dicts)} jobs')

    if args.dry_run:
        print('(dry run; not writing)')
        return 0

    # Hard guard: if we had data before and now have none, abort with a non-
    # zero exit so the workflow's commit step skips.
    prev_total = len(existing.get('jobs') or [])
    if prev_total > 0 and len(merged_dicts) == 0:
        print(f'ABORT: previous run had {prev_total} jobs, this run has 0',
              file=sys.stderr)
        return 2

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'wrote {OUTPUT_PATH}')
    return 0


def _dict_to_job(d: dict) -> Job:
    return Job(
        id=d.get('id', ''),
        company=d.get('company', ''),
        company_name=d.get('company_name', ''),
        title=d.get('title', ''),
        category=d.get('category', '其他'),
        category_raw=d.get('category_raw', ''),
        location=d.get('location', ''),
        department=d.get('department', ''),
        posted_date=d.get('posted_date'),
        url=d.get('url', ''),
        source=d.get('source', ''),
        description=d.get('description', ''),
    )


if __name__ == '__main__':
    sys.exit(main())
