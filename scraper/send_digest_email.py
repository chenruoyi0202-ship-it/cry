"""Send the daily 深圳大厂招聘 digest by email via Resend.

The user wanted email delivery without owning a sending mailbox. Resend
exposes a shared "onboarding@resend.dev" from-address that works
without domain verification — sign up at resend.com, grab an API key,
and you can send to any inbox immediately.

Skips silently when RESEND_API_KEY is not set so the rest of the
workflow keeps working.
"""
from __future__ import annotations

import json
import os
import sys

import requests
import markdown


RESEND_URL = 'https://api.resend.com/emails'
DEFAULT_FROM = 'Jobs Digest <onboarding@resend.dev>'
DEFAULT_TO = '512773445@qq.com'
DEFAULT_DIGEST = 'data/jobs_digest_latest.md'


def main() -> int:
    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    if not api_key:
        print('RESEND_API_KEY not set, skip email')
        return 0

    email_to = os.environ.get('EMAIL_TO', DEFAULT_TO)
    email_from = os.environ.get('EMAIL_FROM', DEFAULT_FROM)
    digest_path = os.environ.get('DIGEST_PATH', DEFAULT_DIGEST)

    if not os.path.exists(digest_path):
        print(f'no digest file at {digest_path}, skip email')
        return 0

    md_text = open(digest_path, encoding='utf-8').read()
    html_body = markdown.markdown(md_text, extensions=['extra', 'nl2br'])
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

    first_line = md_text.splitlines()[0] if md_text else '深圳招聘日报'
    subject = first_line.lstrip('# ').strip() or '深圳招聘日报'

    payload = {
        'from': email_from,
        'to': [email_to],
        'subject': subject,
        'html': html_full,
        'text': md_text,
    }
    print(f'sending → {email_to} via Resend…', flush=True)
    resp = requests.post(
        RESEND_URL,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        data=json.dumps(payload),
        timeout=30,
    )
    if resp.status_code >= 400:
        print(f'Resend send failed {resp.status_code}: {resp.text[:300]}',
              file=sys.stderr)
        return 2
    body = resp.json()
    print(f'email sent to {email_to} (id={body.get("id")})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
