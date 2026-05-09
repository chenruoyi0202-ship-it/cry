# 止盈计算器（index.html）完全脱离 GitHub 迁移补充文档

> 本文档是 `MIGRATION_TO_ALIYUN.md` 的补充，专门针对 `index.html` 止盈计算推演页面。

---

## 一、当前 GitHub 依赖清单

index.html 对 GitHub 的依赖**只有一个**：Gist 同步。

| 依赖 | 用途 | 涉及函数 | 替代方案 |
|------|------|---------|---------|
| GitHub Gist API | 跨设备方案同步 | `gistGet/gistCreate/gistUpdate/gistFind/syncPlans/doAuth` | 阿里云 OSS 或服务端 JSON 文件 |

**不依赖 GitHub 的部分**（无需改动）：
- 汇率获取：Yahoo Finance（通过 CORS 代理）
- 股价获取：Yahoo Finance（通过 CORS 代理）
- 方案存储：localStorage（本地）
- 加密：Web Crypto API（纯浏览器端）
- 图表：canvas（纯浏览器端）

---

## 二、需要替换的代码段

### 2.1 Gist API 函数（约 60 行，全部删除替换）

```
文件: index.html
搜索关键词: gistGet, gistCreate, gistUpdate, gistFind, api.github.com/gists
```

需要替换的函数：
```javascript
gistGet(token, gistId)       // GET 读取 Gist
gistCreate(token, content)   // POST 创建 Gist
gistUpdate(token, gistId, content)  // PATCH 更新 Gist
gistFind(token)              // 搜索已有 Gist
```

### 2.2 认证函数（约 30 行）

```javascript
doAuth()       // 验证 GitHub Token → 改为验证阿里云凭证或 PIN
showAuth()     // 显示认证弹窗 → 简化为 PIN/密码输入
getGHToken()   // 读取 GitHub Token → 改为读取新凭证
setGHAuth()    // 存储 Token → 改为存储新凭证
clearAuth()    // 清除认证 → 保持
isLoggedIn()   // 判断是否登录 → 保持
```

### 2.3 同步函数（约 50 行）

```javascript
syncPlans(forceUpload)  // 核心同步逻辑 → 替换 API 调用
```

### 2.4 认证弹窗 HTML

```
搜索: id="authOverlay"
当前: 输入 GitHub Token
替换为: 输入 PIN 码或密码
```

---

## 三、阿里云替代方案（3 选 1）

### 方案 A：阿里云 OSS 直传（最简单，推荐）

原理：前端直接用 STS Token 读写 OSS 文件，不需要后端。

```
浏览器
  ↓ fetch
阿里云 OSS（存储 plans/{user_id}.enc）
```

成本：5GB 免费，几乎零成本。

需要：
1. 创建 OSS Bucket（私有读写）
2. 创建 RAM 用户，授权 OSS 读写
3. 前端集成阿里云 OSS SDK（或直接用 REST API + 签名）

改动量：替换 gist* 函数为 OSS 读写（约 60 行）。

### 方案 B：服务端 JSON 文件（最省钱）

原理：在阿里云服务器上跑一个简单 API，数据存为 JSON 文件。

```
浏览器
  ↓ fetch
Nginx → Node.js/Python API（3 个接口）
  ↓
/var/www/cry/sync/{pin_hash}.json
```

API 接口：
```
POST /api/cry/pull   { pin: "020608" }  → 返回加密数据
POST /api/cry/push   { pin: "020608", data: "..." }  → 写入加密数据
```

改动量：替换 gist* 函数为 fetch 新 API（约 60 行），加一个 50 行的 Node.js 后端。

### 方案 C：完全本地，不要同步

原理：删掉所有同步代码，只用 localStorage。不同设备的数据独立。

改动量：删除约 200 行同步相关代码。最简单但失去跨设备能力。

---

## 四、方案 B 实现参考（Node.js 后端）

### 4.1 后端代码

