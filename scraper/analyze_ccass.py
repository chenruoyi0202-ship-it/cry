#!/usr/bin/env python3
"""
CCASS 持股分析报告生成
读取 data/stock_XXXXX_ccass.json + data/ccass_history/ 中的历史数据
输出 Markdown 报告 data/stock_XXXXX_ccass_report.md
同时输出 data/stock_XXXXX_ccass_summary.json 供前端读取
"""

import glob
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'ccass_history')


def load_history(stock_code):
    """返回按日期升序的快照列表"""
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, f'{stock_code}-*.json')))
    snapshots = []
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                snapshots.append(json.load(fh))
        except Exception as e:
            print(f'[warn] 无法读取 {f}: {e}', file=sys.stderr)
    return snapshots


def build_participant_index(snapshot):
    """参与者 ID → 记录"""
    idx = {}
    for p in snapshot.get('participants', []):
        key = p.get('id') or p.get('name')
        if key:
            idx[key] = p
    return idx


def concentration(participants):
    """集中度: Top5/10/20 占 CCASS 的百分比；HHI 指数"""
    sorted_p = sorted(participants, key=lambda p: p.get('pct') or 0, reverse=True)
    total_pct = sum(p.get('pct') or 0 for p in sorted_p)

    def top_n(n):
        return round(sum(p.get('pct') or 0 for p in sorted_p[:n]), 2)

    hhi = round(sum((p.get('pct') or 0) ** 2 for p in sorted_p), 2)
    return {
        'top5_pct_of_issued': top_n(5),
        'top10_pct_of_issued': top_n(10),
        'top20_pct_of_issued': top_n(20),
        'hhi': hhi,
        'total_covered_pct': round(total_pct, 2),
    }


def compare(prev, curr, n_days=1):
    """对比前后两个快照，返回每个参与者的变动"""
    prev_idx = build_participant_index(prev)
    curr_idx = build_participant_index(curr)
    changes = []
    for key, c in curr_idx.items():
        p = prev_idx.get(key)
        prev_shares = p.get('shares') if p else 0
        prev_pct = p.get('pct') if p else 0
        curr_shares = c.get('shares') or 0
        curr_pct = c.get('pct') or 0
        delta_shares = (curr_shares or 0) - (prev_shares or 0)
        delta_pct = (curr_pct or 0) - (prev_pct or 0)
        if delta_shares == 0 and delta_pct == 0:
            continue
        changes.append({
            'id': c.get('id'),
            'name': c.get('name'),
            'prev_shares': prev_shares,
            'curr_shares': curr_shares,
            'delta_shares': delta_shares,
            'prev_pct': prev_pct,
            'curr_pct': curr_pct,
            'delta_pct': round(delta_pct, 4),
        })
    # 新增 / 消失
    for key, p in prev_idx.items():
        if key in curr_idx:
            continue
        changes.append({
            'id': p.get('id'),
            'name': p.get('name'),
            'prev_shares': p.get('shares') or 0,
            'curr_shares': 0,
            'delta_shares': -(p.get('shares') or 0),
            'prev_pct': p.get('pct') or 0,
            'curr_pct': 0,
            'delta_pct': round(-(p.get('pct') or 0), 4),
        })
    return changes


def fmt_num(n):
    if n is None:
        return '-'
    if isinstance(n, float):
        return f'{n:,.2f}' if abs(n) < 1000 else f'{n:,.0f}'
    return f'{n:,}'


def fmt_shares(n):
    if not n:
        return '-'
    n = abs(n)
    if n >= 1e8:
        return f'{n/1e8:.2f} 亿'
    if n >= 1e4:
        return f'{n/1e4:.2f} 万'
    return f'{n:,}'


def fmt_signed_shares(n):
    if not n:
        return '0'
    sign = '+' if n > 0 else '-'
    return f'{sign}{fmt_shares(n)}'


def fmt_pct(p):
    if p is None:
        return '-'
    return f'{p:.2f}%'


def fmt_signed_pct(p):
    if p is None or p == 0:
        return '0.00%'
    sign = '+' if p > 0 else ''
    return f'{sign}{p:.2f}%'


