// node test/test.mjs  (선택: SIGN_KEY=<Ed25519 PKCS8 PEM 파일> 이면 올바른 서명도 시험)
import worker from '../src/index.js';
import { readFileSync } from 'node:fs';
import { createHash, createPrivateKey, sign } from 'node:crypto';
const store = new Map();
const env = { BUCKET: {
  async get(k) { const v = store.get(k); return v && { size: v.byteLength, httpEtag: '"x"', body: v, json: async () => JSON.parse(new TextDecoder().decode(v)) }; },
  async head(k) { const v = store.get(k); return v && { size: v.byteLength, httpEtag: '"x"' }; },
  async put(k, v) { store.set(k, typeof v === 'string' ? new TextEncoder().encode(v) : new Uint8Array(v)); },
  async delete(k) { store.delete(k); },
  async list() { return { objects: [...store].map(([key, v]) => ({ key, size: v.byteLength })), truncated: false }; },
} };
let fails = 0;
const ok = (c, m) => { if (!c) { fails++; console.log('✗', m); } else console.log('✓', m); };
const B = 'https://x.workers.dev';
const K = '0123456789abcdef0123.bin';
const req = (m, p, body, sig) => new Request(B + p, { method: m, body, headers: sig ? { 'X-Sig': sig } : {} });
function signed(m, p, body = new Uint8Array(0)) {
  const ts = Math.floor(Date.now() / 1000);
  const d = createHash('sha256').update(body).digest('hex');
  const s = sign(null, Buffer.from(`${m}\n${p}\n${ts}\n${d}`), createPrivateKey(readFileSync(process.env.SIGN_KEY)));
  return req(m, p, m === 'PUT' ? body : undefined, ts + '.' + s.toString('base64'));
}
ok((await worker.fetch(req('GET', '/a/' + K), env)).status === 403, 'GET without family token → 403');
const RT = process.env.READ_TOKEN;
if (RT) ok((await worker.fetch(req('GET', '/a/' + K + '?k=' + RT), env)).status === 404, 'missing → 404');
ok((await worker.fetch(req('GET', '/a/BAD.bin'), env)).status === 400, 'bad key → 400');
ok((await worker.fetch(req('PUT', '/a/' + K, new Uint8Array(100)), env)).status === 403, 'unsigned PUT → 403');
ok((await worker.fetch(req('PUT', '/a/' + K, new Uint8Array(100), `${Math.floor(Date.now()/1000)}.AAAA`), env)).status === 403, 'bad sig → 403');
ok((await worker.fetch(req('GET', '/list'), env)).status === 403, 'unsigned list → 403');
ok((await worker.fetch(req('OPTIONS', '/a/' + K), env)).headers.get('Access-Control-Allow-Origin') === '*', 'CORS preflight');
if (process.env.SIGN_KEY) {
  const body = new Uint8Array(500).fill(7);
  const r = await worker.fetch(signed('PUT', '/a/' + K, body), env);
  ok(r.status === 200, 'signed PUT → 200');
  const g = await worker.fetch(req('GET', '/a/' + K + '?k=' + RT), env);
  ok(g.status === 200 && g.headers.get('Access-Control-Allow-Origin') === '*' && (await g.arrayBuffer()).byteLength === 500, 'GET after PUT');
  const l = await (await worker.fetch(signed('GET', '/list'), env)).json();
  ok(l.keys.length === 1 && l.keys[0][1] === 500 && l.usage.bytes === 500, 'signed list + usage');
  ok((await worker.fetch(signed('PUT', '/a/' + K, new Uint8Array(300)), env)).status === 200, 'replace');
  const l2 = await (await worker.fetch(signed('GET', '/list'), env)).json();
  ok(l2.usage.bytes === 300 && l2.usage.objects === 1, 'usage after replace');
  ok((await worker.fetch(signed('DELETE', '/a/' + K), env)).status === 200 && store.size === 1, 'signed DELETE (only usage left)');
  store.set('_usage.json', new TextEncoder().encode(JSON.stringify({bytes: 8.99e9, objects: 1, month: new Date().toISOString().slice(0,7), writes: 0})));
  ok((await worker.fetch(signed('PUT', '/a/' + K, new Uint8Array(20e6)), env)).status === 507, 'storage cap → 507');
}
if (fails) { console.log(fails + ' failed'); process.exit(1); }
console.log('all ok');
