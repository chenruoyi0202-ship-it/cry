/**
 * 止盈计算器 - 核心逻辑自动化测试
 *
 * 测试范围：
 * 1. formatMoney - 金额格式化
 * 2. 计算引擎 - 盈亏、收益率、仓位
 * 3. 记录管理 - 增删移动
 * 4. 方案存储 - localStorage 读写
 * 5. 加密/解密 - AES-GCM 对称加密
 */

// --- Extract pure functions from index.html for testing ---

// formatMoney: extracted verbatim
function formatMoney(n) {
  if (Math.abs(n) >= 10000) {
    return (n / 10000).toFixed(2) + '万';
  }
  return n.toFixed(2);
}

// Core calculation logic: extracted and made testable
function calcProfit({ costPrice, totalShares, records, currentRtPrice = null }) {
  if (costPrice <= 0 || totalShares <= 0) return null;

  const totalCost = costPrice * totalShares;
  let soldShares = 0, soldRevenue = 0;
  let planShares = 0, planRevenue = 0;

  records.forEach(r => {
    if (r.type === 'done') {
      soldShares += r.shares;
      soldRevenue += r.price * r.shares;
    } else {
      planShares += r.shares;
      planRevenue += r.price * r.shares;
    }
  });

  const remainShares = totalShares - soldShares - planShares;
  const totalRevenue = soldRevenue + planRevenue;
  const totalProfit = totalRevenue - (soldShares + planShares) * costPrice;

  let remainValue = 0, remainProfit = 0;
  if (remainShares > 0 && currentRtPrice) {
    remainValue = remainShares * currentRtPrice;
    remainProfit = (currentRtPrice - costPrice) * remainShares;
  }

  const grandProfit = totalProfit + remainProfit;
  const grandRevenue = totalRevenue + remainValue;
  const profitRate = (grandProfit / totalCost) * 100;

  const allSellShares = soldShares + planShares;
  const avgSellPrice = allSellShares > 0 ? (soldRevenue + planRevenue) / allSellShares : 0;

  return {
    totalCost,
    soldShares, soldRevenue,
    planShares, planRevenue,
    remainShares, remainValue, remainProfit,
    grandProfit, grandRevenue, profitRate,
    avgSellPrice, allSellShares,
  };
}

// Record management: extracted
function moveRecord(records, from, to) {
  if (from === to || from < 0 || to < 0) return records;
  if (from >= records.length || to >= records.length) return records;
  const arr = [...records];
  const item = arr.splice(from, 1)[0];
  arr.splice(to, 0, item);
  return arr;
}

// ==================== TESTS ====================

describe('formatMoney', () => {
  test('小数金额保留2位小数', () => {
    expect(formatMoney(123.456)).toBe('123.46');
  });

  test('整数金额加.00', () => {
    expect(formatMoney(100)).toBe('100.00');
  });

  test('万元转换 (>=10000)', () => {
    expect(formatMoney(12345)).toBe('1.23万');
    expect(formatMoney(10000)).toBe('1.00万');
    expect(formatMoney(99999)).toBe('10.00万');
    expect(formatMoney(123456)).toBe('12.35万');
  });

  test('刚好不到万元', () => {
    expect(formatMoney(9999.99)).toBe('9999.99');
  });

  test('负数金额', () => {
    expect(formatMoney(-500)).toBe('-500.00');
    expect(formatMoney(-15000)).toBe('-1.50万');
  });

  test('零', () => {
    expect(formatMoney(0)).toBe('0.00');
  });

  test('非常大的金额', () => {
    expect(formatMoney(1000000)).toBe('100.00万');
  });
});

