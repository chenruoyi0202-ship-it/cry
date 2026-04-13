---
name: github-sync
description: "GitHub token-based multi-device sync for client-side web apps. Stores user data as plain JSON in a private GitHub repo (auto-created via the API), enabling cross-device synchronization with conflict resolution and deletion propagation. Use when building any single-page web app that needs to persist data across devices/browsers without a backend server. Triggers: 'multi-device sync', 'cross-browser data', 'cloud sync', 'GitHub as backend', 'private data sync', 'offline-first PWA sync', '同步', '云端同步', '跨设备'."
---

# GitHub Token-based Multi-Device Sync

A complete client-side sync mechanism that uses a GitHub Personal Access Token + a private repo as the backend. Battle-tested in `migraine.html`. Use it whenever you need a single-page web app to share user data across devices without running a server.

## When to apply

- The app is a **single-page browser app** (HTML+JS, hosted on GitHub Pages or similar static hosting).
- You need data to **survive across devices and browsers** for a single user.
- You **don't want to run a backend** (no Postgres, no Firebase, no Supabase).
- Privacy matters: data must be **only readable by the owner** (no public URLs).
- Data fits comfortably in a single JSON file (under a few MB).

## Architecture (one-liner)

```
[user's device] ⇄ GitHub Contents API ⇄ private repo `${user}/<app>-data` /data/<app>.json
```

- Token is stored only in the device's localStorage.
- The repo is **automatically created as private** on first use.
- Each record has a unique `id` field set to `Date.now()` at creation time. This doubles as a creation timestamp.
- Sync state per device: `lastSyncAt` (ms epoch).

## Core invariants

1. **Single source of truth is the cloud JSON file**, but each device caches a copy locally.
2. **Records are identified by numeric `id` (= creation timestamp)**.
3. **Deletions propagate via two mechanisms** working together:
   - Explicit tombstones (`deletedIds` array in cloud + local).
   - Implicit deletion detection via `lastSyncAt`: if a record exists on one side but not the other AND its `id < lastSyncAt`, it must have been deleted on the missing side after our last sync.
4. **Never push when local is empty AND no tombstones exist** — protects fresh devices from wiping the cloud.

## Implementation steps

When you build a new app that needs sync:

1. Add the sync UI: a single password-style input for the token + 4 buttons (保存配置, 立即同步, 用云端数据覆盖本地, 清除同步配置).
2. Drop in `scripts/sync.js` (see `scripts/`) and adapt the constants at the top:
   - `STORAGE_KEY` – localStorage key for records (e.g. `migraine_records`)
   - `DELETED_KEY` – localStorage key for deletedIds
   - `LAST_SYNC_KEY` – localStorage key for lastSyncAt
   - `CONFIG_KEY` – localStorage key for syncConfig
   - `REPO_NAME` – default private repo name (e.g. `migraine-data`, `journal-data`)
   - `DATA_PATH` – path inside repo (e.g. `data/migraine.json`)
3. Wire up the buttons to `saveSyncConfig()`, `manualSync()`, `forcePullFromCloud()`, `clearSyncConfig()`.
4. Call `pushToCloud()` (via `autoSync()`) after every local mutation (create/edit/delete).
5. Call `manualSync()` once on `DOMContentLoaded` if a token is configured.

## Mandatory pitfalls to avoid

| ⚠ Pitfall | ✓ Correct |
|---|---|
| Pulling without merging tombstones | Always union local and cloud `deletedIds` |
| Pushing immediately after a fresh-device pull with empty local | Skip push if `records.length === 0 && deletedIds.length === 0` |
| Hardcoding the repo name without owner | Always derive owner via `GET /user` API |
| Overwriting cloud SHA mismatch | Catch "does not match" error, refetch SHA, retry once |
| Using `cache: 'default'` on GitHub API fetches | Append `&t=Date.now()` to the branch query for cache-bust |
| Storing the password (encryption was a misfeature) | Just use a private repo — no encryption needed |
| Letting old cached HTML stick around in PWAs | Bump `APP_VERSION`, show it in the footer, and add no-cache meta tags |

## Required GitHub token scopes

A classic Personal Access Token (PAT) with the **`repo`** scope. Fine-grained PATs work too if you grant Contents (read+write) and Administration (write) for the target repo.

## Token UX rules

- Save token to localStorage **before** validation, so a transient network failure doesn't make the user re-type it.
- Pre-fill the input from localStorage on every page load.
- Never display the token after typing — always use `<input type="password">`.

## Migrating legacy encrypted data

If a previous version of the app used AES-GCM encryption with a user-supplied password, you can decrypt the legacy file outside the browser:

```bash
python3 scripts/decrypt-legacy.py <input_encrypted.json> <password> <output_plain.json>
```

Then commit the plain `data/<app>.json` to the private repo so devices pull it on next sync.

## Files in this skill

- `scripts/sync.js` – complete drop-in JS module (functions: `loadSyncConfig`, `saveSyncConfig`, `clearSyncConfig`, `manualSync`, `autoSync`, `forcePullFromCloud`, `pullFromCloud`, `pushToCloud`, plus GitHub API helpers).
- `scripts/decrypt-legacy.py` – CLI tool to decrypt legacy AES-GCM JSON files migrated from older versions.
- `scripts/sync-ui-template.html` – minimal HTML snippet for the sync settings tab.
