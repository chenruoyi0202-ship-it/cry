# Our Memory 迁移方案：GitHub → 阿里云全托管

## 一、当前架构

```
┌─────────────────────────────────────────────────┐
│ 浏览器 (love.html)                                │
│   ├─ 加密/解密: Web Crypto API (AES-256-GCM)     │
│   ├─ 密码: PBKDF2 200k iterations               │
│   └─ 缓存: localStorage + IndexedDB             │
└───────┬──────────────┬──────────────┬────────────┘
        │ 读取          │ 读取          │ 读写
        ▼              ▼              ▼
   ┌────────┐    ┌──────────┐    ┌──────────┐
   │ OSS    │    │ jsDelivr │    │ GitHub   │
   │ (读写) │    │ CDN(读)  │    │ API(读写)│
   └────────┘    └──────────┘    └──────────┘
```

### 数据文件
| 文件 | 大小 | 说明 |
|------|------|------|
| `data/love_encrypted.json` | ~16 KB | 元数据（纪念日、点滴、照片索引、足迹、配置） |
| `data/love_photos.json` | ~21 MB | 加密照片数据（base64 图片） |

### 密码
- 当前密码: `cryxyx`
- 加密方式: AES-256-GCM + PBKDF2 (salt 16字节, iv 12字节, 200000次迭代)
- 格式: `base64(salt + iv + ciphertext + tag)`

### 存储的密钥（在加密数据 appData 内部）
| 字段 | 说明 |
|------|------|
| `_ghToken` | GitHub Personal Access Token |
| `_ghRepo` | GitHub 仓库名 (owner/repo) |
| `_ossAkId` | 阿里云 AccessKey ID |
| `_ossAkSecret` | 阿里云 AccessKey Secret |
| `_qwenKey` | 通义千问 VL API Key（照片 AI 标签） |

---

## 二、迁移后目标架构

```
┌──────────────────────────────────┐
│ 浏览器 (love.html)               │
│   ├─ 加密/解密: 不变              │
│   └─ 缓存: 不变                  │
└───────┬──────────────────────────┘
        │ 读写（唯一数据源）
        ▼
   ┌──────────────────────┐
   │ 阿里云 OSS            │
   │ Bucket: our-memory    │
   │ 地域: 华东1(杭州)      │
   │ 公共读 + AK签名写     │
   └──────────────────────┘
```

### 页面托管
- `love.html` + 静态资源 → OSS 静态网站托管
- 访问地址: `https://our-memory.oss-cn-hangzhou.aliyuncs.com/love.html`
- 或绑定自定义域名

---

## 三、需要修改的代码模块

### 3.1 删除的模块（GitHub 相关）

| 函数/变量 | 行号 | 说明 |
|-----------|------|------|
| `GH_PATH`, `GH_PHOTOS_PATH` | 3229-3230 | GitHub 文件路径常量 |
| `detectRepo()` | 3294-3300 | 从 URL 检测 GitHub 仓库 |
| `GH_REPO` | 3300 | GitHub 仓库名 |
| `getToken()`, `getRepo()` | 3302-3303 | 获取 GitHub token/repo |
| `saveTokenCookie()` | 988-990 | 保存 GitHub token 到 cookie |
| `getTokenCookie()`, `getRepoCookie()` | 992-1001 | 读取 GitHub token cookie |
| `resolveGitHub()` | 1344-1357 | 解析 GitHub 认证信息 |
| `fetchMetaFromGitHub()` | 1361-1423 | 从 GitHub API 获取元数据 |
| `fetchPhotosBlob()` | 1424-1430 | 从 GitHub API 获取照片 |
| `fetchFromGitHubAPI()` | 1426-1432 | 完整 GitHub API 获取 |
| `syncFromGitHub()` | 1435-1453 | 后台同步 |
| `manualSync()` 中的 GitHub 逻辑 | 1461-1485 | 手动同步 |
| `pushToGitHub()` 中的 GitHub 部分 | 3337-3455 | 保存到 GitHub (blob/tree/commit/ref) |
| `fetchRetry()` | 3321-3335 | GitHub API 重试逻辑 |
| `tryAutoSync()` | 1487-1489 | 自动同步触发器 |
| jsDelivr CDN 相关 | 多处 | CDN 回退路径 |

### 3.2 保留并修改的模块（改为纯 OSS）

| 模块 | 当前行为 | 改为 |
|------|---------|------|
| `tryUnlock()` | OSS → CDN → API → Pages 多源加载 | 仅 OSS |
| `lazyLoadPhotos()` | OSS → Pages → CDN 竞速 | 仅 OSS |
| `pushToGitHub()` | 加密 → GitHub + OSS | 加密 → 仅 OSS |
| `manualSync()` | GitHub API 同步 | OSS 重新读取 |
| `showApp()` 中的 AK 自动设置 | 从 atob 解码 | 保留或改为配置页 |

### 3.3 不需要修改的模块

| 模块 | 说明 |
|------|------|
| 加密/解密 (`encryptData`, `decryptData`) | 纯前端，不依赖后端 |
| 密码管理 (`savePwd`, `getPwd`, `clearPwd`) | localStorage/cookie |
| 数据缓存 (`cacheData`, `getCachedData`) | localStorage |
| 照片缓存 (`cachePhotos`, `getCachedPhotos`) | IndexedDB |
| 所有 UI/渲染代码 | 纯前端 |
| 手势/Lightbox/点滴详情 | 纯前端 |
| EXIF 解析 / 照片压缩 | 纯前端 |
| 旅行地图 (Leaflet) | 纯前端 |
| AI 标签 (Qwen VL) | 直接调阿里云百炼 API |

---