describe('calcProfit - 盈亏计算引擎', () => {
  test('无减仓记录，无实时价 → 全零', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [],
    });
    expect(result.totalCost).toBe(10000);
    expect(result.soldShares).toBe(0);
    expect(result.grandProfit).toBe(0);
    expect(result.remainShares).toBe(1000);
    expect(result.profitRate).toBe(0);
  });

  test('无效输入返回 null', () => {
    expect(calcProfit({ costPrice: 0, totalShares: 1000, records: [] })).toBeNull();
    expect(calcProfit({ costPrice: 10, totalShares: 0, records: [] })).toBeNull();
    expect(calcProfit({ costPrice: -5, totalShares: 100, records: [] })).toBeNull();
  });

  test('单笔已卖出 - 盈利', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [{ price: 15, shares: 500, type: 'done', id: 1 }],
    });
    expect(result.soldShares).toBe(500);
    expect(result.soldRevenue).toBe(7500);
    expect(result.remainShares).toBe(500);
    // profit = (15-10)*500 = 2500
    expect(result.grandProfit).toBe(2500);
    expect(result.profitRate).toBeCloseTo(25, 1);
  });

  test('单笔已卖出 - 亏损', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [{ price: 8, shares: 500, type: 'done', id: 1 }],
    });
    // profit = (8-10)*500 = -1000
    expect(result.grandProfit).toBe(-1000);
    expect(result.profitRate).toBeCloseTo(-10, 1);
  });

  test('多笔混合（已卖出+计划卖出）', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [
        { price: 12, shares: 300, type: 'done', id: 1 },
        { price: 15, shares: 200, type: 'plan', id: 2 },
        { price: 20, shares: 100, type: 'plan', id: 3 },
      ],
    });
    expect(result.soldShares).toBe(300);
    expect(result.planShares).toBe(300);
    expect(result.remainShares).toBe(400);
    // soldRevenue = 12*300 = 3600
    // planRevenue = 15*200 + 20*100 = 3000+2000 = 5000
    expect(result.soldRevenue).toBe(3600);
    expect(result.planRevenue).toBe(5000);
    // totalProfit = 8600 - 600*10 = 8600 - 6000 = 2600
    expect(result.grandProfit).toBe(2600);
  });

  test('有实时价格 - 剩余仓位计入浮盈', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [{ price: 15, shares: 500, type: 'done', id: 1 }],
      currentRtPrice: 12,
    });
    // soldProfit = (15-10)*500 = 2500
    // remainProfit = (12-10)*500 = 1000
    expect(result.grandProfit).toBe(3500);
    expect(result.remainValue).toBe(6000);
    expect(result.remainShares).toBe(500);
    // profitRate = 3500/10000 = 35%
    expect(result.profitRate).toBeCloseTo(35, 1);
  });

  test('有实时价格 - 剩余仓位浮亏', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [{ price: 12, shares: 500, type: 'done', id: 1 }],
      currentRtPrice: 7,
    });
    // soldProfit = (12-10)*500 = 1000
    // remainProfit = (7-10)*500 = -1500
    expect(result.grandProfit).toBe(-500);
  });

  test('卖出均价计算', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [
        { price: 12, shares: 400, type: 'done', id: 1 },
        { price: 18, shares: 200, type: 'plan', id: 2 },
      ],
    });
    // avgSellPrice = (12*400 + 18*200) / 600 = (4800+3600)/600 = 14
    expect(result.avgSellPrice).toBe(14);
    expect(result.allSellShares).toBe(600);
  });

  test('全部卖出 - 无剩余', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 500,
      records: [
        { price: 15, shares: 300, type: 'done', id: 1 },
        { price: 20, shares: 200, type: 'done', id: 2 },
      ],
    });
    expect(result.remainShares).toBe(0);
    expect(result.soldShares).toBe(500);
    // profit = (15*300+20*200) - 500*10 = 4500+4000-5000 = 3500
    expect(result.grandProfit).toBe(3500);
    expect(result.profitRate).toBeCloseTo(70, 1);
  });

  test('收益率精度', () => {
    const result = calcProfit({
      costPrice: 3.5,
      totalShares: 2000,
      records: [{ price: 4.2, shares: 1000, type: 'done', id: 1 }],
    });
    // profit = (4.2-3.5)*1000 = 700
    // rate = 700/(3.5*2000)*100 = 700/7000*100 = 10%
    expect(result.profitRate).toBeCloseTo(10, 2);
  });
});

describe('moveRecord - 记录排序', () => {
  const records = [
    { id: 1, price: 10 },
    { id: 2, price: 20 },
    { id: 3, price: 30 },
    { id: 4, price: 40 },
  ];

  test('向下移动', () => {
    const result = moveRecord(records, 0, 2);
    expect(result.map(r => r.id)).toEqual([2, 3, 1, 4]);
  });

  test('向上移动', () => {
    const result = moveRecord(records, 3, 1);
    expect(result.map(r => r.id)).toEqual([1, 4, 2, 3]);
  });

  test('相同位置 - 不变', () => {
    const result = moveRecord(records, 1, 1);
    expect(result.map(r => r.id)).toEqual([1, 2, 3, 4]);
  });

  test('无效索引 - 不变', () => {
    expect(moveRecord(records, -1, 2).map(r => r.id)).toEqual([1, 2, 3, 4]);
    expect(moveRecord(records, 0, 10).map(r => r.id)).toEqual([1, 2, 3, 4]);
  });

  test('不修改原数组', () => {
    const original = [...records];
    moveRecord(records, 0, 3);
    expect(records).toEqual(original);
  });
});

