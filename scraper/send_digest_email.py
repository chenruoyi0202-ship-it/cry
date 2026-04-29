"""Send the daily 深圳大厂招聘 digest by email via SMTP.

Skips silently when EMAIL_AUTH_CODE is not set so the rest of the
workflow keeps working. Reads data/jobs_digest_latest.md, converts
markdown → HTML, and sends both plain and HTML parts.

Defaults are wired for QQ Mail SMTP (smtp.qq.com:465 SSL). To use a
different provider, override SMTP_HOST/SMTP_PORT/EMAIL_FROM env vars.
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

import markdown


def main() -> int:
    auth_code = os.environ.get('EMAIL_AUTH_CODE', '').strip()
    if not auth_code:
        print('EMAIL_AUTH_CODE not set, skip email')
        return 0

    email_from = os.environ.get('EMAIL_FROM', '512773445@qq.com')
    email_to = os.environ.get('EMAIL_TO', '512773445@qq.com')
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.qq.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '465'))
    digest_path = os.environ.get('DIGEST_PATH', 'data/jobs_digest_latest.md')

    if not os.path.exists(digest_path):
        print(f'no digest file at {digest_path}, skip email')
        return 0

    md_text = open(digest_path, encoding='utf-8').read()
    html_body = markdown.markdown(md_text, extensions=['extra', 'nl2br'])
    # Wrap in a minimal HTML shell so phone email clients render readably.
    html_full = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{font-family:-apple-system,"PingFang SC",sans-serif;line-height:1.65;color:#1a1a2e;max-width:680px;margin:0 auto;padding:18px}}
  h1{{font-size:18px;border-bottom:1px solid #e5e7eb;padding-bottom:8px}}
  h2{{font-size:15px;color:#0284c7;margin-top:22px}}
  a{{color:#0284c7;text-decoration:none}}
  a:hover{{text-decoration:underline}}
  code{{background:#f1f5f9;padding:1px 6px;border-radius:4px;font-size:11px;color:#0284c7}}
  hr{{border:0;border-top:1px solid #e5e7eb;margin:18px 0}}
  p{{margin:6px 0}}
</style></head><body>{html_body}</body></html>'''

    # Subject = first line of the digest, falls back to a static one.
    first_line = md_text.splitlines()[0] if md_text else '深圳招聘日报'
    subject = first_line.lstrip('# ').strip() or '深圳招聘日报'

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f'深圳招聘日报 <{email_from}>'
    msg['To'] = email_to
    msg['Date'] = formatdate(localtime=True)
    msg.attach(MIMEText(md_text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_full, 'html', 'utf-8'))

    print(f'sending → {email_to} via {smtp_host}:{smtp_port}…', flush=True)
    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as s:
        s.login(email_from, auth_code)
        s.sendmail(email_from, [email_to], msg.as_string())
    print(f'email sent to {email_to}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
