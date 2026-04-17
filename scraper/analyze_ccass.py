#!/usr/bin/env python3
"""
CCASS 持股分析报告生成

读取 data/stock_XXXXX_ccass.json + data/ccass_history/ 中的历史数据
输出:
  data/stock_XXXXX_ccass_report.md    - 中文 markdown 报告
  data/stock_XXXXX_ccass_summary.json - 前端用的结构化摘要

报告包含四大板块:
  一、Top 20 持股及最近变化
  二、近期加仓榜
  三、近期减仓榜
  四、洞察分析(集中度、进出 Top 20、异常信号、整体判断)
"""

import glob
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from participant_names import to_chinese, display_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'ccass_history')


# ==================== helpers ====================

def load_history(stock_code):
    """返回按日期升序的快照列表。"""
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, f'{stock_code}-*.json')))
    snapshots = []
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                snapshots.append(json.load(fh))
        except Exception as e:
            print(f'[warn] 无法读取 {f}: {e}', file=sys.stderr)
    return snapshots


def index_by_key(participants):
    """参与者 ID → 记录"""
    return {(p.get('id') or p.get('name')): p for p in participants}


def diff_snapshots(prev, curr):
    """比较两个快照中每个参与者的持股变动。返回 {key: {...}} 列表。"""
    if not prev or prev is curr:
        return []
    prev_idx = index_by_key(prev.get('participants', []))
    curr_idx = index_by_key(curr.get('participants', []))
    changes = []
    for key, c in curr_idx.items():
        p = prev_idx.get(key)
        prev_shares = (p or {}).get('shares') or 0
        prev_pct = (p or {}).get('pct') or 0
        curr_shares = c.get('shares') or 0
        curr_pct = c.get('pct') or 0
        delta_shares = curr_shares - prev_shares
        delta_pct = round(curr_pct - prev_pct, 4)
        if delta_shares == 0 and delta_pct == 0 and p is not None:
            continue
        changes.append({
            'id': c.get('id'),
            'name': c.get('name'),
            'prev_shares': prev_shares,
            'curr_shares': curr_shares,
            'delta_shares': delta_shares,
            'prev_pct': prev_pct,
            'curr_pct': curr_pct,
            'delta_pct': delta_pct,
            'is_new': p is None,
        })
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
            'is_exit': True,
        })
    return changes


def concentration(participants):
    sorted_p = sorted(participants, key=lambda p: p.get('pct') or 0, reverse=True)

    def top_n(n):
        return round(sum(p.get('pct') or 0 for p in sorted_p[:n]), 2)

    hhi = round(sum((p.get('pct') or 0) ** 2 for p in sorted_p), 2)
    return {
        'top1_pct_of_issued': top_n(1),
        'top5_pct_of_issued': top_n(5),
        'top10_pct_of_issued': top_n(10),
        'top20_pct_of_issued': top_n(20),
        'hhi': hhi,
    }


def concentration_label(hhi):
    if hhi > 2500:
        return '高度集中'
    if hhi > 1500:
        return '中度集中'
    return '相对分散'


# ==================== formatters ====================

def fmt_shares(n):
    if not n:
        return '0' if n == 0 else '-'
    a = abs(n)
    if a >= 1e8:
        return f'{n/1e8:.2f} 亿'
    if a >= 1e4:
        return f'{n/1e4:.2f} 万'
    return f'{n:,}'


def fmt_signed_shares(n):
    if not n:
        return '0'
    return ('+' if n > 0 else '') + fmt_shares(n)


def fmt_pct(p):
    if p is None:
        return '-'
    return f'{p:.2f}%'


def fmt_signed_pct(p):
    if p is None or p == 0:
        return '0.00%'
    return ('+' if p > 0 else '') + f'{p:.2f}%'


def fmt_num(n):
    if n is None:
        return '-'
    return f'{n:,}'


def change_cell(delta_pct, delta_shares):
    """Top 20 表格里的变化列文本。"""
    if delta_pct is None or delta_pct == 0:
        return '—'
    sign = '📈' if delta_pct > 0 else '📉'
    return f'{sign} {fmt_signed_pct(delta_pct)} ({fmt_signed_shares(delta_shares)})'


# ==================== report sections ====================

