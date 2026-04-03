import OSS from 'ali-oss';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';

// --- Config from environment variables ---
const {
  OSS_REGION = 'oss-cn-hangzhou',
  OSS_BUCKET = '',
  ALI_KEY_ID = '',
  ALI_KEY_SECRET = '',
  JWT_SECRET = 'cry-default-secret-change-me'
} = process.env;

const oss = new OSS({
  region: OSS_REGION,
  accessKeyId: ALI_KEY_ID,
  accessKeySecret: ALI_KEY_SECRET,
  bucket: OSS_BUCKET
});

// --- Helpers ---
function cors(resp) {
  resp.setHeader('Access-Control-Allow-Origin', '*');
  resp.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  resp.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization');
}

function json(resp, status, data) {
  cors(resp);
  resp.setStatusCode(status);
  resp.setHeader('Content-Type', 'application/json');
  resp.send(JSON.stringify(data));
}

function parseBody(req) {
  try { return JSON.parse(req.body || '{}'); }
  catch { return {}; }
}

function makeToken(phone) {
  return jwt.sign({ phone }, JWT_SECRET, { expiresIn: '90d' });
}

function verifyToken(req) {
  const auth = req.headers?.authorization || '';
  if (!auth.startsWith('Bearer ')) return null;
  try { return jwt.verify(auth.slice(7), JWT_SECRET); }
  catch { return null; }
}

async function ossGet(key) {
  try {
    const result = await oss.get(key);
    return JSON.parse(result.content.toString());
  } catch (e) {
    if (e.status === 404 || e.code === 'NoSuchKey') return null;
    throw e;
  }
}

async function ossPut(key, data) {
  await oss.put(key, Buffer.from(JSON.stringify(data)));
}

function validatePhone(phone) {
  return /^1[3-9]\d{9}$/.test(phone);
}

// --- Main Handler ---
export async function handler(req, resp) {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    cors(resp);
    resp.setStatusCode(204);
    resp.send('');
    return;
  }

  const path = req.path || req.url || '';
  const method = req.method || 'GET';

  try {
    // POST /register
    if (method === 'POST' && path.endsWith('/register')) {
      const { phone, password } = parseBody(req);
      if (!validatePhone(phone)) return json(resp, 400, { error: '请输入有效的手机号' });
      if (!password || password.length < 6) return json(resp, 400, { error: '密码至少6位' });

      const existing = await ossGet(`users/${phone}.json`);
      if (existing) return json(resp, 409, { error: '该手机号已注册' });

      const passwordHash = bcrypt.hashSync(password, 10);
      await ossPut(`users/${phone}.json`, { phone, passwordHash, createdAt: new Date().toISOString() });

      return json(resp, 200, { token: makeToken(phone), phone });
    }

    // POST /login
    if (method === 'POST' && path.endsWith('/login')) {
      const { phone, password } = parseBody(req);
      if (!phone || !password) return json(resp, 400, { error: '请输入手机号和密码' });

      const user = await ossGet(`users/${phone}.json`);
      if (!user) return json(resp, 401, { error: '手机号未注册' });
      if (!bcrypt.compareSync(password, user.passwordHash)) return json(resp, 401, { error: '密码错误' });

      return json(resp, 200, { token: makeToken(phone), phone });
    }

    // GET /plans
    if (method === 'GET' && path.endsWith('/plans')) {
      const payload = verifyToken(req);
      if (!payload) return json(resp, 401, { error: '请先登录' });

      const plans = await ossGet(`plans/${payload.phone}.json`);
      return json(resp, 200, { plans: plans || {} });
    }

    // POST /plans
    if (method === 'POST' && path.endsWith('/plans')) {
      const payload = verifyToken(req);
      if (!payload) return json(resp, 401, { error: '请先登录' });

      const { plans } = parseBody(req);
      if (!plans || typeof plans !== 'object') return json(resp, 400, { error: '无效的方案数据' });

      await ossPut(`plans/${payload.phone}.json`, plans);
      return json(resp, 200, { success: true });
    }

    // 404
    json(resp, 404, { error: '接口不存在' });

  } catch (e) {
    console.error('Server error:', e);
    json(resp, 500, { error: '服务器内部错误' });
  }
}
