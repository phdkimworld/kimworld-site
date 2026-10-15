// 웹 푸시(RFC 8030 · 암호화 RFC 8291 aes128gcm · 서버 인증 RFC 8292 VAPID). 외부 라이브러리 없이 WebCrypto로.
// 보내는 흐름: 알림이 생기면 push_pending에 한 줄(같은 대상·종류는 모음) → 1분마다 drainPush가 설정을 보고 보낸다.
const enc = new TextEncoder();
export const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const unb64u = (s) => Uint8Array.from(atob(String(s).replace(/-/g, "+").replace(/_/g, "/") + "===".slice((String(s).length + 3) % 4)), (c) => c.charCodeAt(0));
const cat = (...a) => { const n = a.reduce((x, y) => x + y.length, 0), o = new Uint8Array(n); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };

// 푸시 서비스 주소만 받는다(크롬·삼성 인터넷 = FCM, 파이어폭스 = 모질라, 사파리·아이폰 = 애플, 엣지 = 윈도우)
export const PUSH_HOST = /^https:\/\/(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|push\.services\.mozilla\.com|([a-z0-9-]+\.)*push\.apple\.com|([a-z0-9-]+\.)*notify\.windows\.com)\//;

// ---------- 설정 ----------
// 종류별: report(팔로우한 종목·테마 새 리포트) · reply · mention · quote · repost(끔 off / 팔로우한 사람 following / 모두 all)
// like · follow · dm · dmreq(켬 on / 끔 off). pause: 이 시각까지 모두 멈춤. quiet: 방해 금지 시간(이 기기 시간대, 분 단위)
export const PREF_DEFAULT = { report: "on", reply: "all", mention: "all", quote: "all", repost: "all", like: "on", follow: "on", dm: "on", dmreq: "on",
  pause: 0, quiet: false, qFrom: 23 * 60, qTo: 7 * 60, tz: -540 };
const WHO = new Set(["off", "following", "all"]), ONOFF = new Set(["on", "off"]);
export function cleanPrefs(p) {
  const o = { ...PREF_DEFAULT };
  if (!p || typeof p !== "object") return o;
  for (const k of ["reply", "mention", "quote", "repost"]) if (WHO.has(p[k])) o[k] = p[k];
  for (const k of ["report", "like", "follow", "dm", "dmreq"]) if (ONOFF.has(p[k])) o[k] = p[k];
  const num = (v, lo, hi, d) => { v = Math.round(Number(v)); return Number.isFinite(v) && v >= lo && v <= hi ? v : d; };
  o.pause = num(p.pause, 0, 9e15, 0);
  o.quiet = !!p.quiet; o.qFrom = num(p.qFrom, 0, 1439, o.qFrom); o.qTo = num(p.qTo, 0, 1439, o.qTo); o.tz = num(p.tz, -840, 840, o.tz);
  return o;
}
export async function prefsOf(db, uid) {
  const r = await db.prepare("SELECT prefs FROM push_prefs WHERE uid = ?").bind(uid).first();
  let p = null; try { p = r ? JSON.parse(r.prefs) : null; } catch (e) {}
  return cleanPrefs(p);
}
export function inQuiet(pr, now) {
  if (!pr.quiet || pr.qFrom === pr.qTo) return false;
  const m = Math.floor(((now - pr.tz * 60000) % 864e5 + 864e5) % 864e5 / 60000); // 그 기기 시간대의 '지금 몇 분'
  return pr.qFrom < pr.qTo ? m >= pr.qFrom && m < pr.qTo : m >= pr.qFrom || m < pr.qTo;
}

// ---------- 대기열 ----------
// 푸시를 켠 계정만 줄을 남긴다(나머지는 쓰기 없음). 같은 (사람, 종류, 대상)은 한 줄로 모으고 개수만 늘린다
export function queuePush(db, uid, type, ref, slug, fromNick, now) {
  if (!uid) return Promise.resolve();
  return db.prepare(`INSERT INTO push_pending (uid, type, ref, slug, from_nick, n, updated, pushed) SELECT ?, ?, ?, ?, ?, 1, ?, 0 WHERE EXISTS (SELECT 1 FROM push_subs WHERE uid = ?)
    ON CONFLICT(uid, type, ref) DO UPDATE SET n = CASE WHEN pushed >= updated THEN 1 ELSE n + 1 END, from_nick = excluded.from_nick, updated = excluded.updated`)
    .bind(uid, type, String(ref), slug || "", fromNick || "", now, uid).run().catch(() => {});
}