def build_top20(latest, day_changes_idx, week_changes_idx):
    """Top 20 持股及最近变化表格行数据。"""
    top20 = sorted(latest.get('participants', []),
                   key=lambda p: p.get('pct') or 0, reverse=True)[:20]
    rows = []
    for i, p in enumerate(top20, 1):
        key = p.get('id') or p.get('name')
        dc = day_changes_idx.get(key) or {}
        wc = week_changes_idx.get(key) or {}
        rows.append({
            'rank': i,
            'id': p.get('id'),
            'name': p.get('name'),
            'cn_name': to_chinese(p.get('id'), p.get('name')),
            'shares': p.get('shares'),
            'pct': p.get('pct'),
            'dayDeltaPct': dc.get('delta_pct', 0),
            'dayDeltaShares': dc.get('delta_shares', 0),
            'weekDeltaPct': wc.get('delta_pct', 0),
            'weekDeltaShares': wc.get('delta_shares', 0),
        })
    return rows


def build_movers(changes, direction='up', limit=10):
    """direction='up' 取增仓前 N,'down' 取减仓前 N。"""
    if direction == 'up':
        sorted_c = sorted(changes, key=lambda c: c['delta_pct'], reverse=True)
        filtered = [c for c in sorted_c if c['delta_pct'] > 0][:limit]
    else:
        sorted_c = sorted(changes, key=lambda c: c['delta_pct'])
        filtered = [c for c in sorted_c if c['delta_pct'] < 0][:limit]
    out = []
    for c in filtered:
        out.append({
            'id': c.get('id'),
            'name': c.get('name'),
            'cn_name': to_chinese(c.get('id'), c.get('name')),
            'deltaPct': c['delta_pct'],
            'deltaShares': c['delta_shares'],
            'prevPct': c.get('prev_pct', 0),
            'currPct': c.get('curr_pct', 0),
            'isNew': c.get('is_new', False),
            'isExit': c.get('is_exit', False),
        })
    return out


def build_insights(snapshots, latest, prev_day, prev_week):
    """产出文字形式的洞察分析段落。"""
    insights = []
    conc_now = concentration(latest.get('participants', []))

    # 1) 集中度变化
    if prev_week and prev_week is not latest:
        conc_prev = concentration(prev_week.get('participants', []))
        d_top1 = round(conc_now['top1_pct_of_issued'] - conc_prev['top1_pct_of_issued'], 2)
        d_top10 = round(conc_now['top10_pct_of_issued'] - conc_prev['top10_pct_of_issued'], 2)
        d_hhi = round(conc_now['hhi'] - conc_prev['hhi'], 2)
        trend_word = '加剧' if d_hhi > 100 else ('缓解' if d_hhi < -100 else '基本稳定')
        insights.append(
            f'**集中度 · {concentration_label(conc_now["hhi"])}** — HHI {conc_now["hhi"]}({fmt_signed_pct(d_hhi).replace("%","")}',
        )
        insights[-1] += (
            f'),Top 10 占比 {conc_now["top10_pct_of_issued"]}%({fmt_signed_pct(d_top10)}),'
            f'第一大户占 {conc_now["top1_pct_of_issued"]}%({fmt_signed_pct(d_top1)})。'
            f'近 7 日集中度 **{trend_word}**。'
        )
    else:
        insights.append(
            f'**集中度 · {concentration_label(conc_now["hhi"])}** — HHI {conc_now["hhi"]},'
            f'Top 10 占比 {conc_now["top10_pct_of_issued"]}%,第一大户占 '
            f'{conc_now["top1_pct_of_issued"]}%。(暂无历史对比数据)'
        )

    # 2) 新进 Top 20 / 退出 Top 20
    if prev_week and prev_week is not latest:
        prev_top20_ids = set()
        for p in sorted(prev_week.get('participants', []),
                        key=lambda p: p.get('pct') or 0, reverse=True)[:20]:
            prev_top20_ids.add(p.get('id') or p.get('name'))
        curr_top20_list = sorted(latest.get('participants', []),
                                 key=lambda p: p.get('pct') or 0, reverse=True)[:20]
        curr_top20_ids = {(p.get('id') or p.get('name')) for p in curr_top20_list}

        new_in = [p for p in curr_top20_list
                  if (p.get('id') or p.get('name')) not in prev_top20_ids]
        exit_out_ids = prev_top20_ids - curr_top20_ids

        if new_in:
            names = '、'.join(
                f'**{to_chinese(p.get("id"), p.get("name"))}** ({fmt_pct(p.get("pct"))})'
                for p in new_in[:5]
            )
            insights.append(f'**新进 Top 20** — {names}')
        if exit_out_ids:
            prev_idx = index_by_key(prev_week.get('participants', []))
            names = '、'.join(
                f'**{to_chinese(k, prev_idx[k].get("name"))}**'
                for k in list(exit_out_ids)[:5]
            )
            insights.append(f'**退出 Top 20** — {names}')

    # 3) 异常信号(单日 ≥ 1% 或 7 日 ≥ 2%)
    alerts = []
    if prev_day and prev_day is not latest:
        for c in diff_snapshots(prev_day, latest):
            if abs(c['delta_pct']) >= 1.0:
                verb = '增仓' if c['delta_pct'] > 0 else '减仓'
                alerts.append(
                    f'**{to_chinese(c.get("id"), c.get("name"))}** 单日{verb} '
                    f'**{fmt_signed_pct(c["delta_pct"])}**({fmt_signed_shares(c["delta_shares"])} 股)'
                )
    if prev_week and prev_week is not latest:
        for c in diff_snapshots(prev_week, latest):
            if abs(c['delta_pct']) >= 2.0 and not any(
                to_chinese(c.get('id'), c.get('name')) in a for a in alerts
            ):
                verb = '累计增仓' if c['delta_pct'] > 0 else '累计减仓'
                alerts.append(
                    f'**{to_chinese(c.get("id"), c.get("name"))}** 近 7 日{verb} '
                    f'**{fmt_signed_pct(c["delta_pct"])}**'
                )
    if alerts:
        insights.append('**异常信号** — ' + ';'.join(alerts[:8]))

    # 4) 整体判断
    judgement = []
    top1 = conc_now['top1_pct_of_issued']
    if top1 > 50:
        judgement.append(f'第一大户持股 {top1}%,公众流通盘极薄,股价易被单家机构行为主导')
    elif top1 > 30:
        judgement.append(f'第一大户持股 {top1}%,筹码较为集中,需关注其动向')
    if conc_now['top10_pct_of_issued'] > 90:
        judgement.append('Top 10 吃掉九成以上筹码,散户实际可交易盘极少')
    ccass_pct = (latest.get('totalInCCASS') or {}).get('pct') or 0
    if ccass_pct < 50:
        judgement.append(
            f'CCASS 存管占比仅 {ccass_pct}%,大部分股份未进入中央结算(可能在大股东或信托手中)'
        )
    if judgement:
        insights.append('**整体判断** — ' + ';'.join(judgement))

    return insights