## 四、OSS 配置要求

### 4.1 Bucket 设置
```
名称: our-memory
地域: oss-cn-hangzhou
读写权限: 公共读
```

### 4.2 静态网站托管
```
默认首页: love.html (或 index.html)
```

### 4.3 CORS 配置
```
来源: *
允许方法: GET, PUT, HEAD
允许 Headers: *
暴露 Headers: Content-Length, ETag
最大缓存时间: 3600
```

### 4.4 文件结构
```
our-memory/
├── love.html              ← 主页面
├── castle-icon.svg        ← 图标
├── castle-icon.png
├── cry-manifest.json      ← PWA manifest
└── data/
    ├── love_encrypted.json ← 加密元数据 (~16KB)
    └── love_photos.json    ← 加密照片 (~21MB)
```

---

## 五、改造后的保存流程

```javascript
// 简化后的 saveData
async function saveToOSS() {
    const pwd = currentPwd;
    const ak = getOssAk();

    // 1. 加密元数据
    appData._updatedAt = new Date().toISOString();
    const encMeta = await encryptData(pwd, appData);
    const metaOutput = JSON.stringify({ encrypted: encMeta, updatedAt: appData._updatedAt });

    // 2. 上传元数据到 OSS (秒传)
    await ossUpload('data/love_encrypted.json', metaOutput, 'application/json');

    // 3. 如果照片有变化，也上传
    if (photosDirty) {
        const photosData = {};
        appData.photos.forEach(p => { if (photoStore[p.id]) photosData[p.id] = photoStore[p.id]; });
        const encPhotos = await encryptData(pwd, photosData);
        await ossUpload('data/love_photos.json', JSON.stringify({ encrypted: encPhotos }), 'application/json');
        photosDirty = false;
    }

    // 4. 更新本地缓存
    cacheData(metaOutput);
    dirty = false;
}
```

### 改造后的加载流程

```javascript
// 简化后的 tryUnlock
async function tryUnlock(pwd) {
    // 1. 先试本地缓存
    let json = getCachedData();
    if (json) {
        appData = await decryptData(pwd, json.encrypted);
        let cachedPhotos = await getCachedPhotos();
        await loadPhotoStore(pwd, cachedPhotos);
        showApp(); renderAll();
        return true;
    }

    // 2. 从 OSS 加载元数据
    const resp = await fetch(ossUrl('data/love_encrypted.json') + '?v=' + Date.now());
    if (!resp.ok) return false;
    json = await resp.json();

    // 3. 解密并显示
    appData = await decryptData(pwd, json.encrypted);
    await loadPhotoStore(pwd, null);
    cacheData(JSON.stringify(json));
    showApp(); renderAll();

    // 4. 后台加载照片
    lazyLoadPhotosFromOSS(pwd);
    return true;
}

async function lazyLoadPhotosFromOSS(pwd) {
    const resp = await fetch(ossUrl('data/love_photos.json') + '?v=' + Date.now());
    if (!resp.ok) return;
    const photosJson = await resp.json();
    await loadPhotoStore(pwd, photosJson);
    await cachePhotos(photosJson);
    renderAll();
}
```

---

## 六、迁移步骤

### 步骤 1: 上传静态文件到 OSS
```bash
# 需要安装 ossutil
ossutil cp love.html oss://our-memory/love.html
ossutil cp castle-icon.svg oss://our-memory/castle-icon.svg
ossutil cp castle-icon.png oss://our-memory/castle-icon.png
ossutil cp cry-manifest.json oss://our-memory/cry-manifest.json
```

### 步骤 2: 确保数据文件在 OSS
```bash
# 检查
ossutil ls oss://our-memory/data/
# 应该有:
#   data/love_encrypted.json (~16KB)
#   data/love_photos.json (~21MB)
```

### 步骤 3: 修改 love.html
1. 删除所有 GitHub 相关代码
2. `pushToGitHub()` 改为 `saveToOSS()`
3. `tryUnlock()` 简化为只从 OSS 加载
4. `lazyLoadPhotos()` 简化为只从 OSS
5. `manualSync()` 改为从 OSS 重新读取

### 步骤 4: 上传修改后的 love.html 到 OSS
```bash
ossutil cp love.html oss://our-memory/love.html
```

### 步骤 5: 验证
- 打开 `https://our-memory.oss-cn-hangzhou.aliyuncs.com/love.html`
- 输入密码解锁
- 验证数据加载、照片显示、编辑保存

### 步骤 6（可选）: 绑定自定义域名
- 在 OSS 控制台绑定域名
- 配置 CNAME 解析
- 申请 SSL 证书（免费）

---

## 七、阿里云费用估算

| 项目 | 单价 | 预估用量 | 月费 |
|------|------|---------|------|
| OSS 存储 | 0.12 元/GB | ~25MB | ≈0 元 |
| OSS 请求 | 0.01 元/万次 | ~3000次/月 | ≈0 元 |
| 外网流量 | 0.5 元/GB | ~500MB/月 | ≈0.25 元 |
| **合计** | | | **< 1 元/月** |

---

## 八、注意事项

1. **AccessKey 安全**: AK 目前用 atob 编码存在 JS 里（不安全但可接受对个人项目）。更安全的方式是使用 STS 临时凭证。
2. **备份**: 迁移前导出 `love_encrypted.json` 和 `love_photos.json` 到本地备份。
3. **密码**: 不要丢失密码 `cryxyx`，数据无法在没有密码的情况下恢复。
4. **Qwen API**: AI 标签功能直接调阿里云百炼 API，不受迁移影响。
5. **GitHub 停用**: 迁移完成验证无误后，可以将 GitHub 仓库设为 private 或 archive。
