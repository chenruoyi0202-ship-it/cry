"""Send the daily 深圳大厂招聘 digest by email via Resend.

The user wanted email delivery without owning a sending mailbox. Resend
exposes a shared "onboarding@resend.dev" from-address that works
without domain verification.

Auth: prefer the RESEND_API_KEY env var (set as a GitHub secret) when
present; otherwise fall back to a copy of the key encrypted in source
under the same 020608 password used for the page sync token. Same
security posture as the embedded PAT — anyone reading the public repo
can decrypt, but Resend free tier is rate-limited and trivial to
rotate if abused.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import sys

import requests
import markdown


RESEND_URL = 'https://api.resend.com/emails'
DEFAULT_FROM = 'Jobs Digest <onboarding@resend.dev>'
DEFAULT_TO = '512773445@qq.com'
DEFAULT_DIGEST = 'data/jobs_digest_latest.md'
NOTIFIED_MARKER = 'data/jobs_notified_date.txt'


def _today_bjt() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d')


def _already_notified_today() -> bool:
    try:
        with open(NOTIFIED_MARKER, encoding='utf-8') as f:
            return f.read().strip() == _today_bjt()
    except FileNotFoundError:
        return False


def _mark_notified_today() -> None:
    os.makedirs(os.path.dirname(NOTIFIED_MARKER), exist_ok=True)
    with open(NOTIFIED_MARKER, 'w', encoding='utf-8') as f:
        f.write(_today_bjt())

# AES-256-GCM(PBKDF2-SHA256(password='020608', salt='cry-jobs-resend-v1', iter=100000))
# encryption of the Resend API key. Output is base64(iv||ciphertext||tag).
EMBEDDED_KEY_CIPHERTEXT_B64 = (
    'zoH6+4IP1VnmpoJAn6+PNX5wLpndw69r6eXSaFNBONqpMpM8bdVeUlq6o7TQ8ZzMQemzdstQRxIcH3qDPI91Hw=='
)
EMBEDDED_KEY_PASSWORD = b'020608'
EMBEDDED_KEY_SALT = b'cry-jobs-resend-v1'
EMBEDDED_KEY_ITERATIONS = 100000


def _decrypt_embedded_key() -> str:
    """Decrypt the in-source Resend key (pycryptodome AES-GCM)."""
    from Crypto.Cipher import AES
    derived = hashlib.pbkdf2_hmac(
        'sha256', EMBEDDED_KEY_PASSWORD, EMBEDDED_KEY_SALT,
        EMBEDDED_KEY_ITERATIONS, dklen=32,
    )
    blob = base64.b64decode(EMBEDDED_KEY_CIPHERTEXT_B64)
    iv, ciphertext, tag = blob[:12], blob[12:-16], blob[-16:]
    cipher = AES.new(derived, AES.MODE_GCM, nonce=iv)
    return cipher.decrypt_and_verify(ciphertext, tag).decode('ascii')


def main() -> int:
    if _already_notified_today():
        print(f'already sent today ({_today_bjt()} BJT), skip email')
        return 0

    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    if not api_key:
        try:
            api_key = _decrypt_embedded_key()
            print('using embedded resend key')
        except Exception as e:
            print(f'no resend key (env empty, embed decrypt failed: {e}), skip email')
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
    _mark_notified_today()
    return 0


if __name__ == '__main__':
    sys.exit(main())
