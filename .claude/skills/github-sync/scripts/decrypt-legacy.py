#!/usr/bin/env python3
"""
Decrypt legacy AES-GCM encrypted JSON files produced by older versions
of github-sync apps (when they used a user password + AES-GCM-256).

The encrypted format is:
    {"encrypted": "<base64(salt[16] + iv[12] + ciphertext + tag[16])>", "updatedAt": "..."}

Key derivation: PBKDF2-HMAC-SHA256, 100000 iterations, 32-byte output.

Usage:
    python3 decrypt-legacy.py <input.json> <password> [output.json]

If output is omitted, prints to stdout. Decrypted file uses the new
plain-JSON format: {"records": [...], "deletedIds": [], "updatedAt": "..."}

Requires: pycryptodome  (pip install pycryptodome)
"""
import json
import base64
import hashlib
import sys
from pathlib import Path

try:
    from Crypto.Cipher import AES
except ImportError:
    print("Error: pycryptodome not installed. Run: pip install pycryptodome", file=sys.stderr)
    sys.exit(1)


def decrypt(input_path: str, password: str) -> dict:
    with open(input_path) as f:
        payload = json.load(f)

    raw = base64.b64decode(payload["encrypted"])
    salt, iv, ct_and_tag = raw[:16], raw[16:28], raw[28:]
    ciphertext, tag = ct_and_tag[:-16], ct_and_tag[-16:]

    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000, dklen=32)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    decrypted = cipher.decrypt_and_verify(ciphertext, tag)
    records = json.loads(decrypted)

    return {
        "records": records,
        "deletedIds": [],
        "updatedAt": payload.get("updatedAt", ""),
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    password = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else None

    result = decrypt(input_path, password)
    text = json.dumps(result, ensure_ascii=False, indent=2)

    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        print(f"Wrote {len(result['records'])} records to {output_path}")
    else:
        print(text)


if __name__ == "__main__":
    main()
