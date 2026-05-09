#!/usr/bin/env python3
"""
深圳宝安区房产数据爬虫
抓取幸福港湾尚品居及碧海片区房价、租金数据
数据源: 乐有家、安居客、贝壳、Q房网、creprice
"""

import asyncio
import json
import random
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'property.json')

# ---------- helpers ----------

async def safe_text(page, selector, default=''):
    """安全提取文本，失败返回默认值"""
    try:
        el = await page.query_selector(selector)
        if el:
            text = await el.inner_text()
            return text.strip()
    except Exception:
        pass
    return default

async def safe_texts(page, selector):
    """提取所有匹配元素的文本列表"""
    try:
        els = await page.query_selector_all(selector)
        return [await el.inner_text() for el in els]
    except Exception:
        return []

async def safe_attr(page, selector, attr, default=''):
    try:
        el = await page.query_selector(selector)
        if el:
            return await el.get_attribute(attr) or default
    except Exception:
        pass
    return default

def parse_price(text):
    """从文本中提取数字价格"""
    import re
    if not text:
        return None
    nums = re.findall(r'[\d,.]+', text.replace(',', ''))
    if nums:
        try:
            return float(nums[0])
        except ValueError:
            pass
    return None

async def delay(min_s=2, max_s=5):
    """随机延迟"""
    await asyncio.sleep(random.uniform(min_s, max_s))

# ---------- scrapers ----------

async def scrape_leyoujia_community(page, url, name):
    """乐有家 - 小区详情页"""
    print(f'[乐有家] 抓取 {name}: {url}')
    result = {'source': 'leyoujia', 'name': name, 'url': url}
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # 尝试提取均价
        price_text = await safe_text(page, '.price-num, .avg-price, .community-price, [class*="price"]')
        result['unit_price'] = parse_price(price_text)
        result['price_text'] = price_text

        # 尝试提取租金
        rent_text = await safe_text(page, '.rent-price, [class*="rent"], .zu-price')
        result['rent_price'] = parse_price(rent_text)
        result['rent_text'] = rent_text

        # 小区基本信息 - 获取所有文本块
        info_texts = await safe_texts(page, '.info-item, .detail-item, .base-info li, .community-info li')
        result['info'] = [t.strip() for t in info_texts if t.strip()]

        # 户型列表
        layout_texts = await safe_texts(page, '.layout-item, .huxing-item, .room-item')
        result['layouts'] = [t.strip() for t in layout_texts if t.strip()]

        # 获取页面完整可见文本用于后续解析
        body_text = await safe_text(page, 'body')
        # 只取前3000字符避免过大
        result['page_excerpt'] = body_text[:3000] if body_text else ''

        print(f'  均价: {result["unit_price"]}, 租金: {result["rent_price"]}')
    except Exception as e:
        result['error'] = str(e)
        print(f'  错误: {e}')
    return result


async def scrape_leyoujia_area(page, url, area_name):
    """乐有家 - 片区小区列表"""
    print(f'[乐有家] 抓取片区 {area_name}: {url}')
    result = {'source': 'leyoujia', 'area': area_name, 'url': url, 'communities': []}
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # 提取小区列表
        items = await page.query_selector_all('.community-item, .xq-item, .list-item, [class*="community"]')
        for item in items[:20]:  # 最多20个
            name = ''
            price = None
            try:
                name_el = await item.query_selector('.name, .title, a')
                if name_el:
                    name = (await name_el.inner_text()).strip()
                price_el = await item.query_selector('.price, [class*="price"]')
                if price_el:
                    price = parse_price(await price_el.inner_text())
            except Exception:
                pass
            if name:
                result['communities'].append({'name': name, 'price': price})

        # 页面摘要
        body_text = await safe_text(page, 'body')
        result['page_excerpt'] = body_text[:3000] if body_text else ''

        print(f'  找到 {len(result["communities"])} 个小区')
    except Exception as e:
        result['error'] = str(e)
        print(f'  错误: {e}')
    return result