describe('localStorage 方案存储', () => {
  const PLAN_STORAGE_KEY = 'cry_plans';

  beforeEach(() => {
    localStorage.clear();
  });

  function getPlans() {
    try { return JSON.parse(localStorage.getItem(PLAN_STORAGE_KEY)) || {}; }
    catch { return {}; }
  }

  test('空存储返回空对象', () => {
    expect(getPlans()).toEqual({});
  });

  test('存储和读取方案', () => {
    const plan = {
      stock: '2680 新奥能源',
      costPrice: 50.5,
      totalShares: 2000,
      records: [{ price: 60, shares: 500, type: 'done', id: 1 }],
      savedAt: new Date().toISOString(),
    };
    const plans = { '我的方案': plan };
    localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(plans));

    const loaded = getPlans();
    expect(loaded['我的方案']).toBeDefined();
    expect(loaded['我的方案'].stock).toBe('2680 新奥能源');
    expect(loaded['我的方案'].costPrice).toBe(50.5);
    expect(loaded['我的方案'].records).toHaveLength(1);
  });

  test('删除方案', () => {
    const plans = {
      '方案A': { stock: 'A', savedAt: '2026-01-01' },
      '方案B': { stock: 'B', savedAt: '2026-01-02' },
    };
    localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(plans));

    const loaded = getPlans();
    delete loaded['方案A'];
    localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(loaded));

    const after = getPlans();
    expect(after['方案A']).toBeUndefined();
    expect(after['方案B']).toBeDefined();
  });

  test('多方案存储', () => {
    const plans = {};
    for (let i = 1; i <= 10; i++) {
      plans[`方案${i}`] = { stock: `stock${i}`, costPrice: i * 10, savedAt: new Date().toISOString() };
    }
    localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(plans));

    const loaded = getPlans();
    expect(Object.keys(loaded)).toHaveLength(10);
    expect(loaded['方案5'].costPrice).toBe(50);
  });

  test('损坏的 JSON 返回空对象', () => {
    localStorage.setItem(PLAN_STORAGE_KEY, '{invalid json!!!');
    expect(getPlans()).toEqual({});
  });
});

describe('同步合并策略', () => {
  // Simulate the merge logic from syncPlans
  function mergePlans(localPlans, cloudPlans) {
    const merged = { ...cloudPlans };
    for (const name in localPlans) {
      const local = localPlans[name];
      const cloud = merged[name];
      if (!cloud || (local.savedAt && (!cloud.savedAt || local.savedAt > cloud.savedAt))) {
        merged[name] = local;
      }
    }
    return merged;
  }

  test('本地有云端没有 → 保留本地', () => {
    const local = { '新方案': { stock: 'A', savedAt: '2026-04-08T10:00:00Z' } };
    const cloud = {};
    const merged = mergePlans(local, cloud);
    expect(merged['新方案']).toBeDefined();
  });

  test('云端有本地没有 → 保留云端', () => {
    const local = {};
    const cloud = { '云端方案': { stock: 'B', savedAt: '2026-04-07T10:00:00Z' } };
    const merged = mergePlans(local, cloud);
    expect(merged['云端方案']).toBeDefined();
  });

  test('同名方案本地更新 → 用本地', () => {
    const local = { '方案X': { stock: 'A-new', savedAt: '2026-04-08T12:00:00Z' } };
    const cloud = { '方案X': { stock: 'A-old', savedAt: '2026-04-08T10:00:00Z' } };
    const merged = mergePlans(local, cloud);
    expect(merged['方案X'].stock).toBe('A-new');
  });

  test('同名方案云端更新 → 用云端', () => {
    const local = { '方案X': { stock: 'A-old', savedAt: '2026-04-08T08:00:00Z' } };
    const cloud = { '方案X': { stock: 'A-cloud', savedAt: '2026-04-08T12:00:00Z' } };
    const merged = mergePlans(local, cloud);
    expect(merged['方案X'].stock).toBe('A-cloud');
  });

  test('双方都有不同方案 → 全部保留', () => {
    const local = { '本地A': { stock: 'A', savedAt: '2026-04-08T10:00:00Z' } };
    const cloud = { '云端B': { stock: 'B', savedAt: '2026-04-08T10:00:00Z' } };
    const merged = mergePlans(local, cloud);
    expect(Object.keys(merged)).toHaveLength(2);
    expect(merged['本地A']).toBeDefined();
    expect(merged['云端B']).toBeDefined();
  });
});

