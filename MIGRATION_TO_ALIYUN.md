# 项目迁移交接文档：GitHub Pages → 阿里云服务器

## 一、项目概览

| 项目 | 说明 |
|---|---|
| 项目名 | cry — 个人工具集合站 |
| 当前部署 | GitHub Pages（chenruoyi0202-ship-it.github.io/cry） |
| 技术栈 | 纯静态 HTML/CSS/JS（无框架），Python 爬虫，Node.js 后端（可选） |
| 总文件数 | ~172 个 |
| 项目体积 | ~440MB（含 21MB 的 love_photos.json） |

---

## 二、项目结构

```
cry/
├── 前端页面（纯静态 HTML）
│   ├── index.html          # 止盈计算推演（股票工具）
│   ├── 02680.html          # 02680 创陞控股分析追踪（核心页面）
│   ├── 02680-sw.js         # Service Worker（可删除，迁移后不需要）
│   ├── love.html           # Our Memory（情侣记忆城堡）
│   ├── migraine.html       # 偏头痛记录
│   ├── projects.html       # 项目导航页
│   ├── property.html       # 房产数据
│   ├── currency.html       # 汇率工具
│   └── *.png/svg           # 各页面图标
│
├── data/                   # 数据文件
│   ├── stock_02680_encrypted.json    # 02680 分析数据（AES-256 加密）
│   ├── stock_02680_quote.json        # 02680 行情缓存
│   ├── stock_02680_ccass.json        # CCASS 最新数据
│   ├── stock_02680_ccass_report.md   # CCASS 报告（Markdown）
│   ├── stock_02680_ccass_report.pdf  # CCASS 报告（PDF）
│   ├── ccass_history/                # CCASS 历史快照
│   ├── love_encrypted.json           # 情侣数据（加密）
│   ├── love_photos.json              # 照片数据（21MB）
│   ├── migraine_encrypted.json       # 偏头痛数据（加密）
│   ├── property.json                 # 房产数据
│   └── 02680_full_analysis_report.md # 完整分析报告
│
├── scraper/                # Python 爬虫脚本
│   ├── scrape_ccass.py             # CCASS 数据抓取（港交所）
│   ├── analyze_ccass.py            # CCASS 分析报告生成
│   ├── generate_ccass_pdf.py       # CCASS PDF 生成
│   ├── participant_names.py        # 券商名称翻译
│   ├── scrape_property.py          # 房产数据抓取
│   └── requirements.txt            # Python 依赖
│
├── worker/                 # Cloudflare Worker（Yahoo Finance 代理）
│   ├── index.js
│   └── wrangler.toml
│
├── backend/                # Node.js 后端（阿里云 OSS 相关）
│   ├── index.mjs
│   ├── package.json
│   └── deploy.md
│
├── .github/workflows/      # GitHub Actions（需要替换）
│   ├── ccass.yml           # CCASS 定时抓取（每日 10:00 + 17:30）
│   ├── static.yml          # 静态页面部署
│   └── jobs-watchdog.yml   # 其他定时任务
│
└── tests/                  # 测试文件
```

---

## 三、需要迁移的服务（按优先级）

### 3.1 静态页面托管（替代 GitHub Pages）

**当前**：GitHub Pages 自动部署 main 分支的所有文件。

**阿里云方案**：
- **方案 A（推荐）**：阿里云 OSS + CDN
  - 把所有 HTML/CSS/JS/图片上传到 OSS Bucket
  - 配置 CDN 加速 + 自定义域名
  - 成本：约 ¥10/月
- **方案 B**：轻量服务器 + Nginx
  - 把文件放到 `/var/www/cry/`
  - Nginx 配置静态文件服务
  - 成本：服务器本身费用

**注意事项**：
- 需要修改所有页面中的 `chenruoyi0202-ship-it.github.io/cry` 为新域名
- og:image、og:url 等 meta 标签需要更新
- Service Worker（02680-sw.js）可以删除或保留（看需要）

### 3.2 数据同步（替代 GitHub API）

**当前**：02680.html 通过 GitHub Contents API 实现多设备同步：
- 用户输入 GitHub Token
- 数据 AES-256 加密后存到 `data/stock_02680_encrypted.json`
- 其他页面（love.html、migraine.html）也用类似方式

**阿里云方案**：需要一个简单的后端 API 来替代 GitHub API。

```
需要实现的 API：
POST /api/sync/pull   — 拉取最新数据
POST /api/sync/push   — 推送更新数据
POST /api/auth        — 验证 Token（或密码）

数据存储选项：
- 阿里云 OSS（最简单，直接存 JSON 文件）
- 阿里云 RDS（MySQL/PostgreSQL）
- 阿里云 Redis（如果数据量小）
- 直接存服务器本地文件（最省钱）
```

