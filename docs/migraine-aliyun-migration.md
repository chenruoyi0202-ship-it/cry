# 偏头痛记录 App — 阿里云迁移文档

## 一、当前架构（全 GitHub 依赖）

```
┌────────────┐     GitHub Pages      ┌──────────────────┐
│ 用户浏览器  │ ◄──── 静态文件托管 ────► │ cry 仓库 (公开)    │
│            │                        │ migraine.html    │
│ localStorage│     GitHub API        │                  │
│ (records)  │ ◄──── 数据读写 ────────► │ migraine-data    │
│            │   Contents API         │ 仓库 (私有)       │
│            │   User API             │ data/migraine.json│
└────────────┘                        └──────────────────┘

依赖清单:
1. GitHub Pages — 静态托管 migraine.html
2. GET  /user — Token 验证 + 获取用户名
3. POST /user/repos — 自动创建私有仓库
4. GET  /repos/{repo} — 获取默认分支名
5. GET  /repos/{repo}/contents/{path} — 读取数据
6. PUT  /repos/{repo}/contents/{path} — 写入数据（含 SHA 冲突检测）
```

## 二、目标架构（全阿里云）

```
┌────────────┐     阿里云 OSS/CDN     ┌──────────────────┐
│ 用户浏览器  │ ◄──── 静态文件托管 ────► │ OSS Bucket       │
│            │                        │ migraine.html    │
│ localStorage│     阿里云 FC/API      │                  │
│ (records)  │ ◄──── 数据读写 ────────► │ 函数计算 (FC)     │
│            │   RESTful API          │   ↓               │
│            │                        │ OSS / 表格存储    │
│            │                        │ data/migraine.json│
└────────────┘                        └──────────────────┘
```

## 三、迁移方案对照

### 3.1 静态托管：GitHub Pages → OSS + CDN

| 项目 | GitHub Pages | 阿里云方案 |
|------|-------------|-----------|
| 服务 | GitHub Pages | OSS 静态网站托管 + CDN |
| 域名 | `*.github.io` | 自定义域名（需 ICP 备案）|
| HTTPS | 自动 | 上传 SSL 证书或用免费证书 |
| 部署 | git push → 自动 | ossutil / GitHub Actions → OSS 或 FC 部署 |
| 费用 | 免费 | OSS 约 ¥0.12/GB/月 + CDN 流量费 |

**操作步骤：**
1. 创建 OSS Bucket（华南1-深圳），开启静态网站托管
2. 上传 `migraine.html`、`migraine-logo.png`、`migraine-logo.svg`、`manifest.json`
3. 绑定自定义域名 + 配置 HTTPS
4. （可选）接入 CDN 加速

### 3.2 数据同步 API：GitHub Contents API → 阿里云函数计算 (FC)

GitHub Contents API 做了 3 件事：认证、读、写。用 FC 替代：

| GitHub API | 阿里云替代 | 说明 |
|-----------|-----------|------|
| `GET /user` | FC `POST /api/login` | 验证密码/Token，返回 JWT |
| `GET /repos/.../contents/...` | FC `GET /api/data` | 从 OSS 读 JSON |
| `PUT /repos/.../contents/...` | FC `PUT /api/data` | 写 JSON 到 OSS |
| `POST /user/repos` | 不需要 | 无需自动创建仓库 |
| SHA 冲突检测 | ETag / If-Match | OSS 原生支持 |

#### FC 函数设计（3 个端点）

```
POST /api/login
  请求: { password: "xxx" }
  响应: { token: "jwt_xxx" }
  说明: 验证密码，返回 JWT（有效期 30 天）

GET /api/data
  请求头: Authorization: Bearer jwt_xxx
  响应: { records: [...], deletedIds: [...], updatedAt: "..." }
  说明: 从 OSS 读取 data/migraine.json

PUT /api/data
  请求头: Authorization: Bearer jwt_xxx, If-Match: "etag_xxx"
  请求体: { records: [...], deletedIds: [...] }
  响应: { etag: "new_etag" }
  说明: 写入 OSS，用 ETag 做冲突检测（替代 GitHub SHA）
```

