# 阿里云部署指南

## 前置条件

- 阿里云账号（已实名认证）
- 开通：函数计算 FC + 对象存储 OSS

## 第一步：创建 OSS Bucket

1. 打开 [OSS 控制台](https://oss.console.aliyun.com)
2. 点击「创建 Bucket」
   - 名称：`cry-plans`（或自定义）
   - 地域：华东1（杭州）
   - 存储类型：标准存储
   - 读写权限：私有
3. 创建后，进入 Bucket → 「跨域设置」→ 添加规则：
   - 来源：`*`
   - 允许 Methods：GET, POST, PUT, OPTIONS
   - 允许 Headers：`*`

## 第二步：创建 AccessKey

1. 打开 [AccessKey 管理](https://ram.console.aliyun.com/manage/ak)
2. 创建 AccessKey，记下 `AccessKey ID` 和 `AccessKey Secret`
3. **安全建议**：创建 RAM 子用户，只授权 OSS 读写权限

## 第三步：部署函数计算

1. 打开 [函数计算控制台](https://fcnext.console.aliyun.com)
2. 创建服务：名称 `cry-service`
3. 创建函数：
   - 运行环境：Node.js 18
   - 请求处理程序：`index.handler`
   - 上传方式：上传代码包
4. 打包代码：
   ```bash
   cd backend
   npm install
   zip -r code.zip index.mjs package.json node_modules/
   ```
5. 上传 `code.zip`
6. 配置环境变量：
   | 变量名 | 值 |
   |--------|-----|
   | OSS_REGION | oss-cn-hangzhou |
   | OSS_BUCKET | cry-plans（你创建的bucket名） |
   | ALI_KEY_ID | 你的 AccessKey ID |
   | ALI_KEY_SECRET | 你的 AccessKey Secret |
   | JWT_SECRET | 随便写一个复杂的字符串（如: cry-jwt-2026-xYz） |

## 第四步：配置 HTTP 触发器

1. 在函数详情页 → 「触发器」→ 创建触发器
2. 触发器类型：HTTP 触发器
3. 认证方式：无需认证
4. 请求方式：GET, POST, OPTIONS
5. 创建后会得到一个 URL，格式类似：
   ```
   https://cry-service-xxxxx.cn-hangzhou.fcapp.run
   ```

## 第五步：配置前端

打开 `index.html`，找到 `API_BASE`，填入你的函数 URL：

```javascript
const API_BASE = 'https://cry-service-xxxxx.cn-hangzhou.fcapp.run';
```

## 第六步：测试

1. 打开页面 → 点击「登录/注册」
2. 输入手机号 + 密码注册
3. 保存一个方案
4. 换一个浏览器/微信打开 → 登录同一个手机号 → 应该能看到方案

## 费用估算

| 服务 | 免费额度 | 超出后 |
|------|---------|--------|
| 函数计算 | 150万次/月 (3个月) | ¥0.0133/万次 |
| OSS 存储 | 5GB 永久免费 | ¥0.12/GB/月 |
| OSS 流量 | 5GB/月 | ¥0.50/GB |

个人使用基本在免费额度内。