**需要改动的文件**（搜索 `ghGet`/`ghPut`/`ghAuth`/`api.github.com`）：

| 文件 | GitHub 依赖 | 改动量 |
|---|---|---|
| `02680.html` | 同步 CRUD、行情缓存推送 | ~100 行（替换 ghGet/ghPut） |
| `index.html` | Gist 同步 | ~50 行 |
| `love.html` | GitHub Contents API 同步 | ~80 行 |
| `migraine.html` | GitHub Contents API 同步 | ~80 行 |

### 3.3 定时任务（替代 GitHub Actions）

**当前**：GitHub Actions cron 任务：
- CCASS 抓取：每日 HKT 10:00 + 17:30
- PDF 报告生成
- GitHub Issue 通知 + pushplus 微信推送

**阿里云方案**：
- **方案 A**：服务器 crontab
  ```bash
  # /etc/crontab
  0  2 * * 1-5  root  cd /var/www/cry && python3 scraper/scrape_ccass.py && python3 scraper/analyze_ccass.py && python3 scraper/generate_ccass_pdf.py
  30 9 * * 1-5  root  cd /var/www/cry && python3 scraper/scrape_ccass.py && python3 scraper/analyze_ccass.py && python3 scraper/generate_ccass_pdf.py
  ```
- **方案 B**：阿里云函数计算（FC）+ 定时触发器
- **方案 C**：阿里云 ARMS 任务调度

**Python 依赖**：
```bash
pip install requests beautifulsoup4 markdown weasyprint
apt install fonts-noto-cjk-extra  # PDF 中文字体
```

### 3.4 行情数据代理（替代 Cloudflare Worker）

**当前**：`worker/index.js` 是一个 Cloudflare Worker，代理 Yahoo Finance API 请求。

**阿里云方案**：
- 在服务器上跑一个简单的 Node.js/Python 反向代理
- 或者直接在 Nginx 里配 proxy_pass
- 02680.html 里的 `stock-quote-proxy.chenruoyi0202.workers.dev` 换成新地址

---

## 四、02680.html 核心改动清单

这是最复杂的文件（~3000 行），以下是需要改的 GitHub 依赖：

### 4.1 同步模块（~200 行需要重写）

```javascript
// 当前代码中需要替换的函数：
ghAuth(token)           → 改为你的 API 认证方式
ghGetDefaultBranch()    → 删除（不再需要）
ghGet(token, repo, path, branch)  → 改为 fetch('/api/sync/pull')
ghPut(token, repo, path, content, sha, branch) → 改为 fetch('/api/sync/push')
pullFromCloud()         → 调用新的拉取 API
pushToCloud()           → 调用新的推送 API
pushQuoteCache()        → 调用新的行情缓存 API

// 常量需要替换：
SYNC_REPO = 'chenruoyi0202-ship-it/cry'  → 删除
SYNC_BRANCH = 'main'                     → 删除
SYNC_PASSWORD = 'cry-02680-sync-2026'    → 保留（加密用）
```

### 4.2 行情数据（~20 行需要改）

```javascript
// worker URL 替换
'https://stock-quote-proxy.chenruoyi0202.workers.dev/...'
→ 'https://你的域名/api/quote/...'  或直接用腾讯/新浪接口（已有）
```

### 4.3 CCASS 报告加载（~5 行需要改）

```javascript
// 当前从同源加载
fetch('data/stock_02680_ccass_report.md')
// 迁移后保持不变（只要文件路径正确）
```

### 4.4 og 标签（~4 行需要改）

```html
<!-- 替换域名 -->
<meta property="og:image" content="https://新域名/02680-icon.png">
<meta property="og:url" content="https://新域名/02680.html">
```

---

## 五、加密与安全

### 5.1 当前加密方案

```
算法：AES-256-GCM
密钥派生：PBKDF2（100,000 iterations, SHA-256）
盐：每次加密随机 16 字节
IV：每次加密随机 12 字节
密码：硬编码 'cry-02680-sync-2026'（建议迁移后改为用户输入）
```

数据格式：`[salt(16)][iv(12)][ciphertext]` → Base64

### 5.2 访客模式

```
密码：'zuge2680'（硬编码在 JS 中）
Owner 检测：localStorage 'stock_02680_owner' 或有 sync config
Guest：输过密码后记住（localStorage 'stock_02680_guest_ok'）
```

### 5.3 迁移建议

- 加密密码从硬编码改为用户首次设置
- 访客密码改为服务端验证（不暴露在前端 JS）
- Token 认证改为你自己的认证系统

