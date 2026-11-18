// 우리집 책 읽어주기 녹음 저장소 (R2)
//  GET/HEAD /a/<20자 hex>.bin?k=<가족 읽기 토큰> : 앱(토큰은 가족 암호로 잠긴 목록 안에만 있음). 받아서 풀어 재생
//
// 요금 안전장치 (R2 무료 한도: 저장 10GB, 쓰기(Class A) 월 100만, 읽기(Class B) 월 1000만)
//  - 저장 9GB를 넘기는 올리기는 거절(507). 쓰기는 한 달 30만 번을 넘으면 거절(429)
//  - 읽기는 가족 토큰이 있어야 하고(남이 주소로 마구 받아 읽기 횟수를 늘릴 수 없음), 받은 파일은 Cloudflare 캐시에 하루 두어 R2를 다시 읽지 않음
//  - 사용량은 버킷 안 _usage.json 에 기록(올리기·지우기 때만 갱신)
//  PUT/DELETE /a/<key>, GET /list : 맥 처리기만. 헤더 X-Sig: <unix초>.<base64 Ed25519 서명>
//    서명 내용 = METHOD \n 경로(쿼리 포함) \n unix초 \n 본문 sha256 hex
const PUB = 'y/rKZ4FQg9SoLkSFSRqpRKZF2+oOv7WslK3GkTN5eFk=';
const KEY_RE = /^[0-9a-f]{20}\.bin$/;
const READ_HASH = '3b736b26c8d6023c6c9b60b6213ae821d265bc278073c636a6fc7a3d693b2666';
const CAP_BYTES = 9e9, CAP_WRITES = 300000;
const USAGE = '_usage.json';
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'Range', 'Access-Control-Max-Age': '86400' };

const b64d = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');

export async function verify(req, body, now = Date.now()) {
  const sig = req.headers.get('X-Sig') || '';
  const dot = sig.indexOf('.');
  if (dot < 1) return false;
  const ts = Number(sig.slice(0, dot));
  if (!Number.isFinite(ts) || Math.abs(now / 1000 - ts) > 300) return false;
  const u = new URL(req.url);
  const digest = hex(await crypto.subtle.digest('SHA-256', body));
  const msg = new TextEncoder().encode(req.method + '\n' + u.pathname + u.search + '\n' + ts + '\n' + digest);
  try {
    const key = await crypto.subtle.importKey('raw', b64d(PUB), { name: 'Ed25519' }, false, ['verify']);
    return await crypto.subtle.verify({ name: 'Ed25519' }, key, b64d(sig.slice(dot + 1)), msg);
  } catch (e) { return false; }
}

async function readOk(k) {
  if (!k) return false;
  return hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(k))) === READ_HASH;
}
async function usage(env) {
  const o = await env.BUCKET.get(USAGE);
  const u = o ? await o.json() : { bytes: 0, objects: 0, month: '', writes: 0 };
  const m = new Date().toISOString().slice(0, 7);
  if (u.month !== m) { u.month = m; u.writes = 0; }
  return u;
}

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'Content-Type': 'application/json' } });

export default {
  async fetch(req, env, ctx) {
    const u = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (u.pathname.startsWith('/a/')) {
      const key = u.pathname.slice(3);
      if (!KEY_RE.test(key)) return new Response('bad key', { status: 400, headers: CORS });
      if (req.method === 'GET' || req.method === 'HEAD') {
        if (!(await readOk(u.searchParams.get('k')))) return new Response('forbidden', { status: 403, headers: CORS });
        const cache = typeof caches !== 'undefined' ? caches.default : null;
        const ck = new Request(u.origin + u.pathname + '?v=' + (u.searchParams.get('v') || ''), { method: 'GET' });
        if (cache && req.method === 'GET') { const hit = await cache.match(ck); if (hit) return hit; }
        const o = req.method === 'HEAD' ? await env.BUCKET.head(key) : await env.BUCKET.get(key);
        if (!o) return new Response('not found', { status: 404, headers: CORS });
        const h = { ...CORS, 'Content-Type': 'application/octet-stream', 'Content-Length': String(o.size),
          'ETag': o.httpEtag, 'Cache-Control': 'public, max-age=86400' };
        const res = new Response(req.method === 'HEAD' ? null : o.body, { headers: h });
        if (cache && req.method === 'GET' && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(ck, res.clone()));
        return res;
      }
      if (req.method === 'PUT' || req.method === 'DELETE') {
        const body = req.method === 'PUT' ? await req.arrayBuffer() : new ArrayBuffer(0);
        if (!(await verify(req, body))) return new Response('forbidden', { status: 403 });
        const us = await usage(env);
        const old = await env.BUCKET.head(key);
        const oldSize = old ? old.size : 0;
        if (req.method === 'DELETE') {
          if (old) { await env.BUCKET.delete(key); us.bytes -= oldSize; us.objects -= 1; us.writes += 1;
            await env.BUCKET.put(USAGE, JSON.stringify(us)); }
          return json({ ok: true, usage: us });
        }
        if (body.byteLength < 13 || body.byteLength > 30e6) return new Response('bad size', { status: 413 });
        if (us.writes + 2 > CAP_WRITES) return json({ error: 'monthly write cap', usage: us }, 429);
        if (us.bytes - oldSize + body.byteLength > CAP_BYTES) return json({ error: 'storage cap', usage: us }, 507);
        await env.BUCKET.put(key, body);
        us.bytes += body.byteLength - oldSize; us.objects += old ? 0 : 1; us.writes += 2;
        await env.BUCKET.put(USAGE, JSON.stringify(us));
        return json({ ok: true, size: body.byteLength, usage: us });
      }
      return new Response('method', { status: 405, headers: CORS });
    }
    if (u.pathname === '/list' && req.method === 'GET') {
      if (!(await verify(req, new ArrayBuffer(0)))) return new Response('forbidden', { status: 403 });
      const r = await env.BUCKET.list({ cursor: u.searchParams.get('cursor') || undefined, limit: 1000 });
      return json({ keys: r.objects.filter(o => o.key !== USAGE).map(o => [o.key, o.size]),
        cursor: r.truncated ? r.cursor : null, usage: u.searchParams.get('cursor') ? undefined : await usage(env) });
    }
    if (u.pathname === '/' ) return new Response('storytime-audio ok', { headers: CORS });
    return new Response('not found', { status: 404 });
  },
};
