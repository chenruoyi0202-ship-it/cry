#!/usr/bin/env python3
"""
港交所 CCASS 中央结算系统持股数据抓取
数据源: https://www3.hkexnews.hk/sdw/search/searchsdw.aspx

用法:
  python scrape_ccass.py                # 抓最近交易日，默认 02680
  python scrape_ccass.py 2026/04/15     # 指定日期
  python scrape_ccass.py 2026/04/15 00700  # 指定日期 + 股票代码

输出:
  data/stock_02680_ccass.json             - 最新快照
  data/ccass_history/02680-YYYY-MM-DD.json - 每日历史
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

HKT = timezone(timedelta(hours=8))
# HKEX CCASS search endpoint — ASP.NET WebForm (requires __VIEWSTATE on POST)
BASE_URL = 'https://www3.hkexnews.hk/sdw/search/searchsdw.aspx'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'ccass_history')


def normalize_number(s):
    if s is None:
        return None
    s = s.replace(',', '').replace('%', '').strip()
    if not s or s in ('-', 'N/A'):
        return None
    try:
        return float(s) if '.' in s else int(s)
    except ValueError:
        return None


def _cell_body(td):
    """从 HKEX 单元格中抽出值(忽略 mobile-list-heading 的列标签)。"""
    body = td.select_one('.mobile-list-body')
    if body:
        return body.get_text(' ', strip=True)
    return td.get_text(' ', strip=True)


def parse_ccass_page(html):
    """解析 CCASS 搜索结果页面 (HKEX searchsdw.aspx 结果页)"""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        'shareholdingDate': None,
        'stockCode': None,
        'stockName': None,
        'totalIssued': None,
        'totalInCCASS': {'shares': None, 'pct': None},
        'marketIntermediaries': {'shares': None, 'pct': None, 'count': None},
        'consentingInvestors': {'shares': None, 'pct': None, 'count': None},
        'nonConsentingInvestors': {'shares': None, 'pct': None, 'count': None},
        'participants': [],
    }

    # Shareholding Date — 标题栏 <b>Shareholding Date:</b> DD/MM/YYYY
    for b in soup.find_all('b'):
        t = b.get_text(strip=True)
        if 'Shareholding Date' in t or '持股日期' in t:
            after = (b.next_sibling or '').strip() if b.next_sibling else ''
            m = re.search(r'(\d{4})/(\d{2})/(\d{2})', after)
            if m:
                result['shareholdingDate'] = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
            else:
                m = re.search(r'(\d{2})/(\d{2})/(\d{4})', after)
                if m:
                    result['shareholdingDate'] = f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
            break

    # Stock Code / Name — 从 form 中或标题栏
    code_input = soup.select_one('input#txtStockCode')
    if code_input and code_input.get('value'):
        result['stockCode'] = code_input['value'].strip().zfill(5)
    name_input = soup.select_one('input#txtStockName')
    if name_input and name_input.get('value'):
        result['stockName'] = name_input['value'].strip()

    # Total Issued Shares — .ccass-search-remarks .summary-value
    issued = soup.select_one('.ccass-search-remarks .summary-value')
    if issued:
        result['totalIssued'] = normalize_number(issued.get_text(strip=True))

    # 汇总行: Market Intermediaries / Consenting / Non-consenting / Total
    for row in soup.select('.ccass-search-summary-table .ccass-search-datarow'):
        category_el = row.select_one('.summary-category')
        if not category_el:
            continue
        cat = category_el.get_text(' ', strip=True).lower()
        shares_el = row.select_one('.shareholding .value')
        count_el = row.select_one('.number-of-participants .value')
        pct_el = row.select_one('.percent-of-participants .value')
        shares = normalize_number(shares_el.get_text(strip=True)) if shares_el else None
        count = normalize_number(count_el.get_text(strip=True)) if count_el else None
        pct = normalize_number(pct_el.get_text(strip=True)) if pct_el else None

        if 'market intermediaries' in cat:
            target = result['marketIntermediaries']
        elif 'non-consenting' in cat or 'non consenting' in cat:
            target = result['nonConsentingInvestors']
        elif 'consenting' in cat:
            target = result['consentingInvestors']
        elif cat.startswith('total'):
            result['totalInCCASS']['shares'] = shares
            result['totalInCCASS']['pct'] = pct
            continue
        else:
            continue
        target['shares'] = shares
        target['count'] = count
        target['pct'] = pct

    # 参与者表: table.table-mobile-list tbody tr
    for tr in soup.select('table.table-mobile-list tbody tr'):
        pid_el = tr.select_one('td.col-participant-id')
        name_el = tr.select_one('td.col-participant-name')
        addr_el = tr.select_one('td.col-address')
        shares_el = tr.select_one('td.col-shareholding')
        pct_el = tr.select_one('td.col-shareholding-percent')
        if not (pid_el and name_el and shares_el):
            continue
        pid = _cell_body(pid_el)
        name = _cell_body(name_el)
        addr = _cell_body(addr_el) if addr_el else None
        shares = normalize_number(_cell_body(shares_el))
        pct = normalize_number(_cell_body(pct_el)) if pct_el else None
        if not pid or not name:
            continue
        result['participants'].append({
            'id': pid,
            'name': name,
            'address': addr,
            'shares': shares,
            'pct': pct,
        })

    return result


def get_viewstate_fields(session):
    r = session.get(BASE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    fields = {}
    # Extract every named form input (hidden + text) with its default value.
    form = soup.select_one('form#form1') or soup
    for el in form.select('input[name]'):
        n = el.get('name')
        t = (el.get('type') or 'text').lower()
        if t in ('submit', 'image', 'button'):
            continue
        if n not in fields:
            fields[n] = el.get('value', '') or ''
    # Ensure standard WebForm fields exist even if missing on page.
    for k in ('__EVENTTARGET', '__EVENTARGUMENT', '__VIEWSTATE',
              '__VIEWSTATEGENERATOR', '__EVENTVALIDATION'):
        fields.setdefault(k, '')
    return fields


def fetch_ccass(stock_code='02680', shareholding_date=None, retries=3):
    """抓取某个股票某日 CCASS 数据"""
    if not stock_code:
        stock_code = '02680'
    stock_code = stock_code.zfill(5)
    if not shareholding_date:  # None or empty string
        # 最近一个交易日 (周末回退到周五)
        now = datetime.now(HKT)
        if now.hour < 17:  # CCASS 通常 17:00 HKT 后才有当日数据
            now = now - timedelta(days=1)
        while now.weekday() >= 5:
            now = now - timedelta(days=1)
        shareholding_date = now.strftime('%Y/%m/%d')
    print(f'[CCASS] 请求: code={stock_code} date={shareholding_date}', flush=True)

    last_err = None
    for attempt in range(retries):
        try:
            with requests.Session() as s:
                s.headers.update(HEADERS)
                fields = get_viewstate_fields(s)
                # The "Search" button is an <a> calling __doPostBack('btnSearch','')
                fields['__EVENTTARGET'] = 'btnSearch'
                fields['__EVENTARGUMENT'] = ''
                fields['txtStockCode'] = stock_code
                fields['txtShareholdingDate'] = shareholding_date
                fields['today'] = datetime.now(HKT).strftime('%Y%m%d')
                fields['sortBy'] = 'shareholding'
                fields['sortDirection'] = 'desc'

                post_headers = dict(HEADERS)
                post_headers['Referer'] = BASE_URL
                post_headers['Origin'] = 'https://www3.hkexnews.hk'
                r = s.post(BASE_URL, data=fields, headers=post_headers, timeout=45)
                r.raise_for_status()
                print(f'  响应 {r.status_code}, {len(r.text)} 字节', flush=True)
                data = parse_ccass_page(r.text)
                data['stockCode'] = stock_code
                data['fetchedAt'] = int(time.time() * 1000)
                if not data.get('shareholdingDate'):
                    parts = shareholding_date.split('/')
                    if len(parts) == 3:
                        y, m, d = parts
                        data['shareholdingDate'] = f'{y}-{m}-{d}'
                print(f'  解析结果: 参与者={len(data["participants"])} '
                      f'日期={data.get("shareholdingDate")} '
                      f'CCASS={data["totalInCCASS"].get("shares")}',
                      flush=True)
                if not data['participants']:
                    # Check if HKEX suggests a fallback date (means our
                    # requested date has no data yet, e.g. late publish)
                    m = re.search(r"data-reset=['\"](\d{4}/\d{2}/\d{2})['\"]", r.text)
                    if m and m.group(1) != shareholding_date:
                        fallback_date = m.group(1)
                        print(f'  HKEX 建议回退到 {fallback_date},重试', flush=True)
                        shareholding_date = fallback_date
                        continue  # retry the outer for-loop with new date
                    # 失败时保留原始 HTML 供诊断
                    debug_dir = os.path.join(ROOT, 'data', 'ccass_history')
                    os.makedirs(debug_dir, exist_ok=True)
                    debug_path = os.path.join(debug_dir, f'_debug_{stock_code}_{int(time.time())}.html')
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(r.text)
                    print(f'  原始 HTML 已保存: {debug_path}', flush=True)
                    raise RuntimeError(f'未解析出参与者数据，HTML 已保存到 {debug_path}')
                return data
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            print(f'  第 {attempt+1} 次尝试失败: {e}，{wait}s 后重试', file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError(f'抓取失败: {last_err}')


def save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    code = data['stockCode']
    latest_path = os.path.join(DATA_DIR, f'stock_{code}_ccass.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    hist_path = os.path.join(HISTORY_DIR, f'{code}-{data["shareholdingDate"]}.json')
    with open(hist_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return latest_path, hist_path


def main():
    shareholding_date = sys.argv[1] if len(sys.argv) > 1 else None
    stock_code = sys.argv[2] if len(sys.argv) > 2 else '02680'

    print(f'[CCASS] 抓取 {stock_code} @ {shareholding_date or "最近交易日"}')
    data = fetch_ccass(stock_code, shareholding_date)
    latest, hist = save(data)

    print(f'  持股日期: {data["shareholdingDate"]}')
    print(f'  已发行: {data.get("totalIssued")}')
    print(f'  CCASS 持股: {data["totalInCCASS"].get("shares")} '
          f'({data["totalInCCASS"].get("pct")}%)')
    print(f'  参与者数: {len(data["participants"])}')
    print(f'  已保存: {latest}')
    print(f'         {hist}')
    return data


if __name__ == '__main__':
    main()