---

## 六、数据文件说明

| 文件 | 大小 | 说明 | 敏感度 |
|---|---|---|---|
| `stock_02680_encrypted.json` | ~60KB | 分析/线索/时间线（AES加密） | 高 |
| `stock_02680_quote.json` | ~4KB | 行情缓存（明文） | 低 |
| `stock_02680_ccass.json` | ~60KB | CCASS 最新数据 | 低 |
| `love_encrypted.json` | ~15KB | 情侣数据（加密） | 高 |
| `love_photos.json` | ~21MB | 照片数据（加密） | 高 |
| `migraine_encrypted.json` | ~350B | 偏头痛数据（加密） | 高 |
| `property.json` | ~8KB | 房产数据（明文） | 中 |
| `ccass_history/*.json` | ~若干 | CCASS 历史快照 | 低 |

---

## 七、localStorage 键名清单

02680.html 使用的所有 localStorage 键：

| 键名 | 内容 |
|---|---|
| `stock_02680_analyses_v1` | 分析记录（JSON 数组） |
| `stock_02680_events_v1` | 线索记录 |
| `stock_02680_timeline_v1` | 推演时间线 |
| `stock_02680_deleted_v1` | 删除墓碑 |
| `stock_02680_sync_config` | 同步配置（Token等） |
| `stock_02680_seeded_v1` | 种子数据标记 |
| `stock_02680_timeline_seeded_v1` | 时间线种子标记 |
| `stock_02680_cost` | 成本价 |
| `stock_02680_owner` | Owner 标记 |
| `stock_02680_guest_ok` | 访客已验证标记 |
| `stock_02680_theme` | 主题偏好 |

---

## 八、迁移步骤（建议顺序）

### 第一步：部署静态文件（1小时）
1. 在阿里云服务器安装 Nginx
2. 把所有 HTML/CSS/JS/图片/data 文件上传到 `/var/www/cry/`
3. 配置 Nginx 虚拟主机
4. 绑定域名 + HTTPS 证书
5. 验证所有页面可以访问

### 第二步：搭建同步 API（2-4小时）
1. 写一个简单的 Node.js/Python 后端
2. 实现 pull/push/auth 三个接口
3. 数据存本地 JSON 文件（最简单）
4. 修改 02680.html/love.html/migraine.html 的同步代码
5. 测试多设备同步

### 第三步：配置定时任务（30分钟）
1. 安装 Python 依赖
2. 配置 crontab 跑 CCASS 抓取
3. 配置 pushplus 微信推送（如果需要）
4. 验证每日自动运行

### 第四步：迁移行情代理（30分钟）
1. 在 Nginx 配反向代理到 Yahoo Finance（或直接用腾讯接口）
2. 或部署 worker/index.js 为 Node.js 服务
3. 更新 02680.html 中的代理 URL

### 第五步：清理 GitHub 依赖（1小时）
1. 全局搜索替换 `chenruoyi0202-ship-it.github.io/cry` → 新域名
2. 删除 `.github/workflows/` 目录
3. 删除 `02680-sw.js`（或更新缓存策略）
4. 删除 `.deploy`、`.nojekyll` 等 GitHub 专用文件
5. 移除 JS 中的 `ghAuth`/`ghGet`/`ghPut` 函数

---

## 九、Nginx 配置参考

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    root /var/www/cry;
    index index.html;
    
    # 静态文件
    location / {
        try_files $uri $uri/ =404;
        add_header Cache-Control "public, max-age=3600";
    }
    
    # 数据文件不缓存
    location /data/ {
        add_header Cache-Control "no-cache";
    }
    
    # 同步 API 代理（如果后端跑在 3000 端口）
    location /api/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
    }
    
    # 行情代理
    location /api/quote/ {
        proxy_pass https://query1.finance.yahoo.com/;
        proxy_set_header Host query1.finance.yahoo.com;
    }
}
```

---

## 十、风险与注意事项

1. **加密数据迁移**：`*_encrypted.json` 文件直接复制即可，不需要解密。密码硬编码在 JS 中，换服务器不影响。
2. **21MB 照片数据**：`love_photos.json` 很大，建议迁移后改用 OSS 存储。
3. **CCASS 抓取**：依赖港交所网站，可能有 IP 限制。阿里云香港节点最佳。
4. **微信分享**：og 标签的图片 URL 必须是 HTTPS 且可公网访问。
5. **PWA**：当前 Service Worker 被禁用了（之前有缓存问题），迁移后可以重新启用。

---

*文档生成时间：2026-05-06*
*适用范围：cry 项目完整迁移至阿里云自有服务器*
