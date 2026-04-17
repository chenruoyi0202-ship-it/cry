#!/usr/bin/env python3
"""
CCASS 历史数据回填

港交所 CCASS 只保留过去 12 个月数据。本脚本从今天往前推 N 天,
为每个工作日抓一次,跳过已存在的快照。

用法:
  python scraper/backfill_ccass.py              # 默认回填 10 个工作日(约 2 周)
  python scraper/backfill_ccass.py 30           # 回填 30 天
  python scraper/backfill_ccass.py 10 02680     # 指定代码

行为:
  - 从最近一天向前推,遇到连续 5 天 "无数据"(推断早于上市日)就停止
  - 已有的历史文件跳过,不重抓
  - 每次请求之间延迟 2.5s
"""
import os
import sys
import time
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from scrape_ccass import fetch_ccass, save, HKT, HISTORY_DIR  # noqa: E402


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else 10
    stock = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else '02680'
    delay = float(os.environ.get('BACKFILL_DELAY', '2.5'))

    # 今天在 HKT
    today = datetime.now(HKT).date()
    # 如果今天 17:00 之前,今天的数据可能还没出,从昨天开始
    if datetime.now(HKT).hour < 17:
        today = today - timedelta(days=1)

    # 从最近一个工作日往前,跳过周末
    dates = []
    d = today
    while len(dates) < days * 2 and len(dates) < days:  # safety cap
        if d.weekday() < 5:  # Mon=0..Fri=4
            dates.append(d)
        d = d - timedelta(days=1)
        if len(dates) >= days:
            break

    os.makedirs(HISTORY_DIR, exist_ok=True)

    print(f'[Backfill] {stock} · 计划 {len(dates)} 个工作日 · 延迟 {delay}s', flush=True)

    scraped = skipped = failed = 0
    consec_nodata = 0

    for i, d in enumerate(dates, 1):
        date_str_slash = d.strftime('%Y/%m/%d')
        hist_path = os.path.join(HISTORY_DIR, f'{stock}-{d.strftime("%Y-%m-%d")}.json')
        if os.path.exists(hist_path):
            skipped += 1
            continue

        try:
            data = fetch_ccass(stock, date_str_slash, retries=2)
            save(data)
            scraped += 1
            consec_nodata = 0
            print(f'  [{i}/{len(dates)}] ✓ {date_str_slash} — '
                  f'{len(data["participants"])} 参与者', flush=True)
        except Exception as e:
            msg = str(e)
            failed += 1
            if '未解析' in msg or 'no data' in msg.lower():
                consec_nodata += 1
                print(f'  [{i}/{len(dates)}] ✗ {date_str_slash} — 无数据', flush=True)
                if consec_nodata >= 5:
                    print(f'  连续 {consec_nodata} 天无数据,推断早于上市日,停止回填', flush=True)
                    break
            else:
                consec_nodata = 0
                print(f'  [{i}/{len(dates)}] ✗ {date_str_slash} — {msg[:100]}', flush=True)

        time.sleep(delay)

    print(f'[Backfill] 完成 · 新抓 {scraped} · 跳过 {skipped} · 失败 {failed}', flush=True)


if __name__ == '__main__':
    main()