#### FC 函数代码骨架（Node.js）

```javascript
// aliyun-fc/index.js
const OSS = require('ali-oss');
const jwt = require('jsonwebtoken');

const client = new OSS({
  region: 'oss-cn-shenzhen',
  accessKeyId: process.env.ACCESS_KEY_ID,
  accessKeySecret: process.env.ACCESS_KEY_SECRET,
  bucket: 'migraine-data-private'
});

const JWT_SECRET = process.env.JWT_SECRET;
const DATA_KEY = 'data/migraine.json';

// POST /api/login
exports.login = async (req) => {
  const { password } = JSON.parse(req.body);
  if (password !== process.env.USER_PASSWORD) {
    return { statusCode: 401, body: JSON.stringify({ error: '密码错误' }) };
  }
  const token = jwt.sign({ sub: 'user' }, JWT_SECRET, { expiresIn: '30d' });
  return { statusCode: 200, body: JSON.stringify({ token }) };
};

// GET /api/data
exports.getData = async (req) => {
  const auth = verifyToken(req);
  if (!auth) return { statusCode: 401, body: '未授权' };
  try {
    const result = await client.get(DATA_KEY);
    return {
      statusCode: 200,
      headers: { 'ETag': result.res.headers.etag },
      body: result.content.toString()
    };
  } catch (e) {
    if (e.code === 'NoSuchKey') return { statusCode: 200, body: JSON.stringify({ records: [], deletedIds: [] }) };
    throw e;
  }
};

// PUT /api/data
exports.putData = async (req) => {
  const auth = verifyToken(req);
  if (!auth) return { statusCode: 401, body: '未授权' };
  const ifMatch = req.headers['if-match'];
  const body = JSON.parse(req.body);
  body.updatedAt = new Date().toISOString();
  const content = JSON.stringify(body, null, 2);
  try {
    const result = await client.put(DATA_KEY, Buffer.from(content), {
      headers: ifMatch ? { 'If-Match': ifMatch } : {}
    });
    return {
      statusCode: 200,
      headers: { 'ETag': result.res.headers.etag },
      body: JSON.stringify({ ok: true })
    };
  } catch (e) {
    if (e.code === 'PreconditionFailed') {
      return { statusCode: 409, body: JSON.stringify({ error: '数据冲突，请重试' }) };
    }
    throw e;
  }
};

function verifyToken(req) {
  const h = req.headers.authorization;
  if (!h || !h.startsWith('Bearer ')) return null;
  try { return jwt.verify(h.slice(7), JWT_SECRET); }
  catch { return null; }
}
```

### 3.3 前端改动（migraine.html）

需要替换的代码段（约 80 行，全在 `<script>` 区域）：

```javascript
// ===== 替换前：GitHub API 相关 =====
// ghHeaders(), ghGetUser(), ensureRepo(), ghGetDefaultBranch(),
// ghGet(), ghPut(), ensurePrivateRepo()
// 
// ===== 替换后：阿里云 FC API =====

const API_BASE = 'https://your-fc-domain.cn-shenzhen.fc.aliyuncs.com';

async function apiLogin(password) {
  const res = await fetch(`${API_BASE}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password })
  });
  if (!res.ok) throw new Error('密码错误');
  const data = await res.json();
  return data.token;
}

async function apiGet(token) {
  const res = await fetch(`${API_BASE}/api/data`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) throw new Error(`拉取失败: ${res.status}`);
  return { data: await res.json(), etag: res.headers.get('ETag') };
}

