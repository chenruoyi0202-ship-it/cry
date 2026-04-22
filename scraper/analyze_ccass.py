#!/usr/bin/env python3
"""
CCASS 持股分析报告生成

读取 data/stock_XXXXX_ccass.json + data/ccass_history/ 中的历史数据
输出:
  data/stock_XXXXX_ccass_report.md    - 中文 markdown 报告
  data/stock_XXXXX_ccass_summary.json - 前端用的结构化摘要

报告包含四大板块 (+ 可选的 AI 深度分析):
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
from participant_names import to_chinese, display_name, categorize, CATEGORY_LABEL

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


def aggregate_by_category(participants):
    """聚合各类机构的持股(数 / 股 / 占比)。"""
    agg = {k: {'count': 0, 'shares': 0, 'pct': 0.0}
           for k in CATEGORY_LABEL}
    for p in participants or []:
        cat = categorize(p.get('id'), p.get('name'))
        agg[cat]['count'] += 1
        agg[cat]['shares'] += p.get('shares') or 0
        agg[cat]['pct'] += p.get('pct') or 0
    for k in agg:
        agg[k]['pct'] = round(agg[k]['pct'], 2)
    return agg


def category_flow(prev_snapshot, curr_snapshot):
    """各类机构 7 日净流入(占比变化 + 股数变化)。"""
    if not prev_snapshot or prev_snapshot is curr_snapshot:
        return {}
    prev_agg = aggregate_by_category(prev_snapshot.get('participants', []))
    curr_agg = aggregate_by_category(curr_snapshot.get('participants', []))
    flow = {}
    for k in CATEGORY_LABEL:
        flow[k] = {
            'curr_pct': curr_agg[k]['pct'],
            'curr_shares': curr_agg[k]['shares'],
            'curr_count': curr_agg[k]['count'],
            'delta_pct': round(curr_agg[k]['pct'] - prev_agg[k]['pct'], 2),
            'delta_shares': curr_agg[k]['shares'] - prev_agg[k]['shares'],
        }
    return flow


def hhi_trend(snapshots, n=7):
    """近 N 个快照的 HHI / Top1 / Top10 走势,返回方向描述。"""
    if len(snapshots) < 3:
        return None
    series = snapshots[-n:] if len(snapshots) >= n else snapshots
    hhis = [concentration(s.get('participants', []))['hhi'] for s in series]
    top1s = [concentration(s.get('participants', []))['top1_pct_of_issued'] for s in series]
    if len(hhis) < 2:
        return None
    # 简单线性方向: 末值减首值
    hhi_change = round(hhis[-1] - hhis[0], 2)
    top1_change = round(top1s[-1] - top1s[0], 2)

    direction = '震荡' if abs(hhi_change) < 50 else ('上行' if hhi_change > 0 else '下行')
    return {
        'days': len(hhis),
        'hhi_first': hhis[0],
        'hhi_last': hhis[-1],
        'hhi_change': hhi_change,
        'top1_change': top1_change,
        'direction': direction,
    }


def build_insights(snapshots, latest, prev_day, prev_week):
    """产出多维度的中文洞察。每条以 '**标题** — 内容' 形式。"""
    insights = []
    participants = latest.get('participants', [])
    conc_now = concentration(participants)
    cat_now = aggregate_by_category(participants)
    cat_flow = category_flow(prev_week, latest) if prev_week and prev_week is not latest else {}
    trend = hhi_trend(snapshots)

    # ============ 1) 集中度 & 趋势 ============
    label = concentration_label(conc_now['hhi'])
    line1 = (
        f'**集中度 · {label}** — HHI {conc_now["hhi"]},'
        f'第一大户 {conc_now["top1_pct_of_issued"]}%、'
        f'Top 5 {conc_now["top5_pct_of_issued"]}%、'
        f'Top 10 {conc_now["top10_pct_of_issued"]}%。'
    )
    if trend:
        line1 += (
            f'近 {trend["days"]} 日 HHI 由 {trend["hhi_first"]} → {trend["hhi_last"]}'
            f'({fmt_signed_pct(trend["hhi_change"]).replace("%","")}),整体 **{trend["direction"]}**。'
        )
    elif prev_week and prev_week is not latest:
        conc_prev = concentration(prev_week.get('participants', []))
        d_hhi = round(conc_now['hhi'] - conc_prev['hhi'], 2)
        d_top1 = round(conc_now['top1_pct_of_issued'] - conc_prev['top1_pct_of_issued'], 2)
        line1 += f'近 7 日 HHI {fmt_signed_pct(d_hhi).replace("%","")}、Top 1 {fmt_signed_pct(d_top1)}。'
    insights.append(line1)

    # ============ 2) 筹码结构(按机构性质) ============
    rows = []
    order = ['custodian', 'retail', 'china', 'international', 'hk_local']
    for k in order:
        v = cat_now[k]
        if v['count'] == 0:
            continue
        flow = cat_flow.get(k, {})
        flow_str = ''
        if flow:
            d_pct = flow.get('delta_pct', 0)
            if d_pct != 0:
                flow_str = f'(7日 {fmt_signed_pct(d_pct)})'
        rows.append(f'{CATEGORY_LABEL[k]} **{v["pct"]}%** ({v["count"]}家){flow_str}')
    insights.append('**筹码结构** — ' + ';'.join(rows))

    # ============ 3) 散户 vs 机构方向 ============
    if cat_flow:
        retail_d = cat_flow.get('retail', {}).get('delta_pct', 0)
        custodian_d = cat_flow.get('custodian', {}).get('delta_pct', 0)
        china_d = cat_flow.get('china', {}).get('delta_pct', 0)
        # 大户 = 托管 + 中资 + 外资
        big_d = (
            cat_flow.get('custodian', {}).get('delta_pct', 0)
            + cat_flow.get('china', {}).get('delta_pct', 0)
            + cat_flow.get('international', {}).get('delta_pct', 0)
        )
        big_d = round(big_d, 2)
        verdict = None
        if retail_d > 0.1 and big_d < -0.1:
            verdict = '⚠️ **疑似派发** — 散户加仓而大户(托管/中资/外资)在减仓,常见于阶段性高位'
        elif retail_d < -0.1 and big_d > 0.1:
            verdict = '✅ **疑似吸纳** — 散户减仓而大户在加仓,常见于阶段性低位'
        elif retail_d > 0.1 and big_d > 0.1:
            verdict = '📈 **共识看多** — 散户和机构同步加仓'
        elif retail_d < -0.1 and big_d < -0.1:
            verdict = '📉 **共识看空** — 散户和机构同步减仓'
        else:
            verdict = '➖ **横盘整理** — 散户与大户均无明显方向,筹码相对稳定'
        insights.append(
            f'**资金性质** — 散户 {fmt_signed_pct(retail_d)}、大户合计 {fmt_signed_pct(big_d)};{verdict}'
        )

    # ============ 4) 大户(Top 3)行为 ============
    top_n = sorted(participants, key=lambda p: p.get('pct') or 0, reverse=True)[:3]
    if prev_week and prev_week is not latest:
        prev_idx = index_by_key(prev_week.get('participants', []))
        big_lines = []
        for p in top_n:
            key = p.get('id') or p.get('name')
            prev_p = prev_idx.get(key)
            if not prev_p:
                continue
            d_pct = round((p.get('pct') or 0) - (prev_p.get('pct') or 0), 4)
            d_shares = (p.get('shares') or 0) - (prev_p.get('shares') or 0)
            if d_pct == 0:
                act = '持股不变'
            elif d_pct > 0:
                act = f'加仓 {fmt_signed_pct(d_pct)} ({fmt_signed_shares(d_shares)})'
            else:
                act = f'减仓 {fmt_signed_pct(d_pct)} ({fmt_signed_shares(d_shares)})'
            big_lines.append(
                f'{to_chinese(p.get("id"), p.get("name"))}({p.get("pct")}%):{act}'
            )
        if big_lines:
            insights.append('**Top 3 大户动向** — ' + ';'.join(big_lines))

    # ============ 5) 流通盘估算 ============
    total_issued = latest.get('totalIssued') or 0
    ccass_shares = (latest.get('totalInCCASS') or {}).get('shares') or 0
    top1 = top_n[0] if top_n else None
    if total_issued and ccass_shares and top1:
        # 假设 top1(若为托管或大额单户)是大股东托管,真实可流通 ≈ CCASS - top1
        top1_shares = top1.get('shares') or 0
        free_float = ccass_shares - top1_shares
        free_float_pct = round(free_float / total_issued * 100, 2)
        top1_name = to_chinese(top1.get('id'), top1.get('name'))
        insights.append(
            f'**流通盘估算** — 假设 {top1_name}({top1.get("pct")}%) 为大股东/控制人托管,'
            f'真实可交易盘 ≈ {fmt_shares(free_float)} 股(约 **{free_float_pct}%**)。'
            f'注:仅为推断,实际控股结构以披露文件为准。'
        )

    # ============ 6) 新进 / 退出 Top 20 ============
    if prev_week and prev_week is not latest:
        prev_top20_ids = {(p.get('id') or p.get('name')) for p in
                          sorted(prev_week.get('participants', []),
                                 key=lambda p: p.get('pct') or 0, reverse=True)[:20]}
        curr_top20_list = sorted(participants, key=lambda p: p.get('pct') or 0, reverse=True)[:20]
        curr_top20_ids = {(p.get('id') or p.get('name')) for p in curr_top20_list}

        new_in = [p for p in curr_top20_list
                  if (p.get('id') or p.get('name')) not in prev_top20_ids]
        exit_out_ids = prev_top20_ids - curr_top20_ids

        movements = []
        if new_in:
            names = '、'.join(
                f'{to_chinese(p.get("id"), p.get("name"))}({fmt_pct(p.get("pct"))})'
                for p in new_in[:5]
            )
            movements.append(f'🆕 新进 {len(new_in)} 家:{names}')
        if exit_out_ids:
            prev_idx = index_by_key(prev_week.get('participants', []))
            names = '、'.join(
                to_chinese(k, prev_idx[k].get('name'))
                for k in list(exit_out_ids)[:5]
            )
            movements.append(f'🚪 退出 {len(exit_out_ids)} 家:{names}')
        if movements:
            insights.append('**Top 20 进出** — ' + ';'.join(movements))

    # ============ 7) 异常信号(单日 ≥1% 或 7 日 ≥2%) ============
    alerts = []
    seen_names = set()
    if prev_day and prev_day is not latest:
        for c in sorted(diff_snapshots(prev_day, latest),
                        key=lambda x: -abs(x['delta_pct'])):
            if abs(c['delta_pct']) >= 1.0:
                verb = '增仓' if c['delta_pct'] > 0 else '减仓'
                cn = to_chinese(c.get('id'), c.get('name'))
                alerts.append(
                    f'**{cn}** 单日{verb} {fmt_signed_pct(c["delta_pct"])}'
                    f'({fmt_signed_shares(c["delta_shares"])})'
                )
                seen_names.add(cn)
    if prev_week and prev_week is not latest:
        for c in sorted(diff_snapshots(prev_week, latest),
                        key=lambda x: -abs(x['delta_pct'])):
            cn = to_chinese(c.get('id'), c.get('name'))
            if abs(c['delta_pct']) >= 2.0 and cn not in seen_names:
                verb = '累计加仓' if c['delta_pct'] > 0 else '累计减仓'
                alerts.append(f'**{cn}** 7 日{verb} {fmt_signed_pct(c["delta_pct"])}')
                seen_names.add(cn)
    if alerts:
        insights.append('**异常信号** — ' + ';'.join(alerts[:6]))

    # ============ 8) 整体判断 & 风险提示 ============
    judgement = []
    top1_pct = conc_now['top1_pct_of_issued']
    if top1_pct > 70:
        judgement.append(
            f'第一大户独占 {top1_pct}%,典型"老千股 / 高度控盘"特征,'
            '股价对该机构行为高度敏感'
        )
    elif top1_pct > 50:
        judgement.append(f'第一大户持股 {top1_pct}%,筹码极度集中,公众流通盘很薄')
    elif top1_pct > 30:
        judgement.append(f'第一大户持股 {top1_pct}%,筹码较为集中')

    if conc_now['top10_pct_of_issued'] > 90:
        judgement.append('Top 10 吃掉九成以上,真实可交易盘十分稀缺,买卖盘容易出现大幅波动')

    ccass_pct = (latest.get('totalInCCASS') or {}).get('pct') or 0
    if ccass_pct < 50:
        judgement.append(
            f'CCASS 存管占比仅 {ccass_pct}%,大部分股份未在中央结算,可能在大股东或信托手中'
        )

    if cat_now.get('retail', {}).get('pct', 0) > 30:
        judgement.append(
            f'散户/互联网经纪持股达 {cat_now["retail"]["pct"]}%,'
            '散户参与度高,情绪驱动明显'
        )

    if judgement:
        insights.append('**整体判断与风险** — ' + ';'.join(judgement))

    # ============ 9) 散户经纪内部明细 ============
    if cat_flow:
        retail_flow = []
        for p in participants:
            if categorize(p.get('id'), p.get('name')) != 'retail':
                continue
            key = p.get('id') or p.get('name')
            wc = ((index_by_key(prev_week.get('participants', []) if prev_week else [])).get(key) or {})
            d_shares = (p.get('shares') or 0) - (wc.get('shares') or 0)
            d_pct = round((p.get('pct') or 0) - (wc.get('pct') or 0), 4)
            retail_flow.append({
                'name': to_chinese(p.get('id'), p.get('name')),
                'pct': p.get('pct') or 0,
                'd_pct': d_pct,
                'd_shares': d_shares,
            })
        retail_flow.sort(key=lambda x: x['pct'], reverse=True)
        top_retail = retail_flow[:5]
        if top_retail:
            lines = []
            for r in top_retail:
                if r['d_pct'] == 0:
                    flow = ''
                else:
                    flow = f' (7日 {fmt_signed_pct(r["d_pct"])})'
                lines.append(f'{r["name"]} {r["pct"]}%{flow}')
            insights.append(
                '**散户去哪买** — ' + ';'.join(lines)
                + '。散户筹码主要通过这些经纪商进出,加仓最多的渠道反映散户买入热情来源。'
            )

    # ============ 10) 中资券商内部明细 ============
    if cat_flow and cat_now['china']['count'] > 0:
        china_flow = []
        for p in participants:
            if categorize(p.get('id'), p.get('name')) != 'china':
                continue
            key = p.get('id') or p.get('name')
            wc = ((index_by_key(prev_week.get('participants', []) if prev_week else [])).get(key) or {})
            d_shares = (p.get('shares') or 0) - (wc.get('shares') or 0)
            d_pct = round((p.get('pct') or 0) - (wc.get('pct') or 0), 4)
            china_flow.append({
                'name': to_chinese(p.get('id'), p.get('name')),
                'pct': p.get('pct') or 0,
                'd_pct': d_pct,
                'd_shares': d_shares,
            })
        china_flow.sort(key=lambda x: x['pct'], reverse=True)
        top_china = china_flow[:5]
        if top_china:
            lines = []
            for r in top_china:
                if r['d_pct'] == 0:
                    flow = ''
                else:
                    flow = f' (7日 {fmt_signed_pct(r["d_pct"])})'
                lines.append(f'{r["name"]} {r["pct"]}%{flow}')
            insights.append(
                '**中资券商分布** — ' + ';'.join(lines)
                + '。中资券商持仓相对分散,缺乏单一主力,反映内地资金参与广度尚可但深度不足。'
            )

    # ============ 11) 加速度 / 减速度 ============
    if len(snapshots) >= 4:
        # 比较 最近 ~3 天 vs 之前 ~4 天 的总变动
        n = len(snapshots)
        mid = n - 4 if n >= 8 else n // 2
        recent = snapshots[mid:]
        earlier = snapshots[:mid + 1]  # +1 to overlap on boundary
        if len(earlier) >= 2 and len(recent) >= 2:
            recent_top1 = concentration(recent[-1].get('participants', []))['top1_pct_of_issued']
            recent_start_top1 = concentration(recent[0].get('participants', []))['top1_pct_of_issued']
            earlier_end_top1 = concentration(earlier[-1].get('participants', []))['top1_pct_of_issued']
            earlier_start_top1 = concentration(earlier[0].get('participants', []))['top1_pct_of_issued']
            recent_speed = round(recent_top1 - recent_start_top1, 3)
            earlier_speed = round(earlier_end_top1 - earlier_start_top1, 3)
            if abs(recent_speed) > abs(earlier_speed) * 1.5 and abs(recent_speed) > 0.05:
                trend = '加速加仓' if recent_speed > 0 else '加速减仓'
                insights.append(
                    f'**节奏变化** — 第一大户最近 {len(recent)} 天 Top 1 占比变化 '
                    f'{fmt_signed_pct(recent_speed)},较之前同窗口的 {fmt_signed_pct(earlier_speed)} **{trend}**,'
                    '动作有提速迹象,值得密切关注后续是否延续。'
                )
            elif abs(recent_speed) < abs(earlier_speed) * 0.5 and abs(earlier_speed) > 0.05:
                insights.append(
                    f'**节奏变化** — 第一大户最近 {len(recent)} 天动作明显放缓 '
                    f'(从 {fmt_signed_pct(earlier_speed)} → {fmt_signed_pct(recent_speed)}),'
                    '可能进入观望阶段。'
                )

    # ============ 12) CCASS 总持股变化 ============
    if prev_week and prev_week is not latest:
        prev_ccass = (prev_week.get('totalInCCASS') or {}).get('shares') or 0
        curr_ccass = (latest.get('totalInCCASS') or {}).get('shares') or 0
        d_ccass = curr_ccass - prev_ccass
        if abs(d_ccass) >= 100000:  # > 10 万股
            verb = '净流入' if d_ccass > 0 else '净流出'
            line = (
                f'**CCASS 总盘 7 日{verb} {fmt_shares(abs(d_ccass))} 股** — '
            )
            if d_ccass > 0:
                line += '场外股份转入中央结算,可能的解读:大股东将股份用于质押/借券/或准备减持。'
            else:
                line += '中央结算股份转出场外,可能是大股东收回或某机构客户提货。'
            insights.append(line)

    return insights


# ==================== Qwen 自然语言总结(可选) ====================

def call_qwen(prompt, api_key, model='qwen-max', max_tokens=1200):
    """调用百炼 Qwen 模型。失败返回 None,调用方应优雅降级。"""
    import urllib.request
    import urllib.error

    url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': '你是一位资深的港股 CCASS 持仓数据分析师,擅长用专业但易懂的中文,'
                                          '从筹码分布数据中读出资金动向、市场情绪和潜在风险。请直接给出分析,'
                                          '不要寒暄,不要复述数据,要有判断有解读。'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.3,
        'max_tokens': max_tokens,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['choices'][0]['message']['content'].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:200]
        print(f'[Qwen] HTTP {e.code}: {body}', file=sys.stderr)
        return None
    except Exception as e:
        print(f'[Qwen] 失败: {e}', file=sys.stderr)
        return None


def build_qwen_narrative(summary, api_key):
    """把结构化 summary 喂给 Qwen,让它产出 2-3 段自然语言深度分析。"""
    top20_brief = '\n'.join(
        f"  {p['rank']}. {p.get('cn_name') or p['name']} — 持股 {p['shares']:,} ({p['pct']}%), "
        f"日变 {p['dayDeltaPct']}%, 7日变 {p['weekDeltaPct']}%"
        for p in summary['top20'][:10]
    )
    movers_up = ', '.join(
        f"{m.get('cn_name') or m['name']}({m['deltaPct']}%)"
        for m in summary['movers7d']['up'][:5]
    ) or '无'
    movers_down = ', '.join(
        f"{m.get('cn_name') or m['name']}({m['deltaPct']}%)"
        for m in summary['movers7d']['down'][:5]
    ) or '无'

    prompt = f"""以下是港股 02680 创陞控股截至 {summary['shareholdingDate']} 的 CCASS 持仓数据,请基于此写一段 250-400 字的深度市场分析。