// ---------- 알림 문구 ----------
const shortTitle = (t) => String(t || "").replace(/^.*?(주가|가격) 내러티브와 패턴 투자전략:\s*/, "");
const who = (r) => (r.from_nick || "누군가") + "님" + (r.n > 1 ? " 외 " + (r.n - 1) + "명" : "");
export function pushMessage(r) {
  const g = r.type + ":" + r.ref; // 같은 대상 알림은 기기에서 한 칸을 덮어쓴다
  switch (r.type) {
    case "report": { const m = /^([a-z0-9.]+)-\d{4}-\d{2}/.exec(r.ref); return { t: "새 리포트" + (m ? " · " + m[1].toUpperCase() : ""), b: shortTitle(r.from_nick) || "팔로우한 종목의 새 리포트가 나왔습니다", u: "/r/" + r.ref + "/", g }; }
    case "reply": return { t: who(r) + "이 답글을 달았습니다", b: "내 글에 새 답글", u: "/p/?id=" + r.ref, g };
    case "mention": return { t: (r.from_nick || "누군가") + "님이 나를 언급했습니다", b: "글에서 @로 불렀어요", u: "/p/?id=" + r.ref, g };
    case "quote": return { t: (r.from_nick || "누군가") + "님이 내 글을 인용했습니다", b: "인용한 글 보기", u: "/p/?id=" + r.ref, g };
    case "repost": return { t: who(r) + "이 내 글을 리포스트했습니다", b: "", u: "/p/?id=" + r.ref, g };
    case "like": return { t: "내 글에 새 좋아요" + (r.n > 1 ? " " + r.n + "개" : ""), b: "", u: "/p/?id=" + r.ref, g };
    case "follow": return { t: (r.from_nick || "누군가") + "님이 나를 팔로우했습니다", b: "프로필 보기", u: "/u/?id=" + r.ref, g };
    case "dm": return r.slug === "req"
      ? { t: (r.from_nick || "누군가") + "님의 쪽지 요청", b: "처음 보는 사람이 쪽지를 보냈어요", u: "/dm/?t=" + r.ref, g }
      : { t: (r.from_nick || "누군가") + "님의 쪽지" + (r.n > 1 ? " " + r.n + "개" : ""), b: "새 쪽지가 왔어요", u: "/dm/?t=" + r.ref, g };
    case "test": return { t: "알림이 켜졌어요", b: "팔로우한 종목의 새 리포트와 내 글 소식을 이렇게 알려 드려요", u: "/settings/", g };
    default: return null;
  }
}

// 설정에 따라 보낼지. 'following'은 보낸 사람(닉네임)을 내가 팔로우하는지 본다
export async function allowedPush(db, r, pr, now) {
  if (pr.pause > now || inQuiet(pr, now)) return false;
  const k = r.type === "dm" && r.slug === "req" ? "dmreq" : r.type;
  const v = pr[k];
  if (v === undefined || v === "off") return r.type === "test";
  if (v === "following") {
    const f = await db.prepare("SELECT 1 AS y FROM follows f JOIN users u ON u.id = f.followee WHERE f.follower = ? AND u.nick = ?").bind(r.uid, r.from_nick || "").first();
    return !!f;
  }
  return true;
}

// ---------- VAPID 키: 처음 한 번 만들어 D1에 둔다(비밀값 설정이 필요 없다) ----------
let VK = null;
export async function vapidKeys(db) {
  if (VK) return VK;
  let row = await db.prepare("SELECT v FROM app_keys WHERE k = 'vapid'").first();
  if (!row) {
    const kp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
    const j = await crypto.subtle.exportKey("jwk", kp.privateKey);
    await db.prepare("INSERT OR IGNORE INTO app_keys (k, v) VALUES ('vapid', ?)").bind(JSON.stringify({ d: j.d, x: j.x, y: j.y })).run();
    row = await db.prepare("SELECT v FROM app_keys WHERE k = 'vapid'").first();
  }
  const j = JSON.parse(row.v);
  const priv = await crypto.subtle.importKey("jwk", { kty: "EC", crv: "P-256", d: j.d, x: j.x, y: j.y, ext: true }, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  VK = { priv, pub: b64u(cat(new Uint8Array([4]), unb64u(j.x), unb64u(j.y))), jwt: {} };
  return VK;
}
async function vapidAuth(vk, endpoint, now) {
  const aud = new URL(endpoint).origin;
  const c = vk.jwt[aud];
  if (c && c.exp - 3600 > now / 1000) return c.h;
  const exp = Math.floor(now / 1000) + 12 * 3600;
  const unsigned = b64u(enc.encode(JSON.stringify({ typ: "JWT", alg: "ES256" }))) + "." + b64u(enc.encode(JSON.stringify({ aud, exp, sub: "https://drkimworld.com" })));
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, vk.priv, enc.encode(unsigned));
  const h = `vapid t=${unsigned}.${b64u(sig)}, k=${vk.pub}`;
  vk.jwt[aud] = { h, exp };
  return h;
}

