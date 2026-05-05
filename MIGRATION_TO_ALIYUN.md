# 阿里云迁移交接文档

把整个 `cry` 项目（深圳招聘聚合 + 静态站 + 邮件推送）从 GitHub Pages / GitHub Actions
迁到一台阿里云 ECS 上。迁完之后 GitHub 仓库可保留作为代码备份，也可以彻底关闭。

> 现状：GitHub Actions 的 schedule 触发器在 `chenruoyi0202-ship-it/cry` 这个 ship-it
> 自动账号下从来没成功跑过一次，导致每日邮件依赖 PR 合并副作用才能触发。迁到自管 cron
> 之后，可靠性问题彻底解决。

---

## 1. 总览

| 组件 | 现状 | 迁移后 |
|---|---|---|
| 静态站点（jobs.html / 02680.html / migraine.html / love.html / projects.html） | GitHub Pages 自动部署 | Nginx 直接对外暴露 `/var/www/cry/` |
| 数据文件（`data/*.json` `data/jobs_digest_*.md`） | git 提交回仓库 | 直接写到 `/var/www/cry/data/` 由 Nginx 服务 |
| 招聘爬虫 + digest + 邮件 | GitHub Actions cron（不靠谱） | systemd timer 或 `crontab` 每天定时跑 |
| 收藏云同步（favorites） | 写 GitHub 仓库的 `data/jobs_favorites.json` | 见 §8，二选一：继续用 GitHub 仓库 / 改写到阿里云本地 |
| 邮件出口（Resend） | 不动 | 不动 |
| 微信推送（PushPlus） | 不动 | 不动 |

---

## 2. 服务器要求

最小规格够用：

- **阿里云 ECS**：1 核 2 GB，40 GB 系统盘，**强烈建议选国内地域**（爬腾讯/字节/美团 API 比海外 IP 快很多且不容易被风控）
- **OS**：Ubuntu 22.04 LTS（下面所有命令都按这个写）
- **公网带宽**：1 Mbps 起步够用（静态站 + 偶发的数据下载）
- **域名**：建议自有域名一个（备案过的最好），然后把 A 记录指到 ECS 公网 IP。如果只想用 IP 直接访问也行，但 Resend 邮件里的链接和 PWA 图标会丑

---

## 3. 一次性环境准备

SSH 上服务器后，以 root 跑：

```bash
# 基础包
apt update && apt install -y python3 python3-pip python3-venv nginx git curl certbot python3-certbot-nginx

# 项目目录
mkdir -p /opt/cry /var/www/cry/data /var/log/cry
chown -R www-data:www-data /var/www/cry

# Python 虚拟环境
python3 -m venv /opt/cry/venv
/opt/cry/venv/bin/pip install --upgrade pip
/opt/cry/venv/bin/pip install requests markdown pycryptodome
```

---

## 4. 把代码搬上去

在本地：

```bash
# 在仓库根跑
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
  ./ root@<ECS_IP>:/opt/cry/repo/

# 静态文件 + 已有数据
ssh root@<ECS_IP> '
  cp /opt/cry/repo/*.html /var/www/cry/
  cp /opt/cry/repo/*.svg /var/www/cry/ 2>/dev/null || true
  cp /opt/cry/repo/*.png /var/www/cry/ 2>/dev/null || true
  cp /opt/cry/repo/*.json /var/www/cry/ 2>/dev/null || true
  cp -r /opt/cry/repo/data/* /var/www/cry/data/
  chown -R www-data:www-data /var/www/cry
'
```

之后 `/opt/cry/repo` 是代码仓库（含 scraper），`/var/www/cry` 是 Nginx 服务的目录（HTML + JSON）。

---

## 5. Nginx 站点配置

`/etc/nginx/sites-available/cry`：

```nginx
server {
    listen 80;
    server_name your.domain.com;          # ← 改成你的域名（或 _ 接受任意）
    root /var/www/cry;
    index projects.html jobs.html index.html;

    # JSON 数据文件不要 gzip 缓存，前端轮询要看实时
    location ~* \.(json|md)$ {
        add_header Cache-Control "no-cache, must-revalidate";
        add_header Access-Control-Allow-Origin "*";
    }

    # HTML 文件可以短期缓存
    location ~* \.html$ {
        add_header Cache-Control "public, max-age=300";
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
```

启用：

