/*
 * GitHub token-based multi-device sync — drop-in module.
 *
 * Adapt the constants in the CONFIG block at the top, then expose the
 * exported functions to your UI buttons. See SKILL.md for full docs.
 *
 * Required globals from the host app:
 *   - records: Array<{id: number, ...}>
 *   - showToast(msg: string, isError?: boolean): void
 *   - renderHistory(): void  // any function that re-renders the list
 */

// ============== CONFIG (edit per app) ==============
const STORAGE_KEY   = 'migraine_records';
const DELETED_KEY   = 'migraine_deleted_ids';
const LAST_SYNC_KEY = 'migraine_last_sync';
const CONFIG_KEY    = 'migraine_sync_config';
const REPO_NAME     = 'migraine-data';      // private repo to auto-create
const DATA_PATH     = 'data/migraine.json'; // path inside the repo
// ====================================================

// State (host app should also reference these)
let deletedIds = [];
let lastSyncAt = 0;
let syncConfig = null;
let fileSha = null;

// ==================== Storage ====================
function loadRecords() {
    try { records = JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
    catch (e) { records = []; }
    try { deletedIds = JSON.parse(localStorage.getItem(DELETED_KEY)) || []; }
    catch (e) { deletedIds = []; }
    lastSyncAt = parseInt(localStorage.getItem(LAST_SYNC_KEY) || '0');
}
function saveRecords() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
    localStorage.setItem(DELETED_KEY, JSON.stringify(deletedIds));
    localStorage.setItem(LAST_SYNC_KEY, String(lastSyncAt));
}
function loadSyncConfig() {
    try { syncConfig = JSON.parse(localStorage.getItem(CONFIG_KEY)); }
    catch (e) { syncConfig = null; }
    if (syncConfig) {
        const tokenInput = document.getElementById('inputToken');
        if (tokenInput) tokenInput.value = syncConfig.token || '';
    }
    updateSyncBar();
}

// ==================== UI helpers ====================
function repoName(r) { return (r || '').split('/').pop(); }
function updateSyncBar() {
    const dot = document.getElementById('syncDot');
    const label = document.getElementById('syncLabel');
    if (!dot || !label) return;
    if (!syncConfig) {
        dot.className = 'sync-dot';
        label.textContent = '未配置同步 - 点击设置';
    } else {
        dot.className = 'sync-dot connected';
        label.textContent = '已连接 · ' + repoName(syncConfig.repo);
    }
}
function setSyncStatus(status, text) {
    const dot = document.getElementById('syncDot');
    const label = document.getElementById('syncLabel');
    if (!dot || !label) return;
    dot.className = 'sync-dot ' + status;
    label.textContent = text;
}

// ==================== Public API ====================
async function saveSyncConfig() {
    const token = document.getElementById('inputToken').value.trim();
    if (!token) { showToast('请填写 Token', true); return; }
    // Save token immediately so it persists even if validation fails
    syncConfig = { token, repo: '' };
    localStorage.setItem(CONFIG_KEY, JSON.stringify(syncConfig));
    setSyncStatus('syncing', '正在验证 Token...');
    try {
        const user = await ghGetUser(token);
        syncConfig.repo = `${user.login}/${REPO_NAME}`;
        await ensureRepo(token, user.login);
        localStorage.setItem(CONFIG_KEY, JSON.stringify(syncConfig));
        updateSyncBar();
        showToast('配置已保存');
        manualSync();
    } catch (e) {
        console.error(e);
        setSyncStatus('error', '配置失败 · 点击重试');
        showToast('配置失败: ' + e.message, true);
    }
}

function clearSyncConfig() {
    if (!confirm('确认清除同步配置？')) return;
    syncConfig = null;
    localStorage.removeItem(CONFIG_KEY);
    fileSha = null;
    const tokenInput = document.getElementById('inputToken');
    if (tokenInput) tokenInput.value = '';
    updateSyncBar();
    showToast('同步配置已清除');
}

async function ensurePrivateRepo() {
    if (!syncConfig.repo || !syncConfig.repo.endsWith('/' + REPO_NAME)) {
        const user = await ghGetUser(syncConfig.token);
        syncConfig.repo = `${user.login}/${REPO_NAME}`;
        syncConfig._branch = null;
        await ensureRepo(syncConfig.token, user.login);
        localStorage.setItem(CONFIG_KEY, JSON.stringify(syncConfig));
    }
}

