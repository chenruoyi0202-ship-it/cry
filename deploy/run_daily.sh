#!/usr/bin/env bash
# 每日抓取 + digest + 发邮件 + 微信推送。
# 由 systemd timer（推荐）或 crontab 触发。
# 手动跑：
#   /opt/cry/repo/deploy/run_daily.sh

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/cry/repo}"
VENV_DIR="${VENV_DIR:-/opt/cry/venv}"
WWW_DIR="${WWW_DIR:-/var/www/cry}"
LOG_DIR="${LOG_DIR:-/var/log/cry}"
SECRETS_FILE="${SECRETS_FILE:-/opt/cry/secrets.env}"

PY="$VENV_DIR/bin/python"

# 加载密钥（RESEND_API_KEY / PUSHPLUS_TOKEN / 等）
if [ -f "$SECRETS_FILE" ]; then
  set -a; . "$SECRETS_FILE"; set +a
fi

# 邮件发到这里
export EMAIL_TO="${EMAIL_TO:-512773445@qq.com}"
# digest 输出位置（生成器写到 repo data/，后面会 cp 到 webroot）
export DIGEST_PATH="${DIGEST_PATH:-$REPO_DIR/data/jobs_digest_latest.md}"

mkdir -p "$LOG_DIR" "$WWW_DIR/data"
LOG_FILE="$LOG_DIR/daily-$(date +%Y%m%d).log"

cd "$REPO_DIR"

{
  echo "==== $(date -Iseconds) start ===="

  echo "-- scrape"
  "$PY" scraper/scrape_jobs.py --company all

  echo "-- generate digest"
  "$PY" scraper/generate_jobs_digest.py

  echo "-- publish data to webroot"
  cp data/jobs.json data/jobs_seen.json "$WWW_DIR/data/"
  cp data/jobs_digest_*.md "$WWW_DIR/data/" 2>/dev/null || true

  echo "-- send email (Resend)"
  "$PY" scraper/send_digest_email.py

  if [ -n "${PUSHPLUS_TOKEN:-}" ]; then
    echo "-- push to WeChat (PushPlus)"
    DATE=$(date +%Y-%m-%d)
    TITLE="🏢 深圳招聘 · ${DATE} 新增推荐"
    "$PY" - <<PYEOF || echo "pushplus failed (non-fatal)"
import json, os, requests
content = open(os.environ['DIGEST_PATH'], encoding='utf-8').read()
r = requests.post(
    'http://www.pushplus.plus/send',
    json={
        'token': os.environ['PUSHPLUS_TOKEN'],
        'title': '${TITLE}',
        'content': content,
        'template': 'markdown',
    },
    timeout=15,
)
print('pushplus:', r.status_code, r.text[:200])
PYEOF
  else
    echo "-- skip WeChat (PUSHPLUS_TOKEN not set)"
  fi

  echo "==== $(date -Iseconds) ok ===="
} >> "$LOG_FILE" 2>&1