// ---------- 암호화(aes128gcm) ----------
async function hkdf(salt, ikm, info, bytes) {
  const k = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info }, k, bytes * 8));
}
export async function encryptPush(p256dh, authSecret, payload) {
  const uaPub = unb64u(p256dh), auth = unb64u(authSecret);
  const uaKey = await crypto.subtle.importKey("raw", uaPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const eph = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPub = new Uint8Array(await crypto.subtle.exportKey("raw", eph.publicKey));
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, eph.privateKey, 256));
  const ikm = await hkdf(auth, shared, cat(enc.encode("WebPush: info\0"), uaPub, asPub), 32);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, enc.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, ikm, enc.encode("Content-Encoding: nonce\0"), 12);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, cat(enc.encode(payload), new Uint8Array([2]))));
  const head = new Uint8Array(21); head.set(salt, 0); new DataView(head.buffer).setUint32(16, 4096); head[20] = 65;
  return cat(head, asPub, ct);
}
export async function sendPush(db, sub, msg, now) {
  const vk = await vapidKeys(db);
  const body = await encryptPush(sub.p256dh, sub.auth, JSON.stringify(msg));
  let res;
  try {
    res = await fetch(sub.endpoint, { method: "POST", headers: { Authorization: await vapidAuth(vk, sub.endpoint, now), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", TTL: "86400", Urgency: msg.urgent ? "high" : "normal", Topic: String(msg.g || "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32) || undefined }, body });
  } catch (e) { res = { status: 0 }; }
  if (res.status === 404 || res.status === 410) await db.prepare("DELETE FROM push_subs WHERE endpoint = ?").bind(sub.endpoint).run(); // 구독이 끝난 기기
  else if (res.status >= 200 && res.status < 300) await db.prepare("UPDATE push_subs SET last_ok = ?, fails = 0 WHERE endpoint = ?").bind(now, sub.endpoint).run();
  else await db.prepare("UPDATE push_subs SET fails = fails + 1 WHERE endpoint = ?").bind(sub.endpoint).run();
  return res.status;
}
export async function pushToUser(db, uid, msg, now) {
  const subs = (await db.prepare("SELECT endpoint, p256dh, auth FROM push_subs WHERE uid = ? AND fails < 20 LIMIT 10").bind(uid).all()).results || [];
  let ok = 0;
  for (const s of subs) { const st = await sendPush(db, s, msg, now); if (st >= 200 && st < 300) ok++; }
  return { subs: subs.length, ok };
}

// ---------- 1분마다: 대기열 보내기 ----------
// 몰려 오는 종류(좋아요·리포스트·답글·쪽지)는 같은 대상으로 10분에 한 번만 울린다. 그 사이 것은 모아서 다음 알림의 개수로
export async function drainPush(db, now, limit = 25) {
  const rows = (await db.prepare(`SELECT * FROM push_pending WHERE updated > pushed AND (type NOT IN ('like', 'repost', 'reply', 'dm') OR pushed_at <= ?)
    ORDER BY updated LIMIT ?`).bind(now - 10 * 60e3, limit).all()).results || [];
  let sent = 0;
  for (const r of rows) {
    await db.prepare("UPDATE push_pending SET pushed = ?, pushed_at = ? WHERE uid = ? AND type = ? AND ref = ?").bind(r.updated, now, r.uid, r.type, r.ref).run();
    const pr = await prefsOf(db, r.uid);
    if (!(await allowedPush(db, r, pr, now))) continue;
    const msg = pushMessage(r); if (!msg) continue;
    sent += (await pushToUser(db, r.uid, msg, now)).ok;
  }
  if (Math.random() < 0.02) await db.prepare("DELETE FROM push_pending WHERE updated < ? AND pushed >= updated").bind(now - 3 * 864e5).run();
  return { rows: rows.length, sent };
}