```bash
ln -s /etc/nginx/sites-available/cry /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default 2>/dev/null
nginx -t && systemctl reload nginx
```

HTTPS（有域名的话）：

```bash
certbot --nginx -d your.domain.com --non-interactive --agree-tos -m you@example.com
# 自动续期已被 certbot 装的 systemd timer 接管，不用动
```

---

## 6. 密钥管理

阿里云上不再用 GitHub Secrets，用环境变量文件：

```bash
cat > /opt/cry/secrets.env <<'EOF'
RESEND_API_KEY=re_QsM6pHMs_3CXmVqdgUhXBN78TrDFm9JRV
PUSHPLUS_TOKEN=
# 如果继续用 GitHub 同步收藏，留这个 PAT；否则可删
GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxxxxxx
EOF
chmod 600 /opt/cry/secrets.env
```

之后 cron 脚本会 `source` 这个文件读环境变量。

> **强烈建议**：迁移完成后立刻去 Resend dashboard 把当前这把 key revoke，建一把新的，
> 因为旧 key 加密后嵌在公开 repo 里，密码（020608）也写在前端 JS 里，等于半公开。
> 拿到新 key 后只需替换 `/opt/cry/secrets.env` 里的 `RESEND_API_KEY`。

---

## 7. 每日 cron

`/opt/cry/run_daily.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/cry/repo
source /opt/cry/secrets.env
export RESEND_API_KEY PUSHPLUS_TOKEN
export EMAIL_TO=512773445@qq.com
export DIGEST_PATH=/var/www/cry/data/jobs_digest_latest.md

PY=/opt/cry/venv/bin/python
LOG=/var/log/cry/daily-$(date +%Y%m%d).log

{
  echo "==== $(date -Iseconds) start ===="
  $PY scraper/scrape_jobs.py --company all
  $PY scraper/generate_jobs_digest.py
  # 把生成的数据同步到 Nginx 目录
  cp data/jobs.json data/jobs_seen.json /var/www/cry/data/
  cp data/jobs_digest_*.md /var/www/cry/data/
  $PY scraper/send_digest_email.py
  if [ -n "${PUSHPLUS_TOKEN:-}" ]; then
    DATE=$(date +%Y-%m-%d)
    TITLE="🏢 深圳招聘 · ${DATE} 新增推荐"
    CONTENT=$(cat /var/www/cry/data/jobs_digest_latest.md)
    curl -sS -X POST "http://www.pushplus.plus/send" \
      -H "Content-Type: application/json" \
      -d "$($PY -c "import sys,json,os; print(json.dumps({'token':os.environ['PUSHPLUS_TOKEN'],'title':'${TITLE}','content':sys.stdin.read(),'template':'markdown'}))" <<< "$CONTENT")"
  fi
  echo "==== $(date -Iseconds) ok ===="
} >> "$LOG" 2>&1
```

```bash
chmod +x /opt/cry/run_daily.sh

# crontab
crontab -e
# 加这一行（北京时间 09:07 每日）：
7 9 * * * /opt/cry/run_daily.sh
```

迁移后 **不再需要** dedup 标记文件 / watchdog / 备份 cron——本地 cron 几乎不会丢。

测试：

```bash
/opt/cry/run_daily.sh && tail -50 /var/log/cry/daily-$(date +%Y%m%d).log
```

输出末尾应该看到 `email sent to 512773445@qq.com (id=...)`，QQ 邮箱也应该收到一封。

---

## 8. 收藏云同步怎么处理

前端 `jobs.html` 里有"密码 020608 解锁后跨设备同步收藏"的功能，用的是 GitHub Contents
API 写仓库里的 `data/jobs_favorites.json`。迁移后两条路：

### 8a. 保留 GitHub 仓库做云同步（最省事）

什么都不改。`jobs.html` 继续读写 GitHub 仓库的那个 JSON 文件。即使主数据流跑在阿里
云上，GitHub 仓库仍然是你的"配置/收藏后端"。代价：仍然依赖 GitHub 可用性 + 那个 PAT
不过期。

### 8b. 改用阿里云后端

写一个极简 Flask/FastAPI 服务在 `/opt/cry/sync_api/`，监听 `127.0.0.1:8765`，Nginx
反代到 `/api/sync`。前端把 GitHub Contents API 的几次 fetch 换成 `/api/sync/get` /
`/api/sync/put`。数据落到 SQLite 或单个 JSON 文件。代码量大概 50 行。

