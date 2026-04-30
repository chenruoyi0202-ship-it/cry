"""Generate the daily 深圳大厂招聘 digest.

Compares current data/jobs.json against the persistent data/jobs_seen.json
catalog, identifies jobs first seen today, scores each one with the
RESUME_PROFILE (kept in sync with the inline profile in jobs.html), and
writes a Markdown digest sorted by match score for posting to GitHub
issue / WeChat.

Outputs:
  - data/jobs_seen.json (updated catalog)
  - data/jobs_digest_YYYY-MM-DD.md (today's digest)

Run after scrape_jobs.py in the daily workflow.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
JOBS_PATH = os.path.join(DATA_DIR, 'jobs.json')
SEEN_PATH = os.path.join(DATA_DIR, 'jobs_seen.json')

CST = timezone(timedelta(hours=8))

# Mirror of jobs.html RESUME_PROFILE. Edit both together.
PROFILE = {
    'themes': [
        {'id': 'platform', 'name': '平台/知识运营', 'weight': 1.00, 'threshold': 1, 'keywords': [
            '平台运营', '平台运营经理', '平台产品', '平台策略', '平台增长', '平台生态',
            '知识运营', '知识平台', '内容平台', '开发者平台', '社区平台',
            '创作者平台', '中台运营', '生态运营', '生态产品']},
        {'id': 'ops', 'name': '运营 (核心)', 'weight': 1.00, 'threshold': 3, 'keywords': [
            '内容运营', '用户运营', '活动运营', '社区运营', '创作者运营', '圈层运营',
            '增长运营', '运营经理', '运营专家', '内容生态运营', '社群运营',
            '社区运营经理', '产品运营', '运营策略', '运营负责人', '生态运营',
            '私域运营']},
        {'id': 'content', 'name': '内容/知识 (核心)', 'weight': 1.00, 'threshold': 2, 'keywords': [
            '内容', '知识', '知识平台', '知识库', '知识社区', '知识中台', '知识管理',
            '知识产品', 'wiki', '文档', '文档运营', '专题', '内容社区', '内容生态',
            '内容生产', '内容分发', '内容策略', '内容矩阵', 'IP 打造', 'OGC', 'PGC',
            'UGC', '编辑', '科普', '资料库']},
        {'id': 'community', 'name': '社区/创作者 (核心)', 'weight': 1.00, 'threshold': 2, 'keywords': [
            '社区', '社区运营', '社群', '社群运营', '创作者', '创作者运营', 'KOL',
            '圈子', '圈层', '互动', '论坛', '社交', '粉丝', '活跃度', '认知度',
            '社区氛围', '社区营销', '社群活跃', '社区生态']},
        {'id': 'devrel', 'name': '开发者生态', 'weight': 0.95, 'threshold': 1, 'keywords': [
            '开发者', '开发者大会', '开发者生态', '开发者关系', '开发者社区',
            '开发者运营', 'devrel', 'developer relations', '开源', '技术布道',
            '技术社区', '技术内容', '技术运营', '技术传播', 'tgdc', 'workshop',
            'hackathon', '黑客松', '程序员', '技术大会', 'meetup']},
        {'id': 'ai', 'name': 'AI / 大模型', 'weight': 0.75, 'threshold': 1, 'keywords': [
            'AI', '大模型', 'LLM', 'Claude', 'AGI', 'GPT', 'AIGC', 'AI Coding',
            '生成式', '智能化', 'AI 工具', '元宝']},
        {'id': 'pm', 'name': '产品 PM', 'weight': 0.70, 'threshold': 2, 'keywords': [
            '产品经理', '产品运营', '产品策略', '产品规划', '产品框架', '功能规划',
            '需求', '迭代', 'PRD', '商业化产品']},
        {'id': 'data', 'name': '数据驱动 / 增长', 'weight': 0.55, 'threshold': 2, 'keywords': [
            '数据分析', '数据驱动', '用户增长', '留存', 'KANO', '数据后台', '指标',
            'A/B', '分层运营', '用户画像']},
        {'id': 'game', 'name': '游戏行业 (背景)', 'weight': 0.20, 'threshold': 1, 'keywords': [
            '游戏开发', '游戏行业', '游戏知识', 'TGDC', '开发者大会']},
    ],
    'antiThemes': [
        {'id': 'gameops', 'name': '具体游戏运营', 'weight': 0.85, 'threshold': 1, 'keywords': [
            '玩法运营', '关卡运营', '赛事运营', '公会运营', '电竞运营', '电竞赛事',
            '游戏发行', '游戏推广', '主播运营', '玩家运营', '内购运营', '付费运营',
            'mmo', 'moba', 'fps', '手游运营', '端游运营', '游戏运营', '英雄联盟',
            '王者荣耀', '和平精英', '金铲铲', '洛克王国', 'nikke', '海岛奇兵',
            'pubg', 'supercell']},
        {'id': 'engineering', 'name': '纯研发岗', 'weight': 0.60, 'threshold': 2, 'keywords': [
            '后端工程师', '前端工程师', '算法工程师', '架构师', '高级研发', 'devops',
            'sre', '测试工程师', 'qa', '安全工程师', 'c++', 'java', 'golang',
            'rust', 'kafka', 'kubernetes', '编译器', '操作系统', '驱动开发',
            'ios 开发', 'android 开发', '客户端开发', '服务端开发']},
        {'id': 'art', 'name': '美术/设计岗', 'weight': 0.50, 'threshold': 1, 'keywords': [
            '美术', '原画', '建模', '动画师', 'pipeline ta', 'ui 设计师',
            'ux 设计师', '视觉设计师', '平面设计', '游戏美术', '场景美术',
            '角色美术', '特效美术']},
        {'id': 'hardware', 'name': '硬件岗', 'weight': 0.55, 'threshold': 1, 'keywords': [
            '硬件', '嵌入式', 'fpga', '芯片', '射频', '机械工程', '结构工程师',
            '电源工程师', '射频工程师']},
        {'id': 'sales', 'name': '销售/BD/客户', 'weight': 0.30, 'threshold': 1, 'keywords': [
            '销售', '商务拓展', '渠道经理', '客户经理', '大客户', '销售总监',
            '商务经理']},
    ],
}
MAX_POS = sum(t['weight'] for t in PROFILE['themes'])


def _haystack(job: dict) -> str:
    return ' '.join(filter(None, [
        job.get('title', ''), job.get('department', ''),
        job.get('category_raw', ''), job.get('description', ''),
    ])).lower()


def score(job: dict) -> tuple[float, list[dict]]:
    text = _haystack(job)
    matched = []
    pos = 0.0
    for theme in PROFILE['themes']:
        hits = sum(1 for k in theme['keywords'] if k.lower() in text)
        if hits == 0:
            continue
        norm = min(1.0, hits / theme['threshold'])
        contrib = theme['weight'] * norm
        pos += contrib
        matched.append({'name': theme['name'], 'hits': hits, 'contrib': contrib})
    neg = 0.0
    for anti in PROFILE['antiThemes']:
        hits = sum(1 for k in anti['keywords'] if k.lower() in text)
        if hits == 0:
            continue
        norm = min(1.0, hits / anti['threshold'])
        neg += anti['weight'] * norm
    raw = (pos - 1.0 * neg) / MAX_POS
    s = max(0.0, min(1.0, raw))
    matched.sort(key=lambda m: m['contrib'], reverse=True)
    return s, matched


def load_seen() -> dict:
    if not os.path.exists(SEEN_PATH):
        return {}
    try:
        return json.load(open(SEEN_PATH, encoding='utf-8'))
    except Exception:
        return {}


def update_seen(seen: dict, current_jobs: list[dict], today: str) -> set[str]:
    """Update the seen catalog and return the set of newly-added job ids."""
    new_today = set()
    for job in current_jobs:
        jid = job.get('id')
        if not jid:
            continue
        if jid not in seen:
            seen[jid] = {'first_seen': today}
            new_today.add(jid)
    return new_today


FALLBACK_WINDOW_DAYS = 7
FALLBACK_MAX_ITEMS = 15

# Categories the user is not in — drop from the digest entirely. The user
# wants 平台/运营/内容/社区 roles, not engineering or design positions.
EXCLUDED_CATEGORIES = {'技术', '设计'}


def _is_excluded(job: dict) -> bool:
    return (job.get('category') or '').strip() in EXCLUDED_CATEGORIES


def _job_age_days(job: dict, today: datetime) -> int:
    """How many days ago was this job posted? Returns 9999 on bad/missing date."""
    raw = job.get('posted_date') or ''
    try:
        d = datetime.strptime(raw, '%Y-%m-%d').replace(tzinfo=CST)
        return (today - d).days
    except Exception:
        return 9999


def build_digest_md(today: str, scored_new: list[tuple[dict, float, list]],
                    total_jobs: int,
                    scored_fallback: list[tuple[dict, float, list]] | None = None
                    ) -> str:
    lines = []
    lines.append(f'# 深圳大厂招聘 · 今日新增 ({today})')
    lines.append('')

    def render_section(title, group, max_items):
        if not group:
            return
        lines.append(f'## {title}')
        lines.append('')
        for idx, (job, s, themes) in enumerate(group[:max_items], 1):
            pct = round(s * 100)
            comp = job.get('company_name') or job.get('company', '')
            dept = job.get('department', '') or ''
            date = job.get('posted_date') or today
            url = job.get('url', '')
            theme_str = ' · '.join(f"{m['name']}" for m in themes[:3]) if themes else ''
            lines.append(f'**{idx}. [{job["title"]}]({url})** · `{pct}%`')
            lines.append(f'  {comp}' + (f' · {dept}' if dept else '') + f' · 🗓 {date}')
            if theme_str:
                lines.append(f'  🎯 {theme_str}')
            lines.append('')

    if scored_new:
        high = [t for t in scored_new if t[1] >= 0.40]
        mid = [t for t in scored_new if 0.20 <= t[1] < 0.40]
        low = [t for t in scored_new if t[1] < 0.20]
        lines.append(f'📊 共 **{len(scored_new)}** 个新增 · '
                     f'高匹配 **{len(high)}** · 中匹配 **{len(mid)}** · 低匹配 **{len(low)}**')
        lines.append(f'· 当前在招总数 {total_jobs}')
        lines.append('')
        render_section('🔥 高匹配 (≥40%)', high, 30)
        render_section('✨ 中匹配 (20-40%)', mid, 20)
        if low and len(high) + len(mid) < 5:
            render_section('一般匹配 (<20%)', low, 10)
    elif scored_fallback:
        # Today had no genuinely new postings — show the highest-matching
        # postings from the recent window so the digest still has signal.
        lines.append(
            f'📭 今日没有新增职位。下面是最近 {FALLBACK_WINDOW_DAYS} 天内 '
            f'按匹配度排序的 Top {FALLBACK_MAX_ITEMS}（当前在招总数 {total_jobs}）。'
        )
        lines.append('')
        render_section(f'⭐ 最近 {FALLBACK_WINDOW_DAYS} 天高匹配',
                       scored_fallback, FALLBACK_MAX_ITEMS)
    else:
        lines.append('今日没有新增职位，最近 7 天也暂无可推荐内容。')

    lines.append('---')
    lines.append('')
    lines.append('_每天 09:00 北京时间自动刷新 · '
                 '[打开网站](https://chenruoyi0202-ship-it.github.io/cry/jobs.html)_')
    return '\n'.join(lines)


def main() -> int:
    if not os.path.exists(JOBS_PATH):
        print(f'no jobs.json at {JOBS_PATH}', file=sys.stderr)
        return 1
    now = datetime.now(CST)
    today = now.strftime('%Y-%m-%d')
    data = json.load(open(JOBS_PATH, encoding='utf-8'))
    jobs = data.get('jobs') or []

    seen = load_seen()
    new_ids = update_seen(seen, jobs, today)
    with open(SEEN_PATH, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)
    print(f'seen catalog: {len(seen)} jobs ({len(new_ids)} new today)')

    new_jobs = [j for j in jobs if j.get('id') in new_ids and not _is_excluded(j)]
    excluded_new = sum(1 for j in jobs
                       if j.get('id') in new_ids and _is_excluded(j))
    if excluded_new:
        print(f'filtered out {excluded_new} new {EXCLUDED_CATEGORIES} jobs')
    scored = [(j, *score(j)) for j in new_jobs]
    scored.sort(key=lambda t: t[1], reverse=True)

    fallback = None
    if not scored:
        # Fallback: highest-scoring jobs from the last 7 days, excluding any
        # so-low-they're-noise. Keeps the daily email useful even on a quiet day.
        candidates = [j for j in jobs
                      if _job_age_days(j, now) <= FALLBACK_WINDOW_DAYS
                      and not _is_excluded(j)]
        scored_recent = [(j, *score(j)) for j in candidates]
        scored_recent = [t for t in scored_recent if t[1] >= 0.10]
        scored_recent.sort(key=lambda t: t[1], reverse=True)
        fallback = scored_recent[:FALLBACK_MAX_ITEMS]
        print(f'fallback: {len(fallback)} recent (≤{FALLBACK_WINDOW_DAYS}d) jobs')

    md = build_digest_md(today, scored, len(jobs), scored_fallback=fallback)
    out_path = os.path.join(DATA_DIR, f'jobs_digest_{today}.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'wrote {out_path} ({len(md)} chars)')
    with open(os.path.join(DATA_DIR, 'jobs_digest_latest.md'), 'w', encoding='utf-8') as f:
        f.write(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