async def scrape_anjuke_trend(page, url):
    """安居客 - 碧海片区价格趋势"""
    print(f'[安居客] 抓取碧海趋势: {url}')
    result = {'source': 'anjuke', 'url': url}
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        # 均价
        price_text = await safe_text(page, '.price-value, .avg-price, .trend-price, [class*="price"]')
        result['avg_price'] = parse_price(price_text)
        result['price_text'] = price_text

        # 趋势数据 - 尝试从页面JS数据中提取
        trend_data = await page.evaluate('''() => {
            // 尝试从全局变量中获取趋势数据
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const t = s.textContent;
                if (t && (t.includes('trend') || t.includes('chartData') || t.includes('priceData'))) {
                    // 尝试提取JSON数据
                    const match = t.match(/(?:trend|chart|price)[Dd]ata\s*[:=]\s*(\{[^}]+\}|\[[^\]]+\])/);
                    if (match) return match[1];
                }
            }
            return null;
        }''')
        if trend_data:
            try:
                result['trend_raw'] = json.loads(trend_data)
            except Exception:
                result['trend_raw_str'] = trend_data

        # 页面摘要
        body_text = await safe_text(page, 'body')
        result['page_excerpt'] = body_text[:3000] if body_text else ''

        print(f'  均价: {result.get("avg_price")}')
    except Exception as e:
        result['error'] = str(e)
        print(f'  错误: {e}')
    return result


