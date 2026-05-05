#!/usr/bin/env bash
# 一次性环境准备：装系统包、建 venv、装 Python 依赖、创建运行时目录。
# 在 Ubuntu 22.04 ECS 上以 root 跑：
#   bash deploy/install.sh
# 完成后参考 deploy/README.md 配置 Nginx / 密钥 / cron。

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/cry/repo}"     # 本仓库 clone/rsync 的目标
VENV_DIR="${VENV_DIR:-/opt/cry/venv}"     # Python venv
WWW_DIR="${WWW_DIR:-/var/www/cry}"        # Nginx 服务的 webroot
LOG_DIR="${LOG_DIR:-/var/log/cry}"        # 日志

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 跑（需要 apt + 写 /opt /var/www /var/log）" >&2
  exit 1
fi

echo "==> 安装系统包"
apt update
apt install -y \
  python3 python3-pip python3-venv \
  nginx git curl rsync \
  certbot python3-certbot-nginx \
  ca-certificates tzdata
# 时区：让 cron 按北京时间跑
timedatectl set-timezone Asia/Shanghai || true

echo "==> 创建目录"
mkdir -p "$(dirname "$REPO_DIR")" "$WWW_DIR/data" "$LOG_DIR"

echo "==> 建 Python venv"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install requests markdown pycryptodome

echo "==> 完成基础环境。下一步："
cat <<'EOF'

  1. rsync / git clone 仓库到 /opt/cry/repo
  2. cp /opt/cry/repo/deploy/secrets.env.example /opt/cry/secrets.env
     编辑填好 RESEND_API_KEY 等，chmod 600 /opt/cry/secrets.env
  3. 部署 Nginx 配置：
       cp /opt/cry/repo/deploy/nginx.conf /etc/nginx/sites-available/cry
       sed -i 's/your.domain.com/<你的域名>/g' /etc/nginx/sites-available/cry
       ln -sf /etc/nginx/sites-available/cry /etc/nginx/sites-enabled/cry
       rm -f /etc/nginx/sites-enabled/default
       nginx -t && systemctl reload nginx
  4. 同步静态资源：
       bash /opt/cry/repo/deploy/sync_static.sh
  5. （有域名）certbot --nginx -d <你的域名>
  6. 安装 systemd timer：
       bash /opt/cry/repo/deploy/install_timer.sh
  7. 立刻跑一次确认链路通：
       /opt/cry/repo/deploy/run_daily.sh
       tail -100 /var/log/cry/daily-$(date +%Y%m%d).log

EOF
