import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { createHash } from 'crypto';
import http from 'http';

// --- Config ---
const SYNC_DIR = process.env.SYNC_DIR || '/var/www/cry/sync';
const PORT = process.env.SYNC_PORT || 3001;

if (!existsSync(SYNC_DIR)) mkdirSync(SYNC_DIR, { recursive: true });

function pinHash(pin) {
    return createHash('sha256').update('cry-sync-' + pin).digest('hex').slice(0, 16);
}

function cors(res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

function json(res, status, data) {
    cors(res);
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
}

http.createServer((req, res) => {
    if (req.method === 'OPTIONS') { cors(res); res.writeHead(204); res.end(); return; }
    if (req.method !== 'POST') { json(res, 405, { error: 'POST only' }); return; }

    let body = '';
    req.on('data', c => { body += c; if (body.length > 5e6) req.destroy(); });
    req.on('end', () => {
        try {
            const { pin, data } = JSON.parse(body);
            if (!pin || String(pin).length < 4) {
                json(res, 400, { error: 'PIN required (min 4 chars)' }); return;
            }
            const file = `${SYNC_DIR}/${pinHash(pin)}.json`;

            if (req.url === '/api/cry/pull') {
                const content = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : {};
                json(res, 200, content);

            } else if (req.url === '/api/cry/push') {
                if (!data || typeof data !== 'object') {
                    json(res, 400, { error: 'data required' }); return;
                }
                writeFileSync(file, JSON.stringify(data, null, 2));
                json(res, 200, { ok: true });

            } else {
                json(res, 404, { error: 'not found' });
            }
        } catch (e) {
            console.error('Error:', e.message);
            json(res, 500, { error: 'server error' });
        }
    });
}).listen(PORT, '127.0.0.1', () => {
    console.log(`Cry Sync API listening on 127.0.0.1:${PORT}`);
    console.log(`Data dir: ${SYNC_DIR}`);
});