async def scrape_ke_search(page, keyword):
    """贝壳找房 - 搜索小区"""
    url = f'https://sz.ke.com/xiaoqu/rs{keyword}/'
    print(f'[贝壳] 搜索: {keyword}')
    result = {'source': 'ke', 'keyword': keyword, 'url': url, 'communities': []}
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('.listContent li, .xiaoquListItem, [class*="xiaoqu"]')
        for item in items[:10]:
            name = ''
            price = None
            try:
                name_el = await item.query_selector('.title a, .name, .maidian-detail')
                if name_el:
                    name = (await name_el.inner_text()).strip()
                price_el = await item.query_selector('.totalPrice, .xiaoquListItemPrice .totalPrice span, [class*="price"]')
                if price_el:
                    price = parse_price(await price_el.inner_text())
            except Exception:
                pass
            if name:
                result['communities'].append({'name': name, 'price': price})

        # 也搜索租金
        rent_url = f'https://sz.ke.com/zufang/rs{keyword}/'
        await delay(2, 4)
        await page.goto(rent_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        rent_items = await page.query_selector_all('.content__list--item, [class*="rent-item"]')
        rents = []
        for item in rent_items[:10]:
            try:
                price_el = await item.query_selector('.content__list--item-price em, .price, [class*="price"] em')
                if price_el:
                    p = parse_price(await price_el.inner_text())
                    if p:
                        rents.append(p)
            except Exception:
                pass
        if rents:
            result['avg_rent'] = sum(rents) / len(rents)
            result['rent_samples'] = rents

        # 页面摘要
        body_text = await safe_text(page, 'body')
        result['page_excerpt'] = body_text[:2000] if body_text else ''

        print(f'  找到 {len(result["communities"])} 个小区, 租金样本 {len(rents)} 条')
    except Exception as e:
        result['error'] = str(e)
        print(f'  错误: {e}')
    return result


async def scrape_qfang_search(page, keyword):
    """Q房网 - 搜索小区"""
    url = f'https://shenzhen.qfang.com/garden/list?keyword={keyword}'
    print(f'[Q房网] 搜索: {keyword}')
    result = {'source': 'qfang', 'keyword': keyword, 'url': url, 'communities': []}
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        items = await page.query_selector_all('.garden-lst li, .list-item, [class*="garden"]')
        for item in items[:10]:
            name = ''
            price = None
            try:
                name_el = await item.query_selector('.garden-name, .name a, .title')
                if name_el:
                    name = (await name_el.inner_text()).strip()
                price_el = await item.query_selector('.price, .avg-price, [class*="price"]')
                if price_el:
                    price = parse_price(await price_el.inner_text())
            except Exception:
                pass
            if name:
                result['communities'].append({'name': name, 'price': price})

        body_text = await safe_text(page, 'body')
        result['page_excerpt'] = body_text[:2000] if body_text else ''

        print(f'  找到 {len(result["communities"])} 个小区')
    except Exception as e:
        result['error'] = str(e)
        print(f'  错误: {e}')
    return result


async def scrape_creprice(page, url, name):
    """全国房价行情 - 小区详情"""
    print(f'[房价行情] 抓取 {name}: {url}')
    result = {'source': 'creprice', 'name': name, 'url': url}
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        price_text = await safe_text(page, '.price, .avg-price, [class*="price"]')
        result['unit_price'] = parse_price(price_text)
        result['price_text'] = price_text

        body_text = await safe_text(page, 'body')
        result['page_excerpt'] = body_text[:3000] if body_text else ''

        print(f'  均价: {result.get("unit_price")}')
    except Exception as e:
        result['error'] = str(e)
        print(f'  错误: {e}')
    return result


# ---------- data consolidation ----------

def consolidate_data(raw_results):
    """将多源原始数据整合为统一格式"""
    data = {
        'scrape_time': datetime.now().isoformat(),
        'communities': [],
        'bihai_overview': {
            'avg_price': None,
            'communities_count': 0,
            'top_communities': []
        },
        'raw_sources': raw_results  # 保留原始数据供调试
    }

    # 收集幸福港湾尚品居的多源价格
    shangpinju_prices = {}
    shangpinju_rents = {}
    shangpinju_info = []
    shangpinju_layouts = []

    for r in raw_results:
        src = r.get('source', '')
        if r.get('name') and '幸福' in r.get('name', '') or '尚品' in r.get('name', ''):
            if r.get('unit_price'):
                shangpinju_prices[src] = r['unit_price']
            if r.get('rent_price'):
                shangpinju_rents[src] = r['rent_price']
            if r.get('info'):
                shangpinju_info.extend(r['info'])
            if r.get('layouts'):
                shangpinju_layouts.extend(r['layouts'])

        # 从搜索结果中提取
        for c in r.get('communities', []):
            cname = c.get('name', '')
            if '幸福' in cname or '尚品' in cname:
                if c.get('price'):
                    shangpinju_prices[src] = c['price']

        # 收集租金
        if r.get('avg_rent') and ('幸福' in r.get('keyword', '') or '尚品' in r.get('keyword', '')):
            shangpinju_rents[src] = r['avg_rent']

    # 构建尚品居数据
    all_prices = list(shangpinju_prices.values())
    all_rents = list(shangpinju_rents.values())
    avg_price = sum(all_prices) / len(all_prices) if all_prices else None
    avg_rent = sum(all_rents) / len(all_rents) if all_rents else None

    shangpinju = {
        'name': '幸福港湾尚品居',
        'area': '碧海片区',
        'district': '宝安区',
        'address': '碧海西乡大道308号',
        'prices': {
            'avg_unit_price': round(avg_price) if avg_price else None,
            'price_range': [min(all_prices), max(all_prices)] if len(all_prices) >= 2 else None,
            'source_prices': {k: round(v) for k, v in shangpinju_prices.items()}
        },
        'rental': {
            'avg_rent': round(avg_rent) if avg_rent else None,
            'source_rents': {k: round(v) for k, v in shangpinju_rents.items()}
        },
        'rent_yield': round(avg_rent * 12 / (avg_price * 89) * 100, 2) if avg_price and avg_rent else None,
        'info': shangpinju_info[:20],
        'layouts': shangpinju_layouts[:10]
    }
    data['communities'].append(shangpinju)

    # 碧海片区数据
    bihai_communities = []
    for r in raw_results:
        if r.get('area') == '碧海片区' or '碧海' in r.get('url', ''):
            for c in r.get('communities', []):
                if c.get('name') and c.get('price'):
                    bihai_communities.append(c)

        # 安居客趋势
        if r.get('source') == 'anjuke' and r.get('avg_price'):
            data['bihai_overview']['avg_price'] = round(r['avg_price'])
            if r.get('trend_raw'):
                data['bihai_overview']['trend'] = r['trend_raw']

    # 去重并排序
    seen = set()
    unique_communities = []
    for c in bihai_communities:
        if c['name'] not in seen:
            seen.add(c['name'])
            unique_communities.append(c)
    unique_communities.sort(key=lambda x: x.get('price', 0) or 0, reverse=True)

    data['bihai_overview']['communities_count'] = len(unique_communities)
    data['bihai_overview']['top_communities'] = unique_communities[:15]
    if unique_communities:
        prices = [c['price'] for c in unique_communities if c.get('price')]
        if prices:
            data['bihai_overview']['price_range'] = [min(prices), max(prices)]

    return data


# ---------- main ----------

async def main():
    print('=' * 60)
    print('深圳宝安区房产数据爬虫')
    print(f'开始时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)

    raw_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            viewport={'width': 390, 'height': 844},
            locale='zh-CN'
        )
        page = await context.new_page()

        # 1. 乐有家 - 幸福港湾尚品居
        r = await scrape_leyoujia_community(page, 'https://shenzhen.leyoujia.com/ysl/70886.html', '幸福港湾尚品居')
        raw_results.append(r)
        await delay()

        # 2. 乐有家 - 碧海片区小区列表
        r = await scrape_leyoujia_area(page, 'https://shenzhen.leyoujia.com/xq/detail/810.html', '碧海片区')
        raw_results.append(r)
        await delay()

        # 3. 安居客 - 碧海趋势
        r = await scrape_anjuke_trend(page, 'https://m.anjuke.com/sz/trendency/baoan-q-bhwsz/')
        raw_results.append(r)
        await delay()

        # 4. 贝壳 - 搜索尚品居
        r = await scrape_ke_search(page, '幸福港湾尚品居')
        raw_results.append(r)
        await delay()

        # 5. 贝壳 - 搜索碧海片区
        r = await scrape_ke_search(page, '碧海')
        raw_results.append(r)
        await delay()

        # 6. Q房网 - 搜索
        r = await scrape_qfang_search(page, '幸福港湾')
        raw_results.append(r)
        await delay()

        # 7. 全国房价行情
        r = await scrape_creprice(page, 'https://m.creprice.cn/community/0046012606.html?city=sz', '幸福港湾尚品居')
        raw_results.append(r)

        await browser.close()

    # 数据整合
    print('\n' + '=' * 60)
    print('数据整合中...')
    data = consolidate_data(raw_results)

    # 保存
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'数据已保存到: {OUTPUT_PATH}')
    print(f'抓取来源: {len(raw_results)} 个')

    # 摘要
    for comm in data.get('communities', []):
        print(f'\n【{comm["name"]}】')
        prices = comm.get('prices', {})
        if prices.get('avg_unit_price'):
            print(f'  均价: {prices["avg_unit_price"]} 元/㎡')
            print(f'  来源: {prices.get("source_prices", {})}')
        rental = comm.get('rental', {})
        if rental.get('avg_rent'):
            print(f'  租金: {rental["avg_rent"]} 元/月')
        if comm.get('rent_yield'):
            print(f'  租售比: {comm["rent_yield"]}%')

    overview = data.get('bihai_overview', {})
    if overview.get('avg_price'):
        print(f'\n【碧海片区总览】')
        print(f'  均价: {overview["avg_price"]} 元/㎡')
        print(f'  小区数: {overview["communities_count"]}')

    print('\n完成!')
    return data


if __name__ == '__main__':
    asyncio.run(main())