> 推荐先 8a，等需要彻底切断 GitHub 依赖时再做 8b。

---

## 9. 日常运维

**查最近一次 cron 日志**：

```bash
ls -lt /var/log/cry/ | head -5
tail -100 /var/log/cry/daily-$(date +%Y%m%d).log
```

**改代码**：

```bash
# 本地改完 push 到 GitHub 仓库（如果保留），然后：
ssh root@<ECS_IP> 'cd /opt/cry/repo && git pull'

# 或者直接 rsync：
rsync -avz scraper/ root@<ECS_IP>:/opt/cry/repo/scraper/
```

**改 HTML 后让站点立刻生效**：

```bash
ssh root@<ECS_IP> 'cp /opt/cry/repo/*.html /var/www/cry/'
```

**手动重发当天邮件**：

```bash
ssh root@<ECS_IP> '/opt/cry/run_daily.sh'
```

---

## 10. 收尾：从 GitHub 退役

确认阿里云上稳定跑了一周邮件都正常之后：

1. **删 GitHub Actions workflows**（保留代码，去掉自动跑的部分）：
   ```bash
   git rm .github/workflows/jobs.yml .github/workflows/jobs-watchdog.yml \
          .github/workflows/ccass.yml .github/workflows/ccass-backfill.yml
   git commit -m "Retire GitHub Actions, migrated to Aliyun"
   git push
   ```

2. **关 GitHub Pages**：仓库 Settings → Pages → Source 改成 None。

3. （可选）**仓库设为 archive 或 private**：Settings 底部。

4. **DNS 切流**：之前 GitHub Pages 的域名（如有）的 A 记录改指阿里云 IP。

---

## 11. 参考：当前项目的关键代码位置

迁移过去后这些路径都按原样保留，方便 cron 脚本引用：

| 文件 | 作用 |
|---|---|
| `scraper/scrape_jobs.py` | 入口，`--company all` 跑全部 10 个数据源 |
| `scraper/jobs_sources/*.py` | 单个数据源的爬虫（tencent / bytedance / meituan / dji / byd / jd / netease / xiaomi / oppo / vivo） |
| `scraper/generate_jobs_digest.py` | 读 `data/jobs.json` + `data/jobs_seen.json` 算"今日新增"，按简历画像评分，写 `data/jobs_digest_YYYY-MM-DD.md` 和 `latest.md`。无新增时降级为最近 7 天 Top 15 |
| `scraper/send_digest_email.py` | 读 latest digest，渲染 markdown→HTML，调 Resend API 发到 `EMAIL_TO`。Resend key 来源：`$RESEND_API_KEY` 环境变量 → 否则从源码内嵌的密文解密 |
| `data/jobs.json` | 当前在招岗位全量 |
| `data/jobs_seen.json` | 历史首次出现日期，用来识别"今日新增" |
| `data/jobs_digest_latest.md` | 给邮件 / 微信 / Issue 用的最新一份 digest |
| `jobs.html` | 前端页面，`fetch('data/jobs.json?t=' + Date.now())` 读数据 |

---

## 12. 一份"懒人速查"清单

```
□ 开通 ECS（国内地域，1c2g，Ubuntu 22.04）
□ apt install python3 python3-pip python3-venv nginx git curl certbot python3-certbot-nginx
□ 创建 venv，pip install requests markdown pycryptodome
□ rsync 项目代码到 /opt/cry/repo
□ 拷贝 HTML/数据到 /var/www/cry
□ 写 /etc/nginx/sites-available/cry，启用，nginx -t && reload
□ 域名 A 记录指 ECS 公网 IP，certbot 拿 HTTPS 证书
□ 写 /opt/cry/secrets.env（chmod 600）
□ 写 /opt/cry/run_daily.sh（chmod +x）
□ crontab -e 加 "7 9 * * * /opt/cry/run_daily.sh"
□ 手动跑一次 /opt/cry/run_daily.sh，确认 QQ 邮箱收到
□ 观察 7 天，全绿后删 .github/workflows/，关 Pages
□ Resend 后台 revoke 旧 key，新 key 写进 /opt/cry/secrets.env
```

---

迁完一切照旧：每天 09:07 自动到一封日报邮件，前端可正常访问，但**不再依赖 GitHub
任何 cron / 部署机制**。