```javascript
// /opt/cry/api/sync.mjs
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { createHash } from 'crypto';
import http from 'http';

const SYNC_DIR = '/var/www/cry/sync';
const PORT = 3001;

if (!existsSync(SYNC_DIR)) mkdirSync(SYNC_DIR, { recursive: true });

function pinHash(pin) {
  return createHash('sha256').update('cry-sync-' + pin).digest('hex').slice(0, 16);
}

http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  let body = '';
  req.on('data', c => body += c);
  req.on('end', () => {
    try {
      const { pin, data } = JSON.parse(body);
      if (!pin || pin.length < 4) {
        res.writeHead(400); res.end('{"error":"PIN required"}'); return;
      }
      const file = `${SYNC_DIR}/${pinHash(pin)}.json`;

      if (req.url === '/api/cry/pull') {
        const content = existsSync(file) ? readFileSync(file, 'utf8') : '{}';
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(content);
      } else if (req.url === '/api/cry/push') {
        writeFileSync(file, JSON.stringify(data || {}));
        res.writeHead(200); res.end('{"ok":true}');
      } else {
        res.writeHead(404); res.end('{"error":"not found"}');
      }
    } catch (e) {
      res.writeHead(500); res.end('{"error":"server error"}');
    }
  });
}).listen(PORT, () => console.log(`Sync API on :${PORT}`));
```

### 4.2 Nginx 配置补充

```nginx
# 在现有 nginx.conf 的 server block 中添加：
location /api/cry/ {
    proxy_pass http://127.0.0.1:3001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 4.3 前端改动

将 index.html 中的 gist 函数替换为：

```javascript
// 替换 gistGet/gistCreate/gistUpdate/gistFind
const SYNC_API = 'https://你的域名/api/cry';

async function syncPull(pin) {
  const resp = await fetch(SYNC_API + '/pull', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin })
  });
  return await resp.json();
}

async function syncPush(pin, data) {
  await fetch(SYNC_API + '/push', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin, data })
  });
}
```

---

## 五、迁移步骤

### 第一步：部署静态文件（10 分钟）

```bash
# 在阿里云服务器上
rsync -avz --exclude='.git' --exclude='node_modules' \
  /path/to/cry/ root@<ECS_IP>:/var/www/cry/

# 或者从 GitHub 拉取
cd /opt/cry && git clone https://github.com/chenruoyi0202-ship-it/cry.git repo
bash /opt/cry/repo/deploy/sync_static.sh
```

### 第二步：部署同步 API（20 分钟）

```bash
# 1. 上传 sync.mjs
mkdir -p /opt/cry/api
# 复制上面的 sync.mjs 到 /opt/cry/api/

# 2. 安装 Node.js（如果没有）
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt install -y nodejs

# 3. 用 systemd 管理
cat > /etc/systemd/system/cry-sync.service <<'EOF'
[Unit]
Description=Cry Sync API
After=network.target

[Service]
ExecStart=/usr/bin/node /opt/cry/api/sync.mjs
Restart=always
WorkingDirectory=/opt/cry/api

[Install]
WantedBy=multi-user.target
EOF

systemctl enable cry-sync && systemctl start cry-sync
```

### 第三步：修改 index.html（30 分钟）

1. 删除 Gist 相关函数（gistGet/gistCreate/gistUpdate/gistFind）
2. 替换 syncPlans 为新的 pull/push 逻辑
3. 替换 doAuth 弹窗为 PIN 输入
4. 更新 og:url、og:image 为新域名

### 第四步：配置 HTTPS（10 分钟）

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d 你的域名
```

### 第五步：DNS 切换

在域名管理中将 A 记录指向阿里云服务器 IP。

### 第六步：验证 + 清理 GitHub

```bash
# 验证所有功能正常后：
# 1. 关闭 GitHub Pages：Settings → Pages → 关闭
# 2. 删除 .github/workflows/ 中的 static.yml
# 3. 可选：将 GitHub 仓库设为 private 或 archive
```

---

## 六、数据迁移

止盈计算器的方案数据存在 GitHub Gist 中（加密的 JSON）。迁移步骤：

1. 在旧版页面登录，打开浏览器控制台
2. 执行：`console.log(JSON.stringify(getPlans()))` 复制输出
3. 在新版页面打开控制台
4. 执行：`localStorage.setItem('cry_plans', '粘贴的内容')`
5. 刷新页面，方案数据恢复

或者直接把 Gist 中的加密数据下载，放到新的同步存储中。

---

## 七、回退计划

如果迁移后出问题，立即回退：
1. DNS 改回 GitHub Pages 的 CNAME
2. 重新开启 GitHub Pages
3. 用户刷新页面即回到旧版

建议新旧并行运行 1 周后再关闭 GitHub Pages。

---

## 八、成本估算

| 项目 | 月费用 |
|------|-------|
| 阿里云轻量服务器 2C2G | ¥60-100 |
| 域名 | ¥50-70/年 |
| SSL 证书 | 免费（Let's Encrypt） |
| **合计** | **约 ¥70/月** |

如果已有服务器，增量成本为 0。

---

*生成时间：2026-05-09*
*适用于：index.html 止盈计算推演完全脱离 GitHub*