async function apiPut(token, data, etag) {
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
  if (etag) headers['If-Match'] = etag;
  const res = await fetch(`${API_BASE}/api/data`, {
    method: 'PUT', headers,
    body: JSON.stringify(data)
  });
  if (res.status === 409) throw new Error('数据冲突');
  if (!res.ok) throw new Error(`推送失败: ${res.status}`);
  return res.headers.get('ETag');
}
```

**同步 UI 改动：**
- "GitHub Personal Access Token" → "登录密码"
- `<input type="password">` placeholder 改为 "输入你的密码"
- 去掉 GitHub Token 创建说明
- `saveSyncConfig()` 内部改为调 `apiLogin(password)` → 存 JWT 到 localStorage

**同步逻辑改动：**

| 函数 | 改动 |
|------|------|
| `pullFromCloud()` | `ghGet()` → `apiGet()`, 用 ETag 替代 SHA |
| `pushToCloud()` | `ghPut()` → `apiPut()`, 冲突检测用 ETag + 409 |
| `ensurePrivateRepo()` | 删除（不再需要） |
| `saveSyncConfig()` | 改为密码登录 + 存 JWT |
| `getDefaultBranch()` | 删除（不再需要） |

## 四、阿里云资源清单

| 资源 | 规格 | 月费估算 |
|------|------|---------|
| OSS Bucket（公开）| 静态托管 | ~¥1（几MB流量）|
| OSS Bucket（私有）| 数据存储 | ~¥0.1 |
| 函数计算 FC | Node.js 16+ | 免费额度内（每月 100 万次免费）|
| CDN（可选）| 加速静态资源 | ~¥5/月 |
| 域名 + SSL | 自定义域名 | ~¥50/年 |
| **合计** | | **~¥10/月**（有域名情况下）|

## 五、迁移步骤（按顺序执行）

### 第 1 步：准备阿里云资源（30 分钟）
1. 注册/登录阿里云控制台
2. 创建 OSS Bucket `migraine-static`（公开读），开启静态网站托管
3. 创建 OSS Bucket `migraine-data-private`（私有）
4. 创建函数计算 FC 服务
5. 配置环境变量：`ACCESS_KEY_ID`, `ACCESS_KEY_SECRET`, `JWT_SECRET`, `USER_PASSWORD`

### 第 2 步：部署 FC 函数（20 分钟）
1. 用上面的骨架代码创建 3 个 HTTP 触发器（login / getData / putData）
2. 配置 API 网关或自定义域名
3. 测试 API：`curl -X POST https://your-fc/api/login -d '{"password":"xxx"}'`

### 第 3 步：迁移数据（5 分钟）
1. 从 GitHub 私有仓库 `migraine-data` 下载 `data/migraine.json`
2. 上传到 OSS `migraine-data-private` 的 `data/migraine.json`

### 第 4 步：改前端代码（30 分钟）
1. 替换 GitHub API 函数为阿里云 FC API（如上所述）
2. 修改同步 UI（密码替代 Token）
3. 更新 `og:url`、`og:image` 为新域名
4. 上传 `migraine.html` 到 `migraine-static` Bucket

### 第 5 步：验证（15 分钟）
1. 访问新地址，输入密码登录
2. 验证数据拉取
3. 新增一条记录，验证推送
4. 在另一台设备验证跨端同步

### 第 6 步：切换 & 清理（10 分钟）
1. （可选）配置自定义域名指向 OSS
2. 停用 GitHub Pages 部署（删除 `.github/workflows/static.yml`）
3. 删除 GitHub `migraine-data` 私有仓库

## 六、回退方案

如果阿里云部署失败，所有旧代码和数据仍在 GitHub，随时可以回滚：
- `git revert` 前端改动
- 恢复 `static.yml` 工作流
- 用户重新输入 GitHub Token

## 七、不迁移不影响的部分

以下内容与偏头痛 App 无关，不需要迁移：
- `index.html`（止盈计算推演）
- `backend/`
- `.github/workflows/` 中的 `ccass.yml`, `jobs.yml` 等
- `data/` 中的 `love_*.json`, `stock_*.json`, `property.json`