# ==================== main ====================

def build_report(stock_code):
    snapshots = load_history(stock_code)
    if not snapshots:
        raise RuntimeError(f'没有找到 {stock_code} 的 CCASS 历史数据')

    latest = snapshots[-1]
    prev_day = snapshots[-2] if len(snapshots) >= 2 else None
    prev_week = snapshots[-8] if len(snapshots) >= 8 else snapshots[0]

    day_changes = diff_snapshots(prev_day, latest)
    week_changes = diff_snapshots(prev_week, latest)
    day_changes_idx = {(c['id'] or c['name']): c for c in day_changes}
    week_changes_idx = {(c['id'] or c['name']): c for c in week_changes}

    top20 = build_top20(latest, day_changes_idx, week_changes_idx)
    movers_up = build_movers(week_changes, 'up', 10)
    movers_down = build_movers(week_changes, 'down', 10)
    insights = build_insights(snapshots, latest, prev_day, prev_week)
    conc = concentration(latest.get('participants', []))

    # ---------- Markdown ----------
    md = []
    md.append(f'# {stock_code} 创陞控股 · CCASS 持股分析报告')
    md.append('')
    md.append(
        f'**持股日期**: {latest.get("shareholdingDate", "-")}　　'
        f'**数据更新**: '
        + (datetime.fromtimestamp(latest.get("fetchedAt", 0) / 1000).strftime("%Y-%m-%d %H:%M")
           if latest.get("fetchedAt") else "-")
    )
    md.append('')

    # 概览
    md.append('## 概览')
    md.append('')
    md.append('| 指标 | 数值 |')
    md.append('|---|---|')
    md.append(f'| 已发行股份 | {fmt_num(latest.get("totalIssued"))} |')
    md.append(
        f'| CCASS 存管 | {fmt_num(latest["totalInCCASS"].get("shares"))} '
        f'({fmt_pct(latest["totalInCCASS"].get("pct"))}) |'
    )
    md.append(f'| 参与者数量 | {len(latest.get("participants", []))} |')
    md.append(f'| Top 1 持股占比 | {conc["top1_pct_of_issued"]}% |')
    md.append(f'| Top 10 持股占比 | {conc["top10_pct_of_issued"]}% |')
    md.append(f'| Top 20 持股占比 | {conc["top20_pct_of_issued"]}% |')
    md.append(f'| HHI 集中度 | {conc["hhi"]} ({concentration_label(conc["hhi"])}) |')
    md.append(f'| 历史快照数 | {len(snapshots)} 天 |')
    md.append('')

    # 一、Top 20
    md.append('## 一、Top 20 持股及最近变化')
    md.append('')
    if not prev_day:
        md.append('> 首日快照,暂无变化对比数据。后续每日追加。')
        md.append('')
    md.append('| # | 机构 | 持股 | 占比 | 日变化 | 7日变化 |')
    md.append('|---:|---|---:|---:|---:|---:|')
    for r in top20:
        md.append(
            f'| {r["rank"]} | {r["cn_name"]} | {fmt_shares(r["shares"])} | '
            f'{fmt_pct(r["pct"])} | {change_cell(r["dayDeltaPct"], r["dayDeltaShares"])} | '
            f'{change_cell(r["weekDeltaPct"], r["weekDeltaShares"])} |'
        )
    md.append('')

    # 二、加仓榜
    md.append('## 二、近期加仓榜 (最近 7 日)')
    md.append('')
    if movers_up:
        md.append('| 机构 | 持股变化 | 占比变化 | 当前占比 |')
        md.append('|---|---:|---:|---:|')
        for m in movers_up:
            tag = '🆕 ' if m['isNew'] else ''
            md.append(
                f'| {tag}{m["cn_name"]} | 📈 {fmt_signed_shares(m["deltaShares"])} | '
                f'{fmt_signed_pct(m["deltaPct"])} | {fmt_pct(m["currPct"])} |'
            )
    else:
        md.append('> 暂无加仓数据(需要至少 2 天的历史快照)。')
    md.append('')

    # 三、减仓榜
    md.append('## 三、近期减仓榜 (最近 7 日)')
    md.append('')
    if movers_down:
        md.append('| 机构 | 持股变化 | 占比变化 | 当前占比 |')
        md.append('|---|---:|---:|---:|')
        for m in movers_down:
            tag = '🚪 ' if m['isExit'] else ''
            md.append(
                f'| {tag}{m["cn_name"]} | 📉 {fmt_signed_shares(m["deltaShares"])} | '
                f'{fmt_signed_pct(m["deltaPct"])} | {fmt_pct(m["currPct"])} |'
            )
    else:
        md.append('> 暂无减仓数据(需要至少 2 天的历史快照)。')
    md.append('')

    # 四、洞察分析
    md.append('## 四、洞察分析')
    md.append('')
    if insights:
        for ins in insights:
            md.append(f'- {ins}')
    else:
        md.append('> 暂无可输出的洞察(数据量不足)。')
    md.append('')

    # 历史趋势
    if len(snapshots) >= 2:
        md.append('## 附:近期 CCASS 总持股走势')
        md.append('')
        md.append('| 日期 | CCASS 存管 | 占比 | 参与者 | Top1 | Top10 | HHI |')
        md.append('|---|---:|---:|---:|---:|---:|---:|')
        for s in snapshots[-15:]:
            c = concentration(s.get('participants', []))
            md.append(
                f'| {s.get("shareholdingDate", "-")} | '
                f'{fmt_shares(s["totalInCCASS"].get("shares"))} | '
                f'{fmt_pct(s["totalInCCASS"].get("pct"))} | '
                f'{len(s.get("participants", []))} | '
                f'{c["top1_pct_of_issued"]}% | {c["top10_pct_of_issued"]}% | '
                f'{c["hhi"]} |'
            )
        md.append('')

    md.append('---')
    md.append('')
    md.append(
        '> 数据来源:[港交所 CCASS](https://www3.hkexnews.hk/sdw/search/searchsdw.aspx)　　'
        f'报告生成:{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}　　'
        '本报告由自动化脚本生成,不构成投资建议'
    )

    # ---------- 前端摘要 JSON ----------
    summary = {
        'stockCode': stock_code,
        'shareholdingDate': latest.get('shareholdingDate'),
        'fetchedAt': latest.get('fetchedAt'),
        'totalIssued': latest.get('totalIssued'),
        'totalInCCASS': latest.get('totalInCCASS'),
        'participantCount': len(latest.get('participants', [])),
        'concentration': {**conc, 'label': concentration_label(conc['hhi'])},
        'top20': top20,
        'movers7d': {'up': movers_up, 'down': movers_down},
        'insights': insights,
        'historyDays': len(snapshots),
        'trend': [
            {
                'date': s.get('shareholdingDate'),
                'shares': (s.get('totalInCCASS') or {}).get('shares'),
                'pct': (s.get('totalInCCASS') or {}).get('pct'),
                'participants': len(s.get('participants', [])),
                'top1Pct': concentration(s.get('participants', []))['top1_pct_of_issued'],
                'top10Pct': concentration(s.get('participants', []))['top10_pct_of_issued'],
                'hhi': concentration(s.get('participants', []))['hhi'],
            }
            for s in snapshots[-30:]
        ],
    }
    return '\n'.join(md), summary


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
