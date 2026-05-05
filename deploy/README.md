# `deploy/` — 阿里云部署套件

配套 `MIGRATION_TO_ALIYUN.md` 的现成脚本/配置。在新 Ubuntu 22.04 ECS 上从零部署的最短路径：

```bash
# 1. 把 repo 拉到 /opt/cry/repo
mkdir -p /opt/cry && cd /opt/cry
git clone https://github.com/chenruoyi0202-ship-it/cry.git repo
# 或者：rsync -avz --exclude='.git' /path/to/local/cry/ root@<ECS_IP>:/opt/cry/repo/

# 2. 装系统包 + venv + Python 依赖
bash /opt/cry/repo/deploy/install.sh

# 3. 配置密钥
cp /opt/cry/repo/deploy/secrets.env.example /opt/cry/secrets.env
vim /opt/cry/secrets.env          # 填 RESEND_API_KEY 等
chmod 600 /opt/cry/secrets.env

# 4. Nginx
cp /opt/cry/repo/deploy/nginx.conf /etc/nginx/sites-available/cry
sed -i 's/your.domain.com/example.com/g' /etc/nginx/sites-available/cry
ln -sf /etc/nginx/sites-available/cry /etc/nginx/sites-enabled/cry
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 5. 同步静态文件到 webroot
bash /opt/cry/repo/deploy/sync_static.sh

# 6. HTTPS（有域名时；DNS A 记录先指过来）
certbot --nginx -d example.com

# 7. 装 systemd timer（每天 BJT 09:07 自动跑）
bash /opt/cry/repo/deploy/install_timer.sh

# 8. 立刻跑一次确认全链路通
systemctl start cry-daily.service
journalctl -u cry-daily.service -n 200 --no-pager
# 或直接：
/opt/cry/repo/deploy/run_daily.sh
tail -100 /var/log/cry/daily-$(date +%Y%m%d).log
```

最后一步看到 `email sent to 512773445@qq.com (id=...)` + 自己 QQ 邮箱收到日报，就齐活。

## 文件总览

| 文件 | 作用 |
|---|---|
| `install.sh` | 一次性环境（apt + venv + pip）。可重复跑、幂等。 |
| `nginx.conf` | Nginx 站点模板。`your.domain.com` 替换成实际域名。|
| `secrets.env.example` | 密钥模板。复制为 `/opt/cry/secrets.env` 填值。|
| `sync_static.sh` | 把 repo 里的 HTML / SVG / JSON 同步到 `/var/www/cry/`。改完代码 `git pull` 后跑一次。 |
| `run_daily.sh` | 每日核心脚本：scrape → digest → 推 email + 微信。 |
| `install_timer.sh` | 创建 systemd timer，每天 BJT 09:07 触发 `run_daily.sh`。 |

## 路径约定

| 路径 | 用途 |
|---|---|
| `/opt/cry/repo` | 代码仓库（这个仓库的 clone） |
| `/opt/cry/venv` | Python 虚拟环境 |
| `/opt/cry/secrets.env` | 密钥（`chmod 600`，**不要进 git**） |
| `/var/www/cry` | Nginx 服务的 webroot（HTML + JSON 在这里） |
| `/var/log/cry/daily-YYYYMMDD.log` | 每天 cron 日志 |
| `/etc/systemd/system/cry-daily.{service,timer}` | systemd 单元 |

要改哪个路径，所有脚本头部都有 `XXX="${XXX:-...}"` 形式的环境变量覆盖。

## 改代码后的发布流程

```bash
ssh root@<ECS_IP>
cd /opt/cry/repo && git pull
bash deploy/sync_static.sh             # 让网页改动立即生效
# Python 改动不需要做什么——下一次 timer 自动用新代码
# 想立刻验证：systemctl start cry-daily.service
```

## 常见问题

**邮件没到？**
```bash
journalctl -u cry-daily.service -n 200 --no-pager
tail -200 /var/log/cry/daily-$(date +%Y%m%d).log
```
看末尾的 `email sent` / `Resend send failed` 行。Resend 后台 https://resend.com/emails 也能看每封邮件的投递状态。

**timer 不触发？**
```bash
systemctl status cry-daily.timer
systemctl list-timers cry-daily
```
确认 `Active: active (waiting)` 且 `NEXT` 列显示了下一次触发时间。

**爬虫某个数据源失败？**
正常现象，已经做了 per-source 隔离：单个失败保留它上次的快照。`tail -200 /var/log/cry/daily-...log` 会看到具体哪家失败、什么错。

**想删 GitHub Actions 完全脱钩？**
等阿里云这边连续稳定一周后，参考 `MIGRATION_TO_ALIYUN.md` §10。