## 概览
- 已发行股份: {summary['totalIssued']:,}
- CCASS 存管: {summary['totalInCCASS']['shares']:,} ({summary['totalInCCASS']['pct']}%)
- 参与者数量: {summary['participantCount']} 家
- 集中度 HHI: {summary['concentration']['hhi']} ({summary['concentration']['label']})
- Top 1 占比: {summary['concentration']['top1_pct_of_issued']}%
- Top 10 占比: {summary['concentration']['top10_pct_of_issued']}%

## Top 10 参与者
{top20_brief}

## 近 7 日加仓榜
{movers_up}

## 近 7 日减仓榜
{movers_down}

## 已生成的规则版洞察
{chr(10).join('- ' + i for i in summary.get('insights', []))}

请输出:
1. 不要重复罗列上面的数据,而是从中提炼**资金行为模式**和**控盘特征**;
2. 解读这些数据**意味着什么**(可能的剧本:大股东锁仓/派发/吸纳;散户接盘还是离场;有无机构博弈);
3. 给出**未来 1-2 周值得关注的信号**;
4. 用中文,分 2-3 段,每段 80-150 字,直接以分析开头,不要"以下是分析:"之类的开场白。
"""
    return call_qwen(prompt, api_key)


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

    # 可选: 调用百炼 Qwen 生成自然语言深度分析
    api_key = os.environ.get('DASHSCOPE_API_KEY', '').strip()
    if api_key:
        print('[Qwen] 调用百炼 API 生成 AI 深度分析...', flush=True)
        narrative = build_qwen_narrative(summary, api_key)
        if narrative:
            md += '\n\n## 五、AI 深度分析(Qwen)\n\n' + narrative + '\n\n*由阿里云百炼 qwen-max 生成*\n'
            summary['aiNarrative'] = narrative
            print('[Qwen] AI 分析已附加到报告', flush=True)
        else:
            print('[Qwen] AI 调用失败,跳过', flush=True)
    else:
        print('[Qwen] 未配置 DASHSCOPE_API_KEY,跳过 AI 分析', flush=True)

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