describe('AES-GCM 加密/解密', () => {
  const { webcrypto } = require('crypto');
  const { TextEncoder: TE, TextDecoder: TD } = require('util');
  const subtle = webcrypto.subtle;
  const getRandomValues = (buf) => webcrypto.getRandomValues(buf);

  async function deriveKey(password) {
    const enc = new TE();
    const keyMaterial = await subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
    return subtle.deriveKey(
      { name: 'PBKDF2', salt: enc.encode('cry-salt-2026'), iterations: 100000, hash: 'SHA-256' },
      keyMaterial,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );
  }

  async function encryptData(data, password) {
    const key = await deriveKey(password);
    const enc = new TE();
    const iv = getRandomValues(new Uint8Array(12));
    const encrypted = await subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(JSON.stringify(data)));
    const buf = new Uint8Array(iv.length + encrypted.byteLength);
    buf.set(iv);
    buf.set(new Uint8Array(encrypted), iv.length);
    return Buffer.from(buf).toString('base64');
  }

  async function decryptData(base64, password) {
    const key = await deriveKey(password);
    const buf = Uint8Array.from(Buffer.from(base64, 'base64'));
    const iv = buf.slice(0, 12);
    const data = buf.slice(12);
    const decrypted = await subtle.decrypt({ name: 'AES-GCM', iv }, key, data);
    return JSON.parse(new TD().decode(decrypted));
  }

  test('加密后解密还原数据', async () => {
    const original = { '方案1': { stock: '2680', costPrice: 50, records: [] } };
    const encrypted = await encryptData(original, 'mypassword123');
    const decrypted = await decryptData(encrypted, 'mypassword123');
    expect(decrypted).toEqual(original);
  });

  test('不同密码无法解密', async () => {
    const data = { test: '秘密数据' };
    const encrypted = await encryptData(data, 'password1');
    await expect(decryptData(encrypted, 'wrongpassword')).rejects.toThrow();
  });

  test('加密结果是 base64 字符串', async () => {
    const encrypted = await encryptData({ a: 1 }, 'pass');
    expect(typeof encrypted).toBe('string');
    expect(() => Buffer.from(encrypted, 'base64')).not.toThrow();
  });

  test('每次加密结果不同（随机 IV）', async () => {
    const data = { same: 'data' };
    const enc1 = await encryptData(data, 'pass');
    const enc2 = await encryptData(data, 'pass');
    expect(enc1).not.toBe(enc2);
    // But both decrypt to same data
    expect(await decryptData(enc1, 'pass')).toEqual(data);
    expect(await decryptData(enc2, 'pass')).toEqual(data);
  });

  test('中文数据加密解密', async () => {
    const data = { '方案名': '新奥能源止盈', '备注': '分三批卖出' };
    const encrypted = await encryptData(data, '中文密码');
    const decrypted = await decryptData(encrypted, '中文密码');
    expect(decrypted).toEqual(data);
  });
});

describe('边界场景', () => {
  test('卖出股数超过总股数', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 100,
      records: [{ price: 15, shares: 200, type: 'done', id: 1 }],
    });
    expect(result.remainShares).toBe(-100);
    // Still calculates (no crash)
    expect(result.grandProfit).toBe(1000);
  });

  test('极小价格 (港股仙股)', () => {
    const result = calcProfit({
      costPrice: 0.01,
      totalShares: 1000000,
      records: [{ price: 0.02, shares: 500000, type: 'done', id: 1 }],
    });
    expect(result.grandProfit).toBeCloseTo(5000, 0);
  });

  test('极大数量', () => {
    const result = calcProfit({
      costPrice: 100,
      totalShares: 10000000,
      records: [{ price: 110, shares: 5000000, type: 'done', id: 1 }],
    });
    expect(result.grandProfit).toBe(50000000);
    expect(formatMoney(result.grandProfit)).toBe('5000.00万');
  });

  test('所有记录都是计划（无实际卖出）', () => {
    const result = calcProfit({
      costPrice: 10,
      totalShares: 1000,
      records: [
        { price: 15, shares: 500, type: 'plan', id: 1 },
        { price: 20, shares: 300, type: 'plan', id: 2 },
      ],
    });
    expect(result.soldShares).toBe(0);
    expect(result.planShares).toBe(800);
    expect(result.remainShares).toBe(200);
  });
});