async function manualSync() {
    if (!syncConfig) { showToast('请先配置同步', true); return; }
    setSyncStatus('syncing', '同步中...');
    try {
        await ensurePrivateRepo();
        await pullFromCloud();
        // Safety: don't push only if both records and tombstones are empty (fresh device)
        if (records.length > 0 || deletedIds.length > 0) {
            await pushToCloud();
        }
        setSyncStatus('connected', '已同步 · ' + repoName(syncConfig.repo));
        showToast(records.length > 0 ? '同步完成' : '已拉取，本地暂无数据');
    } catch (e) {
        console.error('Sync error:', e);
        setSyncStatus('error', '同步失败 · 点击重试');
        showToast('同步失败: ' + e.message, true);
    }
}

async function autoSync() {
    if (!syncConfig) return;
    setSyncStatus('syncing', '同步中...');
    try {
        await ensurePrivateRepo();
        await pushToCloud();
        setSyncStatus('connected', '已同步 · ' + repoName(syncConfig.repo));
    } catch (e) {
        console.error('Auto sync error:', e);
        setSyncStatus('error', '同步失败');
    }
}

async function forcePullFromCloud() {
    if (!syncConfig) { showToast('请先配置同步', true); return; }
    if (!confirm('将丢弃本地数据，使用云端数据覆盖。确定？')) return;
    setSyncStatus('syncing', '正在拉取云端...');
    try {
        await ensurePrivateRepo();
        const branch = await getDefaultBranch();
        const file = await ghGet(syncConfig.token, syncConfig.repo, DATA_PATH, branch);
        if (!file) {
            records = [];
            deletedIds = [];
            lastSyncAt = Date.now();
            saveRecords();
            showToast('云端无数据', true);
            setSyncStatus('connected', '已同步 · ' + repoName(syncConfig.repo));
            return;
        }
        fileSha = file.sha;
        const content = decodeURIComponent(escape(atob(file.content.replace(/\n/g, ''))));
        const parsed = JSON.parse(content);
        records = parsed.records || [];
        deletedIds = parsed.deletedIds || [];
        lastSyncAt = Date.now();
        saveRecords();
        renderHistory();
        setSyncStatus('connected', '已同步 · ' + repoName(syncConfig.repo));
        showToast(`已从云端拉取 ${records.length} 条记录`);
    } catch (e) {
        console.error(e);
        setSyncStatus('error', '拉取失败');
        showToast('拉取失败: ' + e.message, true);
    }
}

// ==================== Sync internals ====================
async function getDefaultBranch() {
    if (!syncConfig._branch) {
        syncConfig._branch = await ghGetDefaultBranch(syncConfig.token, syncConfig.repo);
    }
    return syncConfig._branch;
}

async function pullFromCloud() {
    const branch = await getDefaultBranch();
    const file = await ghGet(syncConfig.token, syncConfig.repo, DATA_PATH, branch);
    if (!file) return;
    fileSha = file.sha;
    const content = decodeURIComponent(escape(atob(file.content.replace(/\n/g, ''))));
    const parsed = JSON.parse(content);
    const cloudRecords = parsed.records || [];
    const cloudDeleted = parsed.deletedIds || [];
    const cloudIds = new Set(cloudRecords.map(r => r.id));

    // 1) Union tombstones from both sides
    const allDeleted = new Set([...deletedIds, ...cloudDeleted]);

    // 2) Implicit deletion: a record in local but not in cloud, with id < lastSyncAt,
    //    means *some other device* deleted it after our last sync.
    if (lastSyncAt > 0) {
        records.forEach(r => {
            if (!cloudIds.has(r.id) && r.id < lastSyncAt) {
                allDeleted.add(r.id);
            }
        });
    }

    // 3) Implicit deletion (other direction): a record in cloud but not in local,
    //    with id < lastSyncAt, means we deleted it locally after our last sync.
    const localIds = new Set(records.map(r => r.id));
    if (lastSyncAt > 0) {
        cloudRecords.forEach(r => {
            if (!localIds.has(r.id) && r.id < lastSyncAt) {
                allDeleted.add(r.id);
            }
        });
    }

    deletedIds = Array.from(allDeleted);
    records = records.filter(r => !allDeleted.has(r.id));
    const localMap = new Map(records.map(r => [r.id, r]));
    cloudRecords.forEach(r => {
        if (!allDeleted.has(r.id) && !localMap.has(r.id)) {
            localMap.set(r.id, r);
        }
    });
    records = Array.from(localMap.values());
    saveRecords();
}

