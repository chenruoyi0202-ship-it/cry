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


def parse_ccass_page(html):
    """解析 CCASS 搜索结果页面"""
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

    # 顶部标题信息 (shareholding date, stock code, total issued)
    for div in soup.select('.ccass-search-datebox, .ccass-search-result, .summary-header'):
        pass  # fallback, we also scan labels below

    # 通用扫描: 查找 "持股日期" / "Shareholding Date"
    text_blocks = soup.find_all(['div', 'span', 'td'])
    for el in text_blocks:
        t = el.get_text(' ', strip=True)
        m = re.search(r'(\d{2}/\d{2}/\d{4})', t)
        if m and ('持股日期' in t or 'Shareholding Date' in t):
            # 日期格式 DD/MM/YYYY -> YYYY-MM-DD
            d, mo, y = m.group(1).split('/')
            result['shareholdingDate'] = f'{y}-{mo}-{d}'
            break

    # 股票代码 & 名称
    for el in soup.select('#txt_stock_name, #txt_stock_code'):
        val = el.get_text(strip=True) or el.get('value', '')
        if 'name' in el.get('id', '').lower():
            result['stockName'] = val.strip(':：').strip()
        else:
            result['stockCode'] = val.strip(':：').strip()

    # 如果没找到，从页面文字中找
    if not result['stockCode']:
        body_text = soup.get_text(' ', strip=True)
        m = re.search(r'(?:股份代号|Stock Code)[:：\s]*(\d{4,5})', body_text)
        if m:
            result['stockCode'] = m.group(1).zfill(5)
        m = re.search(r'(?:股份名称|Stock Name)[:：\s]*([^\s,，]+)', body_text)
        if m:
            result['stockName'] = m.group(1)

    # 汇总区域: Total Issued Shares / Shareholding in CCASS
    for el in soup.select('.ccass-search-totalsharesbox, .summary-row, td'):
        t = el.get_text(' ', strip=True)
        m = re.search(r'(?:已发行股份总数|Total Number of Issued Shares)[^\d]*([\d,]+)', t)
        if m:
            result['totalIssued'] = normalize_number(m.group(1))
        m = re.search(r'(?:中央结算系统的存管股份总数|Total number of shares in CCASS)[^\d]*([\d,]+)', t)
        if m:
            result['totalInCCASS']['shares'] = normalize_number(m.group(1))
        m = re.search(r'(?:占已发行股份百分比|as percentage of the total number of Issued Shares)[^\d]*([\d.]+)\s*%', t)
        if m:
            result['totalInCCASS']['pct'] = normalize_number(m.group(1))

    # 参与者表格
    # 表头: Participant ID | Name of CCASS Participant | Address | Shareholding | % of Total...
    table = None
    for tbl in soup.find_all('table'):
        headers = [th.get_text(strip=True) for th in tbl.find_all('th')]
        joined = ' '.join(headers).lower()
        if 'participant' in joined or '参与者' in ''.join(headers) or 'shareholding' in joined or '持股量' in ''.join(headers):
            table = tbl
            break

    if table:
        rows = table.find_all('tr')
        for tr in rows:
            cells = tr.find_all(['td', 'th'])
            if len(cells) < 3:
                continue
            texts = [c.get_text(' ', strip=True) for c in cells]
            # 典型结构: [ID, Name, Address, Shareholding, %]  或  [Name, Shareholding, %]
            # 针对 HKEX 的实际 DOM: 每行内部有 .mobile-list-heading + .mobile-list-body
            # 这里提取数字列
            pid = None
            name = None
            address = None
            shares = None
            pct = None

            # 有 data-cell attribute 标注列含义
            for cell in cells:
                k = (cell.get('class') or [''])[0]
                v = cell.get_text(' ', strip=True)
                # 数字识别
                if re.match(r'^[\d,]+$', v.replace(' ', '')):
                    if shares is None:
                        shares = normalize_number(v)
                elif re.match(r'^[\d.]+\s*%$', v):
                    pct = normalize_number(v)
                elif re.match(r'^[A-Z]\d{5}$', v) or re.match(r'^\d{5,}$', v):
                    pid = v
                elif len(v) > 2 and not v.replace(',', '').isdigit():
                    if name is None:
                        name = v
                    elif address is None and len(v) > len(name or ''):
                        address = v

            if name and shares is not None:
                result['participants'].append({
                    'id': pid,
                    'name': name,
                    'address': address,
                    'shares': shares,
                    'pct': pct,
                })

    # 类别汇总 (Market Intermediaries / Investor Participants)
    for el in soup.find_all(text=re.compile(r'市场中介|Market Intermediaries|投资者户口|Investor Participants', re.I)):
        parent = el.parent
        if not parent:
            continue
        row_text = parent.get_text(' ', strip=True) if hasattr(parent, 'get_text') else str(el)
        m_shares = re.search(r'([\d,]{4,})', row_text)
        m_pct = re.search(r'([\d.]+)\s*%', row_text)
        m_count = re.search(r'(\d+)\s*(?:个|家|of)', row_text)
        target = None
        if 'Market Intermediaries' in row_text or '市场中介' in row_text:
            target = result['marketIntermediaries']
        elif 'Consenting' in row_text or '同意' in row_text:
            if 'Non' in row_text or '非' in row_text or '不' in row_text:
                target = result['nonConsentingInvestors']
            else:
                target = result['consentingInvestors']
        if target:
            if m_shares:
                target['shares'] = normalize_number(m_shares.group(1))
            if m_pct:
                target['pct'] = normalize_number(m_pct.group(1))
            if m_count:
                target['count'] = normalize_number(m_count.group(1))

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
