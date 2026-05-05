#!/usr/bin/env bash
# 安装 systemd timer：每天北京时间 09:07 跑一次 run_daily.sh。
# 用 systemd 而不是 crontab 是因为：
#   - 日志直接进 journalctl
#   - Persistent=true 在服务器宕机过节点后会补跑
#   - timezone 配置可以独立于系统时区

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root（写 /etc/systemd/system）" >&2; exit 1
fi

REPO_DIR="${REPO_DIR:-/opt/cry/repo}"

cat > /etc/systemd/system/cry-daily.service <<EOF
[Unit]
Description=cry daily scrape + digest + email
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$REPO_DIR/deploy/run_daily.sh
# 即便链路里有非 0 退出（比如 PushPlus 偶发失败），让它继续；run_daily.sh
# 已经把可恢复错误抓住了。
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/cry-daily.timer <<'EOF'
[Unit]
Description=Trigger cry-daily.service every morning (BJT 09:07)

[Timer]
# OnCalendar 解析为本地时区——install.sh 已经把系统时区设成 Asia/Shanghai
OnCalendar=*-*-* 09:07:00
# 错过窗口（比如服务器关了几小时再开机）补跑一次
Persistent=true
Unit=cry-daily.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now cry-daily.timer
systemctl list-timers --all | grep cry-daily || true

cat <<'EOF'

已安装 cry-daily.timer。

查状态：
  systemctl status cry-daily.timer
  systemctl list-timers cry-daily

立刻手动触发一次：
  systemctl start cry-daily.service
  journalctl -u cry-daily.service -f

EOF