async function pushToCloud() {
    const branch = await getDefaultBranch();
    const content = JSON.stringify({ records, deletedIds, updatedAt: new Date().toISOString() }, null, 2);
    // Cache-bust to avoid stale SHA
    const file = await ghGet(syncConfig.token, syncConfig.repo, DATA_PATH, branch + '&t=' + Date.now());
    fileSha = file ? file.sha : null;
    try {
        const result = await ghPut(syncConfig.token, syncConfig.repo, DATA_PATH, content, fileSha, branch);
        fileSha = result.content.sha;
    } catch (e) {
        if (e.message && e.message.includes('does not match')) {
            const freshFile = await ghGet(syncConfig.token, syncConfig.repo, DATA_PATH, branch + '&t=' + Date.now());
            fileSha = freshFile ? freshFile.sha : null;
            const result = await ghPut(syncConfig.token, syncConfig.repo, DATA_PATH, content, fileSha, branch);
            fileSha = result.content.sha;
        } else {
            throw e;
        }
    }
    lastSyncAt = Date.now();
    saveRecords();
}

// ==================== GitHub API ====================
async function ghGetUser(token) {
    const res = await fetch('https://api.github.com/user', {
        headers: { 'Authorization': `token ${token}`, 'Accept': 'application/vnd.github.v3+json' }
    });
    if (!res.ok) throw new Error('Token 无效或缺少权限');
    return res.json();
}
async function ensureRepo(token, owner) {
    const check = await fetch(`https://api.github.com/repos/${owner}/${REPO_NAME}`, {
        headers: { 'Authorization': `token ${token}`, 'Accept': 'application/vnd.github.v3+json' }
    });
    if (check.ok) return;
    if (check.status !== 404) throw new Error(`检查仓库失败: ${check.status}`);
    const create = await fetch('https://api.github.com/user/repos', {
        method: 'POST',
        headers: { 'Authorization': `token ${token}`, 'Content-Type': 'application/json', 'Accept': 'application/vnd.github.v3+json' },
        body: JSON.stringify({
            name: REPO_NAME,
            description: '自动创建的私有数据仓库',
            private: true,
            auto_init: true
        })
    });
    if (!create.ok) {
        const err = await create.json().catch(() => ({}));
        throw new Error(err.message || '创建仓库失败');
    }
    await new Promise(r => setTimeout(r, 1500));
}
async function ghGetDefaultBranch(token, repo) {
    const res = await fetch(`https://api.github.com/repos/${repo}`, {
        headers: { 'Authorization': `token ${token}`, 'Accept': 'application/vnd.github.v3+json' }
    });
    if (!res.ok) throw new Error('无法获取仓库信息');
    const data = await res.json();
    return data.default_branch;
}
async function ghGet(token, repo, path, branch) {
    const url = `https://api.github.com/repos/${repo}/contents/${path}` + (branch ? `?ref=${branch}` : '');
    const res = await fetch(url, {
        headers: { 'Authorization': `token ${token}`, 'Accept': 'application/vnd.github.v3+json' }
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`GitHub GET failed: ${res.status}`);
    return res.json();
}
async function ghPut(token, repo, path, content, sha, branch) {
    const body = { message: 'Update data', content: btoa(unescape(encodeURIComponent(content))) };
    if (sha) body.sha = sha;
    if (branch) body.branch = branch;
    const res = await fetch(`https://api.github.com/repos/${repo}/contents/${path}`, {
        method: 'PUT',
        headers: { 'Authorization': `token ${token}`, 'Content-Type': 'application/json', 'Accept': 'application/vnd.github.v3+json' },
        body: JSON.stringify(body)
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || `GitHub PUT failed: ${res.status}`);
    }
    return res.json();
}

// ==================== Wire-up notes ====================
// 1. Add deleted-id tracking to your local delete function:
//      function deleteRecord(id) {
//          records = records.filter(r => r.id !== id);
//          if (!deletedIds.includes(id)) deletedIds.push(id);
//          saveRecords();
//          autoSync();
//      }
// 2. Add a sync settings UI (see scripts/sync-ui-template.html).
// 3. On DOMContentLoaded:
//      loadRecords();
//      loadSyncConfig();
//      if (syncConfig) manualSync().catch(() => {});