def build_report(stock_code):
    snapshots = load_history(stock_code)
    if not snapshots:
        raise RuntimeError(f'没有找到 {stock_code} 的 CCASS 历史数据')

    latest = snapshots[-1]
    prev_day = snapshots[-2] if len(snapshots) >= 2 else None
    prev_7d = snapshots[-8] if len(snapshots) >= 8 else snapshots[0]
    prev_30d = snapshots[-31] if len(snapshots) >= 31 else snapshots[0]

    conc = concentration(latest.get('participants', []))

    # Top 20 + 日变化
    top20 = sorted(latest.get('participants', []), key=lambda p: p.get('pct') or 0, reverse=True)[:20]
    day_changes_idx = {}
    if prev_day:
        for c in compare(prev_day, latest):
            day_changes_idx[c['id'] or c['name']] = c

    # 期间变化榜 (7 日 / 30 日)
    movers_7d = sorted(compare(prev_7d, latest), key=lambda c: c['delta_pct'], reverse=True) if prev_7d is not latest else []
    movers_30d = sorted(compare(prev_30d, latest), key=lambda c: c['delta_pct'], reverse=True) if prev_30d is not latest else []

    # 异常信号
    alerts = []
    for c in day_changes_idx.values():
        if abs(c['delta_pct']) >= 1.0:
            alerts.append(f"⚠️ **{c['name']}** 日内持股变动 **{fmt_signed_pct(c['delta_pct'])}**（{fmt_signed_shares(c['delta_shares'])} 股）")
    for c in movers_7d[:5]:
        if c['delta_pct'] >= 2.0:
            alerts.append(f"📈 **{c['name']}** 近 7 日加仓 **{fmt_signed_pct(c['delta_pct'])}**")
    for c in movers_7d[-5:]:
        if c['delta_pct'] <= -2.0:
            alerts.append(f"📉 **{c['name']}** 近 7 日减仓 **{fmt_signed_pct(c['delta_pct'])}**")

    # Markdown
    lines = []
    lines.append(f'# {stock_code} 创陞控股 · CCASS 持股分析报告')
    lines.append('')
    lines.append(f'**持股日期**: {latest.get("shareholdingDate", "-")}    '
                 f'**数据更新**: {datetime.fromtimestamp(latest.get("fetchedAt", 0)/1000).strftime("%Y-%m-%d %H:%M") if latest.get("fetchedAt") else "-"}')
    lines.append('')
    lines.append('## 一、总体概览')
    lines.append('')
    lines.append('| 指标 | 数值 |')
    lines.append('|---|---|')
    lines.append(f'| 已发行股份总数 | {fmt_num(latest.get("totalIssued"))} |')
    lines.append(f'| CCASS 存管股份 | {fmt_num(latest["totalInCCASS"].get("shares"))} ({fmt_pct(latest["totalInCCASS"].get("pct"))}) |')
    lines.append(f'| 参与者数量 | {len(latest.get("participants", []))} |')
    lines.append(f'| Top 5 持股占比 | {conc["top5_pct_of_issued"]}% |')
    lines.append(f'| Top 10 持股占比 | {conc["top10_pct_of_issued"]}% |')
    lines.append(f'| Top 20 持股占比 | {conc["top20_pct_of_issued"]}% |')
    lines.append(f'| HHI 集中度指数 | {conc["hhi"]} (>2500 为高度集中) |')
    lines.append('')

    if alerts:
        lines.append('## 二、异常信号')
        lines.append('')
        for a in alerts[:15]:
            lines.append(f'- {a}')
        lines.append('')

    lines.append('## 三、Top 20 参与者')
    lines.append('')
    lines.append('| # | 参与者 | 持股数 | 占比 | 日变化 |')
    lines.append('|---:|---|---:|---:|---:|')
    for i, p in enumerate(top20, 1):
        key = p.get('id') or p.get('name')
        change = day_changes_idx.get(key)
        delta_str = '-' if not change else f"{fmt_signed_pct(change['delta_pct'])} ({fmt_signed_shares(change['delta_shares'])})"
        lines.append(f"| {i} | {p.get('name') or '-'} | {fmt_shares(p.get('shares'))} | {fmt_pct(p.get('pct'))} | {delta_str} |")
    lines.append('')

    if movers_7d:
        lines.append('## 四、近 7 日加仓榜 (Top 10)')
        lines.append('')
        lines.append('| 参与者 | 持股变化 | 占比变化 |')
        lines.append('|---|---:|---:|')
        for c in movers_7d[:10]:
            if c['delta_pct'] <= 0:
                break
            lines.append(f"| {c['name']} | {fmt_signed_shares(c['delta_shares'])} | {fmt_signed_pct(c['delta_pct'])} |")
        lines.append('')

        lines.append('## 五、近 7 日减仓榜 (Top 10)')
        lines.append('')
        lines.append('| 参与者 | 持股变化 | 占比变化 |')
        lines.append('|---|---:|---:|')
        for c in list(reversed(movers_7d))[:10]:
            if c['delta_pct'] >= 0:
                break
            lines.append(f"| {c['name']} | {fmt_signed_shares(c['delta_shares'])} | {fmt_signed_pct(c['delta_pct'])} |")
        lines.append('')

    # 时序: 近 N 日 CCASS 总持股走势
    if len(snapshots) >= 2:
        lines.append('## 六、近期 CCASS 总持股走势')
        lines.append('')
        lines.append('| 日期 | CCASS 持股 | 占比 | 参与者数 |')
        lines.append('|---|---:|---:|---:|')
        for s in snapshots[-15:]:
            lines.append(f"| {s.get('shareholdingDate','-')} "
                         f"| {fmt_shares(s['totalInCCASS'].get('shares'))} "
                         f"| {fmt_pct(s['totalInCCASS'].get('pct'))} "
                         f"| {len(s.get('participants', []))} |")
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('> 数据来源: [港交所 CCASS](https://www3.hkexnews.hk/sdw/search/searchsdw.aspx)  ')
    lines.append(f'> 报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  ')
    lines.append('> 本报告由自动化脚本生成，仅供参考，不构成投资建议')

    return '\n'.join(lines), {
        'stockCode': stock_code,
        'shareholdingDate': latest.get('shareholdingDate'),
        'fetchedAt': latest.get('fetchedAt'),
        'totalIssued': latest.get('totalIssued'),
        'totalInCCASS': latest.get('totalInCCASS'),
        'participantCount': len(latest.get('participants', [])),
        'concentration': conc,
        'top20': [
            {
                'id': p.get('id'),
                'name': p.get('name'),
                'shares': p.get('shares'),
                'pct': p.get('pct'),
                'dayDeltaPct': (day_changes_idx.get(p.get('id') or p.get('name')) or {}).get('delta_pct', 0),
                'dayDeltaShares': (day_changes_idx.get(p.get('id') or p.get('name')) or {}).get('delta_shares', 0),
            }
            for p in top20
        ],
        'movers7d': {
            'top': [{'name': c['name'], 'deltaPct': c['delta_pct'], 'deltaShares': c['delta_shares']} for c in movers_7d[:10] if c['delta_pct'] > 0],
            'bottom': [{'name': c['name'], 'deltaPct': c['delta_pct'], 'deltaShares': c['delta_shares']} for c in reversed(movers_7d[-10:]) if c['delta_pct'] < 0],
        },
        'trend': [
            {
                'date': s.get('shareholdingDate'),
                'shares': s['totalInCCASS'].get('shares'),
                'pct': s['totalInCCASS'].get('pct'),
                'participants': len(s.get('participants', [])),
            }
            for s in snapshots[-30:]
        ],
        'alerts': alerts,
    }


def main():
    stock_code = sys.argv[1].zfill(5) if len(sys.argv) > 1 else '02680'
    md, summary = build_report(stock_code)

    md_path = os.path.join(DATA_DIR, f'stock_{stock_code}_ccass_report.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)

    sum_path = os.path.join(DATA_DIR, f'stock_{stock_code}_ccass_summary.json')
    with open(sum_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f'报告已生成: {md_path}')
    print(f'摘要已生成: {sum_path}')


if __name__ == '__main__':
    main()
