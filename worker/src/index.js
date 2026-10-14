// 김박사 월드 API (Cloudflare Worker + D1)
// - 조회수: 같은 사람(해시)·같은 글은 하루 한 번만 센다
// - 댓글: 닉네임만(회원 가입 없음), 링크·연락처·리딩방 유도 문구는 자동 보류, 신고 3건이면 숨김
// - 좋아요·신고: 같은 사람은 댓글마다 한 번
// - 검색어: 하루 한 사람 한 번만 세서 '요즘 찾는 종목'에 쓴다(화면에는 사이트 종목·테마와 맞는 것만 보인다)
// 원래 IP는 저장하지 않는다. 그날의 무작위 값으로 만든 해시만 남기고, 그 무작위 값은 이틀 뒤 지운다.
// 내 댓글·좋아요는 기기에 저장한 무작위 번호(d=)로 구분한다(같은 공용 IP를 쓰는 사람끼리 섞이지 않게).

const ALLOWED_ORIGINS = ["https://drkimworld.com", "https://www.drkimworld.com", "http://localhost:8765"];
const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,60}$/;
const HOLD_PATTERNS = [
  /https?:\/\//i, /www\./i, /\b[a-z0-9-]+\.(com|net|kr|co|io|me|ly|gg)\b/i,
  /01[016789][\s.-]?\d{3,4}[\s.-]?\d{4}/, /\d{2,3}[\s.-]\d{3,4}[\s.-]\d{4}/,
  /(카톡|카카오톡|오픈\s*채팅|오픈톡|텔레그램|텔레|단톡|리딩|vip|브이아이피|문의\s*주세요|연락\s*주세요|수익\s*보장|원금\s*보장|무료\s*추천|종목\s*추천|급등\s*주|상한가\s*종목)/i,
  /@[a-z0-9_]{3,}/i,
];
const LIMITS = { nickMax: 12, bodyMin: 2, bodyMax: 500, perMinute: 2, perDay: 30, minTypingMs: 3000, reportHide: 3, bestMinLikes: 3, bestCount: 3 };

const kstDay = (ms) => new Date(ms + 9 * 3600e3).toISOString().slice(0, 10);

async function sha256hex(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function cors(req) {
  const o = req.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(o) ? o : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

const json = (req, data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...cors(req), ...extra } });

function cleanText(s, max) {
  return String(s ?? "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F​-‏‪-‮⁦-⁩]/g, "")
    .replace(/\r\n?/g, "\n").replace(/\n{3,}/g, "\n\n").trim().slice(0, max);
}

export function needsHold(text) {
  return HOLD_PATTERNS.some((re) => re.test(text));
}

const quoteOf = (c) => (c.q_kind ? { kind: c.q_kind, ref: c.q_ref, text: c.q_text } : null);
function publicComment(c, actor) {
  return { id: c.id, nick: c.nick, body: c.body, likes: c.likes, created: c.created, parent: c.parent_id || null, uid: c.uid || null, pinned: !!c.pinned, mine: !!actor && !!c.did && c.did === actor, quote: quoteOf(c) };
}

async function readJson(req) {
  try {
    const t = await req.text();
    return t.length > 4000 ? {} : JSON.parse(t || "{}");
  } catch {
    return {};
  }
}

// 그날의 무작위 값(pepper). 같은 날 안에서만 같은 IP를 알아본다(중복 조회·도배 막기). 이틀 지난 값은 지운다.
let pepperCache = { day: "", v: "" };
async function dayPepper(db, day) {
  if (pepperCache.day === day) return pepperCache.v;
  const rnd = [...crypto.getRandomValues(new Uint8Array(24))].map((b) => b.toString(16).padStart(2, "0")).join("");
  await db.prepare("INSERT OR IGNORE INTO peppers (day, v) VALUES (?, ?)").bind(day, rnd).run();
  const row = await db.prepare("SELECT v FROM peppers WHERE day = ?").bind(day).first();
  pepperCache = { day, v: row.v };
  return row.v;
}

// 기기 번호: 브라우저가 만든 무작위 값(d=). 형식이 맞을 때만 쓴다
const DEVICE_RE = /^[A-Za-z0-9_-]{22,64}$/;

// 같은 키로 정해진 시간 안에 limit번까지만 허용
async function allow(db, key, limit, ttlMs, now) {
  await db.prepare("INSERT INTO rate (k, n, exp) VALUES (?, 1, ?) ON CONFLICT(k) DO UPDATE SET n = CASE WHEN exp < ? THEN 1 ELSE n + 1 END, exp = CASE WHEN exp < ? THEN excluded.exp ELSE exp END")
    .bind(key, now + ttlMs, now, now).run();
  const r = await db.prepare("SELECT n FROM rate WHERE k = ?").bind(key).first();
  return (r?.n || 0) <= limit;
}

// 종토방: 댓글과 같은 저장소를 쓰고 slug가 "b-티커"인 묶음. 글쓰기는 계정이 있어야 한다
const isBoard = (slug) => slug.startsWith("b-");
const NICK_RE = /^[가-힣A-Za-z0-9_]{2,12}$/;
const ACCOUNT = { nickChangeMs: 14 * 864e5, createPerIpDay: 3, newMs: 864e5, newPostsPerDay: 5, newPostGapMs: 10 * 60e3, followPerDay: 200, bioMax: 80 };

async function userByActor(db, actor) {
  return db.prepare("SELECT id, nick, bio, created, status, nick_changed, av, dm_pref FROM users WHERE actor = ?").bind(actor).first();
}
// 닉네임 규칙: 한글·영문·숫자·_ 2~12자, 운영자·사이트 이름 흉내와 홍보 문구 금지. 문제가 없으면 null
function nickProblem(nick) {
  if (!NICK_RE.test(nick)) return "닉네임은 한글·영문·숫자·_ 2~12자입니다.";
  if (/운영자|관리자|김박사|admin|drkim|kimworld/i.test(nick) || needsHold(nick)) return "쓸 수 없는 닉네임입니다.";
  return null;
}
// 다음에 닉네임을 바꿀 수 있는 시각(가입 직후 정한 닉네임도 14일 뒤부터)
const nickNext = (u) => (u.nick_changed || u.created) + ACCOUNT.nickChangeMs;
// 알림: 같은 대상·종류는 한 줄로 모으고 개수만 늘린다(좋아요 100개 → 알림 1줄)
async function notify(db, uid, type, ref, slug, fromNick, now) {
  if (!uid) return;
  await db.prepare(`INSERT INTO notifs (uid, type, ref, slug, from_nick, n, updated, seen) VALUES (?, ?, ?, ?, ?, 1, ?, 0)
    ON CONFLICT(uid, type, ref) DO UPDATE SET n = CASE WHEN seen = 1 THEN 1 ELSE n + 1 END, from_nick = excluded.from_nick, updated = excluded.updated, seen = 0`)
    .bind(uid, type, String(ref), slug || "", fromNick || "", now).run();
}

// ---------- 멘션(@닉네임): 있는 닉네임만 링크·알림. 있는 닉네임의 @는 홍보 판정에서 뺀다 ----------
const MENTION_RE = /@([가-힣A-Za-z0-9_]{2,12})/g;
async function mentionsOf(db, text) {
  const names = [...new Set([...String(text || "").matchAll(MENTION_RE)].map((m) => m[1].toLowerCase()))].slice(0, 5);
  if (!names.length) return [];
  const r = await db.prepare(`SELECT id, nick_lc FROM users WHERE status = 'ok' AND nick_lc IN (${names.map(() => "?").join(",")})`).bind(...names).all();
  return r.results || [];
}
const stripMentions = (text, known) => { const k = new Set(known.map((u) => u.nick_lc)); return String(text || "").replace(MENTION_RE, (m, n) => (k.has(n.toLowerCase()) ? "" : m)); };

// ---------- 차단 ----------
async function blockedEither(db, x, y) {
  return !!(await db.prepare("SELECT 1 AS y FROM blocks WHERE (blocker = ? AND blocked = ?) OR (blocker = ? AND blocked = ?)").bind(x, y, y, x).first());
}

// ---------- 쪽지(DM): 사기 예방 규칙 ----------
// 주식 커뮤니티 쪽지는 '리딩방'·외부 메신저 유도에 가장 많이 쓰인다. 그래서 링크·연락처·외부 채팅·입금 안내는 보내지 못하게 막는다(이 사이트 주소는 허용).
const DM = { bodyMax: 1000, perHour: 60, perDay: 300, reqPerDay: 10, newMs: 864e5, reportBlock: 3 };
const DM_BLOCK = [
  /https?:\/\//i, /www\./i, /\b[a-z0-9-]+\.(com|net|kr|co|io|me|ly|gg|link|xyz|site|top|app|to)\b/i, /\bt\.me\b/i,
  /01[016789][\s.-]?\d{3,4}[\s.-]?\d{4}/, /\d{2,3}[\s.-]\d{3,4}[\s.-]\d{4}/,
  /(카톡|카카오\s*톡|오픈\s*채팅|오픈\s*톡|텔레\s*그램|텔레방|단톡|리딩\s*방|vip\s*방|브이아이피|수익\s*보장|원금\s*보장|선\s*입금|입금\s*(해|하)|계좌\s*번호|가입비|회비|유료\s*방)/i,
];
function dmProblem(text) {
  const t = String(text || "").replace(/(https?:\/\/)?(www\.)?drkimworld\.com[^\s]*/gi, "");
  return DM_BLOCK.some((re) => re.test(t)) ? "쪽지에는 링크·연락처·외부 채팅방·입금 안내를 보낼 수 없습니다(투자 사기 예방)." : null;
}
const pair = (x, y) => (x < y ? [x, y] : [y, x]);
// 내가 상대에게 쪽지를 보낼 수 있는지. 없으면 이유
async function dmPermission(db, me, other, thread, now) {
  if (!other || other.status !== "ok" || other.id === me.id) return { can: false, reason: "쪽지를 보낼 수 없는 상대입니다." };
  if (me.status !== "ok") return { can: false, reason: "이용이 제한된 계정입니다." };
  if (await blockedEither(db, me.id, other.id)) return { can: false, reason: "쪽지를 보낼 수 없는 상대입니다." };
  const theyFollowMe = !!(await db.prepare("SELECT 1 AS y FROM follows WHERE follower = ? AND followee = ?").bind(other.id, me.id).first());
  if (thread && thread.accepted) return { can: true, theyFollowMe };
  if (thread && thread.starter !== me.id) return { can: true, theyFollowMe, accepting: true }; // 받은 요청에 답하면 수락
  if (!theyFollowMe) {
    if (other.dm_pref === "none") return { can: false, reason: "이 사용자는 쪽지를 받지 않습니다." };
    if (other.dm_pref === "following") return { can: false, reason: "이 사용자는 자신이 팔로우한 사람의 쪽지만 받습니다." };
    if (now - me.created < DM.newMs) return { can: false, reason: "가입 하루 뒤부터 처음 보는 사람에게 쪽지를 보낼 수 있습니다." };
    const rep = await db.prepare("SELECT COUNT(DISTINCT r.by_uid) AS n FROM dm_reports r JOIN dm_msgs m ON m.id = r.mid WHERE m.sender = ? AND r.created > ?").bind(me.id, now - 30 * 864e5).first();
    if ((rep?.n || 0) >= DM.reportBlock) return { can: false, reason: "신고가 많아 처음 보는 사람에게는 쪽지를 보낼 수 없습니다." };
    if (thread) { // 내가 보낸 요청이 아직 수락 전: 한 통만
      const n = await db.prepare("SELECT COUNT(*) AS n FROM dm_msgs WHERE tid = ? AND sender = ? AND status = 'ok'").bind(thread.id, me.id).first();
      if ((n?.n || 0) >= 1) return { can: false, reason: "상대가 요청을 수락하면 더 보낼 수 있습니다.", pending: true };
    }
    return { can: true, request: true, theyFollowMe };
  }
  return { can: true, theyFollowMe };
}
async function dmUnread(db, uid) {
  const r = await db.prepare(`SELECT
      SUM(CASE WHEN last_from != ? AND ((a = ? AND last_id > a_read AND last_id > a_del) OR (b = ? AND last_id > b_read AND last_id > b_del)) AND (accepted = 1 OR starter = ?) THEN 1 ELSE 0 END) AS unread,
      SUM(CASE WHEN accepted = 0 AND starter != ? AND ((a = ? AND last_id > a_del) OR (b = ? AND last_id > b_del)) THEN 1 ELSE 0 END) AS requests
      FROM dm_threads WHERE a = ? OR b = ?`).bind(uid, uid, uid, uid, uid, uid, uid, uid, uid).first();
  return { dmUnread: r?.unread || 0, dmRequests: r?.requests || 0 };
}

// ---------- 프로필 사진: 정사각형 256px webp/jpeg/png, 64KB까지 ----------
const AVATAR_MAX = 64 * 1024;
function imageMime(u8) {
  if (u8.length > 12 && u8[0] === 0x52 && u8[1] === 0x49 && u8[2] === 0x46 && u8[3] === 0x46 && u8[8] === 0x57 && u8[9] === 0x45 && u8[10] === 0x42 && u8[11] === 0x50) return "image/webp";
  if (u8.length > 3 && u8[0] === 0xff && u8[1] === 0xd8 && u8[2] === 0xff) return "image/jpeg";
  if (u8.length > 8 && u8[0] === 0x89 && u8[1] === 0x50 && u8[2] === 0x4e && u8[3] === 0x47) return "image/png";
  return null;
}
function toB64(u8) { let s = ""; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); }
function fromB64(b) { const s = atob(b); const u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let x = 0;
  for (let i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return x === 0;
}

// ---------- 소셜 로그인(구글·카카오). 받는 것은 회원 번호(sub/id)뿐이고, 그 번호도 되돌릴 수 없게 바꿔 저장한다 ----------
const SITE = "https://drkimworld.com";
const SESSION_DAYS = 180;
function providers(env) {
  const p = [];
  if (env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET) p.push("google");
  if (env.KAKAO_REST_KEY) p.push("kakao");
  return p;
}
function cookieOf(req, name) {
  const m = (req.headers.get("Cookie") || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
  return m ? m[1] : "";
}
function randHex(n) { return [...crypto.getRandomValues(new Uint8Array(n))].map((b) => b.toString(16).padStart(2, "0")).join(""); }
function safeReturn(r) { r = String(r || "/"); return /^\/(?!\/)[\w\-./?=&%#~]*$/.test(r) ? r : "/"; }
function redirect(to, extra = {}) { return new Response(null, { status: 302, headers: { Location: to, "Cache-Control": "no-store", ...extra } }); }
function b64urlJson(part) {
  const s = part.replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(decodeURIComponent(escape(atob(s + "===".slice((s.length + 3) % 4)))));
}
async function oauthSubject(provider, code, env, redirectUri) {
  if (provider === "google") {
    const r = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ code, client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET, redirect_uri: redirectUri, grant_type: "authorization_code" }),
    });
    const t = await r.json();
    if (!t.id_token) return null;
    // 토큰 엔드포인트에서 TLS로 직접 받은 id_token이므로 서명 대신 발급자·대상만 확인한다(OIDC 3.1.3.7)
    const pl = b64urlJson(t.id_token.split(".")[1]);
    if (!["accounts.google.com", "https://accounts.google.com"].includes(pl.iss) || pl.aud !== env.GOOGLE_CLIENT_ID || !pl.sub) return null;
    return "google:" + pl.sub;
  }
  if (provider === "kakao") {
    const body = { grant_type: "authorization_code", client_id: env.KAKAO_REST_KEY, redirect_uri: redirectUri, code };
    if (env.KAKAO_CLIENT_SECRET) body.client_secret = env.KAKAO_CLIENT_SECRET;
    const r = await fetch("https://kauth.kakao.com/oauth/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" }, body: new URLSearchParams(body) });
    const t = await r.json();
    if (!t.access_token) return null;
    const u = await (await fetch("https://kapi.kakao.com/v2/user/me", { headers: { Authorization: `Bearer ${t.access_token}` } })).json();
    return u && u.id ? "kakao:" + u.id : null;
  }
  return null;
}

// ---------- 운영자 애널리틱스 집계: 지금 기간과 바로 앞 같은 길이 기간을 함께 계산(증감 비교) ----------
async function analytics(db, now, daysIn) {
  const days = [7, 30, 90].includes(daysIn) ? daysIn : 30;
  const D = (k) => kstDay(now - k * 864e5);
  const since = D(days - 1), prevSince = D(2 * days - 1);
  const dayOf = "date((created + 32400000) / 1000, 'unixepoch')"; // ms → 한국 날짜
  const all = (sql, ...a) => db.prepare(sql).bind(...a).all().then((r) => r.results || []);
  const one = (sql, ...a) => db.prepare(sql).bind(...a).first();
  const [daily, uvDaily, srcDaily, srcs, pages, types, hours, wau, mau, dau, prevPage, prevSrc, prevUv,
    users, signups, prevSignups, posts, postsDaily, likes, follows, searches, ads, queue, topUsers] = await Promise.all([
    all("SELECT day, SUM(pv) AS pv, SUM(secs) AS secs, SUM(mob) AS mob FROM an_page WHERE day >= ? GROUP BY day ORDER BY day", since),
    all("SELECT day, COUNT(*) AS uv FROM an_seen WHERE day >= ? GROUP BY day", since),
    all("SELECT day, SUM(sess) AS sess, SUM(multi) AS multi, SUM(newv) AS newv FROM an_src WHERE day >= ? GROUP BY day", since),
    all("SELECT src, SUM(sess) AS sess, SUM(multi) AS multi, SUM(newv) AS newv FROM an_src WHERE day >= ? GROUP BY src ORDER BY sess DESC LIMIT 20", since),
    all("SELECT path, t, SUM(pv) AS pv, SUM(secs) AS secs, SUM(entries) AS entries, SUM(scroll) AS scroll, SUM(scroll_n) AS scroll_n FROM an_page WHERE day >= ? GROUP BY path ORDER BY pv DESC LIMIT 40", since),
    all("SELECT t, SUM(pv) AS pv, SUM(secs) AS secs, SUM(mob) AS mob FROM an_page WHERE day >= ? GROUP BY t ORDER BY pv DESC", since),
    all("SELECT h, SUM(pv) AS pv FROM an_hour WHERE day >= ? GROUP BY h ORDER BY h", since),
    one("SELECT COUNT(DISTINCT vh) AS n FROM an_seen WHERE day >= ?", D(6)),
    one("SELECT COUNT(DISTINCT vh) AS n FROM an_seen WHERE day >= ?", D(29)),
    one("SELECT COUNT(*) AS n FROM an_seen WHERE day = ?", D(0)),
    one("SELECT SUM(pv) AS pv, SUM(secs) AS secs FROM an_page WHERE day >= ? AND day < ?", prevSince, since),
    one("SELECT SUM(sess) AS sess, SUM(multi) AS multi, SUM(newv) AS newv FROM an_src WHERE day >= ? AND day < ?", prevSince, since),
    one("SELECT COUNT(DISTINCT vh) AS n FROM an_seen WHERE day >= ? AND day < ?", prevSince, since),
    one("SELECT COUNT(*) AS n, SUM(status != 'ok') AS banned FROM users"),
    all(`SELECT ${dayOf} AS day, COUNT(*) AS n FROM users WHERE created >= ? GROUP BY day`, now - days * 864e5),
    one("SELECT COUNT(*) AS n FROM users WHERE created >= ? AND created < ?", now - 2 * days * 864e5, now - days * 864e5),
    one(`SELECT SUM(slug LIKE 'b-%' AND parent_id IS NULL) AS board, SUM(slug LIKE 'b-%' AND parent_id IS NOT NULL) AS replies, SUM(q_kind = 'r' AND parent_id IS NULL) AS report,
         COUNT(DISTINCT uid) AS writers FROM comments WHERE status = 'ok' AND pinned = 0 AND created >= ?`, now - days * 864e5),
    all(`SELECT ${dayOf} AS day, SUM(slug LIKE 'b-%') AS board, SUM(q_kind = 'r' AND parent_id IS NULL) AS report FROM comments WHERE status = 'ok' AND pinned = 0 AND created >= ? GROUP BY day`, now - days * 864e5),
    one("SELECT COUNT(*) AS n FROM post_likes WHERE created >= ?", now - days * 864e5),
    one("SELECT COUNT(*) AS total, SUM(created >= ?) AS recent FROM follows", now - days * 864e5),
    all("SELECT q, SUM(n) AS n FROM searches WHERE day >= ? GROUP BY q ORDER BY n DESC LIMIT 15", since),
    all("SELECT slot, SUM(imps) AS imps, SUM(clicks) AS clicks FROM ad_stats WHERE day >= ? GROUP BY slot ORDER BY imps DESC", since),
    one("SELECT SUM(status = 'held') AS held, SUM(status = 'hidden' AND reviewed = 0) AS hidden FROM comments"),
    all(`SELECT u.id, u.nick, COUNT(c.id) AS posts, COALESCE(SUM(c.likes), 0) AS likes,
         (SELECT COUNT(*) FROM follows f WHERE f.followee = u.id) AS followers
         FROM users u LEFT JOIN comments c ON c.uid = u.id AND c.status = 'ok' AND c.created >= ? WHERE u.status = 'ok'
         GROUP BY u.id ORDER BY posts DESC, likes DESC LIMIT 10`, now - days * 864e5),
  ]);
  // ---- 확장: 앱·행동 이벤트·리텐션·기기·유입 페이지·콘텐츠 성과·수요 신호·광고 추이 ----
  const [appU, appPv, evs, evPrev, evDaily, cohorts, tech, entries, rpages, topics, topicNew, misses, adDaily, rpN, qN] = await Promise.all([
    one("SELECT COUNT(DISTINCT vh) AS n FROM an_seen WHERE app = 1 AND day >= ?", D(29)),
    one("SELECT SUM(app) AS n FROM an_page WHERE day >= ?", since),
    all("SELECT ev, SUM(n) AS n FROM an_event WHERE day >= ? GROUP BY ev", since),
    all("SELECT ev, SUM(n) AS n FROM an_event WHERE day >= ? AND day < ? GROUP BY ev", prevSince, since),
    all("SELECT day, ev, SUM(n) AS n FROM an_event WHERE day >= ? AND ev IN ('installed', 'install_accept', 'login_start', 'share') GROUP BY day, ev", since),
    // 처음 본 날(이 기록이 있는 35일 안에서) 기준 코호트: 다음 날·7일 안에 다시 왔는지
    all(`WITH f AS (SELECT vh, MIN(day) AS fd FROM an_seen GROUP BY vh)
         SELECT f.fd AS day, COUNT(*) AS n,
           SUM(EXISTS(SELECT 1 FROM an_seen s WHERE s.vh = f.vh AND s.day = date(f.fd, '+1 day'))) AS d1,
           SUM(EXISTS(SELECT 1 FROM an_seen s WHERE s.vh = f.vh AND s.day > f.fd AND s.day <= date(f.fd, '+7 day'))) AS d7
         FROM f WHERE f.fd >= ? GROUP BY f.fd ORDER BY f.fd`, D(27)),
    all("SELECT os, br, SUM(pv) AS pv, SUM(sess) AS sess FROM an_tech WHERE day >= ? GROUP BY os, br ORDER BY pv DESC LIMIT 20", since),
    all("SELECT path, src, SUM(n) AS n FROM an_entry WHERE day >= ? GROUP BY path, src ORDER BY n DESC LIMIT 40", since),
    all("SELECT path, SUM(pv) AS pv, SUM(secs) AS secs, SUM(scroll) AS scroll, SUM(scroll_n) AS scroll_n, SUM(entries) AS entries, SUM(app) AS app FROM an_page WHERE day >= ? AND t = 'r' GROUP BY path ORDER BY pv DESC LIMIT 60", since),
    all("SELECT kind, key, COUNT(*) AS n FROM topic_follows GROUP BY kind, key ORDER BY n DESC LIMIT 20"),
    one("SELECT COUNT(*) AS n FROM topic_follows WHERE created >= ?", now - days * 864e5),
    all("SELECT q, SUM(n) AS n FROM search_miss WHERE day >= ? GROUP BY q ORDER BY n DESC LIMIT 20", since),
    all("SELECT day, SUM(imps) AS imps, SUM(clicks) AS clicks FROM ad_stats WHERE day >= ? GROUP BY day", since),
    one("SELECT COUNT(*) AS n FROM reposts WHERE created >= ?", now - days * 864e5),
    one("SELECT COUNT(*) AS n FROM comments WHERE q_kind IS NOT NULL AND status = 'ok' AND created >= ?", now - days * 864e5),
  ]);
  // 리포트별 반응(좋아요·댓글·리포스트)을 페이지 성과에 붙인다
  const rslugs = rpages.map((x) => (x.path.match(/^\/r\/([a-z0-9-]+)\/$/) || [])[1]).filter(Boolean);
  const react = {};
  if (rslugs.length) {
    const qm = rslugs.map(() => "?").join(",");
    const [lk, cm, rp] = await Promise.all([
      all(`SELECT slug, n FROM likes_total WHERE slug IN (${qm})`, ...rslugs),
      all(`SELECT slug, COUNT(*) AS n FROM comments WHERE status = 'ok' AND slug IN (${qm}) GROUP BY slug`, ...rslugs),
      all(`SELECT ref, COUNT(*) AS n FROM reposts WHERE kind = 'r' AND ref IN (${qm}) GROUP BY ref`, ...rslugs),
    ]);
    for (const x of rslugs) react[x] = { likes: 0, comments: 0, reposts: 0 };
    for (const x of lk) react[x.slug].likes = x.n;
    for (const x of cm) react[x.slug].comments = x.n;
    for (const x of rp) react[x.ref].reposts = x.n;
  }
  // ---- 유입 분석(세분화) ----
  const acqCols = "SUM(pv) AS pv, SUM(secs) AS secs, SUM(sess) AS sess, SUM(multi) AS multi, SUM(deep) AS deep, SUM(newv) AS newv, SUM(mob) AS mob, SUM(app) AS app, SUM(engaged) AS engaged";
  const [acCh, acChPrev, acSrc, acSrcPrev, acDaily, acLand, acRef, acCamp, acEv, acDow] = await Promise.all([
    all(`SELECT ch, ${acqCols} FROM an_acq WHERE day >= ? GROUP BY ch ORDER BY sess DESC`, since),
    all(`SELECT ch, ${acqCols} FROM an_acq WHERE day >= ? AND day < ? GROUP BY ch`, prevSince, since),
    all(`SELECT ch, src, ${acqCols} FROM an_acq WHERE day >= ? GROUP BY ch, src ORDER BY sess DESC LIMIT 80`, since),
    all("SELECT src, SUM(sess) AS sess FROM an_acq WHERE day >= ? AND day < ? GROUP BY src", prevSince, since),
    all("SELECT day, ch, SUM(sess) AS sess FROM an_acq WHERE day >= ? GROUP BY day, ch", since),
    all("SELECT path, src, SUM(sess) AS sess, SUM(multi) AS multi, SUM(pv) AS pv, SUM(secs) AS secs FROM an_land WHERE day >= ? GROUP BY path, src HAVING SUM(sess) > 0 ORDER BY sess DESC LIMIT 120", since),
    all("SELECT host, SUM(sess) AS sess FROM an_ref WHERE day >= ? GROUP BY host ORDER BY sess DESC LIMIT 50", since),
    all("SELECT src, med, camp, cont, SUM(sess) AS sess, SUM(pv) AS pv, SUM(secs) AS secs, SUM(multi) AS multi FROM an_camp WHERE day >= ? GROUP BY src, med, camp, cont ORDER BY sess DESC LIMIT 50", since),
    all("SELECT src, ev, SUM(n) AS n FROM an_srcev WHERE day >= ? GROUP BY src, ev", since),
    all("SELECT CAST(strftime('%w', day) AS INTEGER) AS dow, ch, SUM(sess) AS sess FROM an_acq WHERE day >= ? GROUP BY dow, ch", since),
  ]);
  const prevBySrc = Object.fromEntries(acSrcPrev.map((x) => [x.src, x.sess]));
  const evBySrc = {};
  for (const x of acEv) (evBySrc[x.src] = evBySrc[x.src] || {})[x.ev] = x.n;
  const acq = {
    channels: acCh, channelsPrev: acChPrev,
    sources: acSrc.map((x) => ({ ...x, prevSess: prevBySrc[x.src] || 0, ev: evBySrc[x.src] || {} })),
    daily: acDaily, landings: acLand, refs: acRef, campaigns: acCamp, dow: acDow,
  };
  const evMap = (rows) => Object.fromEntries(rows.map((x) => [x.ev, x.n]));
  const ext = {
    app: { users30: appU?.n || 0, pv: appPv?.n || 0 },
    events: evMap(evs), eventsPrev: evMap(evPrev), eventsDaily: evDaily,
    cohorts, tech, entries,
    reports: rpages.map((x) => ({ ...x, slug: (x.path.match(/^\/r\/([a-z0-9-]+)\/$/) || [])[1] || "", ...(react[(x.path.match(/^\/r\/([a-z0-9-]+)\/$/) || [])[1]] || { likes: 0, comments: 0, reposts: 0 }) })),
    topics, topicNew: topicNew?.n || 0, misses, adDaily,
    actions: { reposts: rpN?.n || 0, quotes: qN?.n || 0 },
    acq,
  };
  // 날짜 축을 빈 날 없이 채운다
  const axis = []; for (let k = days - 1; k >= 0; k--) axis.push(D(k));
  const by = (rows) => Object.fromEntries(rows.map((r) => [r.day, r]));
  const dP = by(daily), dU = by(uvDaily), dS = by(srcDaily), dG = by(signups), dC = by(postsDaily);
  const series = axis.map((day) => ({
    day, pv: dP[day]?.pv || 0, secs: dP[day]?.secs || 0, uv: dU[day]?.uv || 0, sess: dS[day]?.sess || 0, multi: dS[day]?.multi || 0,
    newv: dS[day]?.newv || 0, signups: dG[day]?.n || 0, board: dC[day]?.board || 0, report: dC[day]?.report || 0,
  }));
  const sum = (k) => series.reduce((a, x) => a + x[k], 0);
  return {
    days, since, generated: now,
    totals: { pv: sum("pv"), secs: sum("secs"), sess: sum("sess"), multi: sum("multi"), newv: sum("newv"), signups: sum("signups"),
      uv: (await one("SELECT COUNT(DISTINCT vh) AS n FROM an_seen WHERE day >= ?", since))?.n || 0, mob: daily.reduce((a, x) => a + (x.mob || 0), 0) },
    prev: { pv: prevPage?.pv || 0, secs: prevPage?.secs || 0, sess: prevSrc?.sess || 0, multi: prevSrc?.multi || 0, newv: prevSrc?.newv || 0, uv: prevUv?.n || 0, signups: prevSignups?.n || 0 },
    active: { dau: dau?.n || 0, wau: wau?.n || 0, mau: mau?.n || 0 },
    series, sources: srcs, pages, types, hours,
    community: { users: users?.n || 0, banned: users?.banned || 0, board: posts?.board || 0, replies: posts?.replies || 0, report: posts?.report || 0,
      writers: posts?.writers || 0, postLikes: likes?.n || 0, follows: follows?.total || 0, newFollows: follows?.recent || 0, held: queue?.held || 0, hidden: queue?.hidden || 0 },
    topUsers, searches, ads, ...ext,
  };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
    const now = Date.now();
    const ip = req.headers.get("CF-Connecting-IP") || "0.0.0.0";
    const db = env.DB;
    const today = kstDay(now);
    // ih: 그날만 통하는 IP 해시(중복 조회·검색어·도배 막기). actor: 기기 번호 해시(내 댓글·좋아요의 주인)
    const ih = (await sha256hex(`${await dayPepper(db, today)}|${ip}`)).slice(0, 24);
    const dev = url.searchParams.get("d") || "";
    const devActor = DEVICE_RE.test(dev) ? (await sha256hex(`${env.SALT || "dev-salt"}|dev|${dev}`)).slice(0, 24) : `ip-${ih}`;
    // 로그인(세션 쿠키)이 있으면 계정이 주인, 없으면 기기 번호가 주인(익명 리포트 댓글·좋아요)
    const stoken = cookieOf(req, "kw_s");
    let session = null;
    if (/^[0-9a-f]{64}$/.test(stoken)) {
      session = await db.prepare("SELECT th, actor FROM sessions WHERE th = ? AND exp > ?").bind(await sha256hex(stoken), now).first();
    }
    // 세션으로 상태를 바꾸는 요청은 우리 사이트에서 온 것만(다른 사이트가 몰래 보내는 요청 막기)
    if (session && req.method === "POST" && !ALLOWED_ORIGINS.includes(req.headers.get("Origin") || "")) return json(req, { error: "origin" }, 403);
    const actor = session ? session.actor : devActor;
    const clearCookie = "kw_s=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax";
    if (Math.random() < 0.01) {
      await db.batch([
        db.prepare("DELETE FROM peppers WHERE day < ?").bind(kstDay(now - 2 * 864e5)),
        db.prepare("DELETE FROM rate WHERE exp < ?").bind(now),
      ]);
    }
    const p = url.pathname.replace(/\/+$/, "");
    try {
      // ---------- 조회수 ----------
      if (p === "/v1/view" && req.method === "POST") {
        const { slug } = await readJson(req);
        if (!SLUG_RE.test(slug || "")) return json(req, { error: "slug" }, 400);
        const day = kstDay(now);
        const seen = await db.prepare("INSERT OR IGNORE INTO view_seen (day, slug, ih) VALUES (?, ?, ?)").bind(day, slug, ih).run();
        if (seen.meta?.changes) {
          await db.batch([
            db.prepare("INSERT INTO views_total (slug, n) VALUES (?, 1) ON CONFLICT(slug) DO UPDATE SET n = n + 1").bind(slug),
            db.prepare("INSERT INTO views_daily (slug, day, n) VALUES (?, ?, 1) ON CONFLICT(slug, day) DO UPDATE SET n = n + 1").bind(slug, day),
          ]);
          if (Math.random() < 0.02) await db.prepare("DELETE FROM view_seen WHERE day < ?").bind(kstDay(now - 3 * 864e5)).run();
        }
        const row = await db.prepare("SELECT n FROM views_total WHERE slug = ?").bind(slug).first();
        return json(req, { views: row?.n || 0 });
      }
      if (p === "/v1/stats" && req.method === "GET") {
        // 피드 카드용: 조회·좋아요·댓글 수, 내가 좋아요 했는지, 대표 댓글 하나(좋아요 많은 순 → 최신)
        const slugs = (url.searchParams.get("slugs") || "").split(",").filter((s) => SLUG_RE.test(s)).slice(0, 60);
        if (!slugs.length) return json(req, { stats: {} });
        const q = slugs.map(() => "?").join(",");
        const [v, l, c, mine, top, rp, rpMine] = await Promise.all([
          db.prepare(`SELECT slug, n FROM views_total WHERE slug IN (${q})`).bind(...slugs).all(),
          db.prepare(`SELECT slug, n FROM likes_total WHERE slug IN (${q})`).bind(...slugs).all(),
          // 리포트의 '댓글 수' = 그 리포트를 공유·인용한 커뮤니티 글 수
          db.prepare(`SELECT q_ref AS slug, COUNT(*) AS n FROM comments WHERE status = 'ok' AND q_kind = 'r' AND parent_id IS NULL AND q_ref IN (${q}) GROUP BY q_ref`).bind(...slugs).all(),
          db.prepare(`SELECT slug FROM post_likes WHERE ih = ? AND slug IN (${q})`).bind(actor, ...slugs).all(),
          db.prepare(`SELECT slug, id, nick, body, likes, created FROM (SELECT q_ref AS slug, id, nick, body, likes, created,
              ROW_NUMBER() OVER (PARTITION BY q_ref ORDER BY likes DESC, created DESC) AS rn
              FROM comments WHERE status = 'ok' AND q_kind = 'r' AND parent_id IS NULL AND q_ref IN (${q})) WHERE rn = 1`).bind(...slugs).all(),
          db.prepare(`SELECT ref, COUNT(*) AS n FROM reposts WHERE kind = 'r' AND ref IN (${q}) GROUP BY ref`).bind(...slugs).all(),
          session ? db.prepare(`SELECT r.ref FROM reposts r JOIN users u ON u.id = r.uid WHERE u.actor = ? AND r.kind = 'r' AND r.ref IN (${q})`).bind(actor, ...slugs).all() : { results: [] },
        ]);
        const stats = {};
        for (const s of slugs) stats[s] = { views: 0, likes: 0, comments: 0, liked: false, top: null, reposts: 0, reposted: false };
        for (const r of rp.results || []) stats[r.ref].reposts = r.n;
        for (const r of rpMine.results || []) stats[r.ref].reposted = true;
        for (const r of v.results || []) stats[r.slug].views = r.n;
        for (const r of l.results || []) stats[r.slug].likes = r.n;
        for (const r of c.results || []) stats[r.slug].comments = r.n;
        for (const r of mine.results || []) stats[r.slug].liked = true;
        for (const r of top.results || []) stats[r.slug].top = { id: r.id, nick: r.nick, body: r.body.length > 70 ? r.body.slice(0, 70) + "…" : r.body, likes: r.likes, created: r.created };
        return json(req, { stats }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/like" && req.method === "POST") {
        const { slug } = await readJson(req);
        if (!SLUG_RE.test(slug || "")) return json(req, { error: "slug" }, 400);
        if (!(await allow(db, `like|${ih}`, 300, 864e5, now))) return json(req, { error: "rate", message: "잠시 뒤에 다시 눌러 주세요." }, 429);
        const ins = await db.prepare("INSERT OR IGNORE INTO post_likes (slug, ih, created) VALUES (?, ?, ?)").bind(slug, actor, now).run();
        if (ins.meta?.changes) {
          await db.prepare("INSERT INTO likes_total (slug, n) VALUES (?, 1) ON CONFLICT(slug) DO UPDATE SET n = n + 1").bind(slug).run();
        } else { // 한 번 더 누르면 취소
          await db.batch([
            db.prepare("DELETE FROM post_likes WHERE slug = ? AND ih = ?").bind(slug, actor),
            db.prepare("UPDATE likes_total SET n = MAX(n - 1, 0) WHERE slug = ?").bind(slug),
          ]);
        }
        const row = await db.prepare("SELECT n FROM likes_total WHERE slug = ?").bind(slug).first();
        return json(req, { likes: row?.n || 0, liked: !!ins.meta?.changes });
      }
      // 이번 주 가장 오래 읽힌 리포트(실제로 본 시간 합계, 최근 7일). 홈 피드 맨 위 '대표 글'
      if (p === "/v1/popular/read" && req.method === "GET") {
        const r = await db.prepare(`SELECT path, SUM(secs) AS secs, SUM(pv) AS pv FROM an_page WHERE day >= ? AND t = 'r' GROUP BY path
            HAVING SUM(pv) >= 3 ORDER BY secs DESC LIMIT 3`).bind(kstDay(now - 6 * 864e5)).all();
        const items = (r.results || []).map((x) => ({ slug: (x.path.match(/^\/r\/([a-z0-9-]+)\/$/) || [])[1] || "", secs: x.secs, pv: x.pv, avg: x.pv ? Math.round(x.secs / x.pv) : 0 })).filter((x) => x.slug);
        return json(req, { items }, 200, { "Cache-Control": "public, max-age=600" });
      }
      if (p === "/v1/popular" && req.method === "GET") {
        const days = Math.min(30, Math.max(1, parseInt(url.searchParams.get("days") || "7", 10) || 7));
        const limit = Math.min(50, Math.max(1, parseInt(url.searchParams.get("limit") || "5", 10) || 5));
        const since = kstDay(now - (days - 1) * 864e5);
        // today: 오늘(한국 날짜) 조회수. 화면에서 '급상승' 표시에 쓴다
        const r = await db.prepare("SELECT slug, SUM(n) AS n, SUM(CASE WHEN day = ? THEN n ELSE 0 END) AS today FROM views_daily WHERE day >= ? GROUP BY slug ORDER BY n DESC, slug LIMIT ?")
          .bind(kstDay(now), since, limit).all();
        return json(req, { days, items: r.results || [] }, 200, { "Cache-Control": "public, max-age=300" });
      }

      // ---------- 광고 성과(학습용): 페이지를 떠날 때 한 번에 보내는 묶음 ----------
      if (p === "/v1/ad/events" && req.method === "POST") {
        const b = await readJson(req);
        const seg = String(b.seg || "");
        const ev = Array.isArray(b.e) ? b.e.slice(0, 40) : [];
        if (!/^[md]\.[a-z]{1,2}$/.test(seg) || !ev.length) return json(req, { ok: false });
        if (!(await allow(db, `adev|${ih}`, 400, 864e5, now))) return json(req, { ok: false });
        const SLOTS = new Set(["report_mid", "report_products", "report_late", "report_end", "list", "feed_inline", "thread_inline", "rail", "explore", "explore_inline", "profile_inline", "dm_list", "post_detail"]);
        const agg = new Map(); // 한 페이지에서 같은 묶음·자리는 노출 1, 클릭 1까지만(부풀리기 막기)
        for (const x of ev) {
          const g = String(x?.g || ""), slot = String(x?.s || "");
          if (!/^[a-z0-9]{2,40}$/.test(g) || !SLOTS.has(slot)) continue;
          const k = g + "|" + slot, cur = agg.get(k) || { g, slot, i: 0, c: 0 };
          if (x.k === "c") { cur.c = 1; cur.i = 1; } else if (x.k === "i") cur.i = 1;
          agg.set(k, cur);
        }
        const rows = [...agg.values()].slice(0, 12);
        if (Math.random() < 0.002) await db.prepare("DELETE FROM ad_stats WHERE day < ?").bind(kstDay(now - 90 * 864e5)).run(); // 90일 지난 기록 정리
        if (rows.length) {
          await db.batch(rows.map((r) => db.prepare(`INSERT INTO ad_stats (day, g, slot, seg, imps, clicks) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(day, g, slot, seg) DO UPDATE SET imps = imps + excluded.imps, clicks = clicks + excluded.clicks`).bind(today, r.g, r.slot, seg, r.i, r.c)));
        }
        return json(req, { ok: true, n: rows.length });
      }

      // ---------- 방문 통계(운영자 애널리틱스용): 페이지를 떠날 때 한 번. 합계만 저장 ----------
      if (p === "/v1/hit" && req.method === "POST") {
        const b = await readJson(req);
        let path = String(b.p || "/").slice(0, 100).toLowerCase();
        const PATHS = /^\/(|dm\/|r\/[a-z0-9-]{2,60}\/|t\/[a-z0-9.-]{1,12}\/|theme\/[a-z0-9-]{2,40}\/|search\/|u\/|p\/|about\/|disclaimer\/|privacy\/|terms\/|contact\/|admin\/)$/;
        if (!PATHS.test(path)) path = "/(기타)";
        if (path === "/admin/") return json(req, { ok: false });
        const t = path === "/" ? "h" : path.startsWith("/r/") ? "r" : path.startsWith("/t/") ? "t" : path.startsWith("/theme/") ? "th" : path === "/p/" ? "p" : path === "/u/" ? "u" : path === "/search/" ? "s" : "o";
        const src = /^[a-z0-9.-]{1,40}$/.test(String(b.r || "")) ? String(b.r) : "direct";
        const m = b.m ? 1 : 0, n = b.n ? 1 : 0, s = Math.max(1, Math.min(999, parseInt(b.s, 10) || 1)), app = b.app ? 1 : 0;
        const OS = new Set(["ios", "android", "windows", "mac", "linux", "other"]), BR = new Set(["chrome", "safari", "samsung", "edge", "firefox", "kakaotalk", "naver", "youtube", "instagram", "facebook", "whale", "other"]);
        const os = OS.has(b.os) ? b.os : "other", br = BR.has(b.br) ? b.br : "other";
        const EV = new Set(["install_prompt", "install_card", "install_click", "install_accept", "install_dismiss", "installed", "ios_help", "login_start", "compose_open", "post_submit",
          "share", "save", "repost", "quote_open", "quote_submit", "follow_user", "follow_topic", "yt_play", "search", "notif_open", "like",
          "yt_jump_shown", "yt_jump_click", "featured_click",
          "install_bar", "install_inapp", "ic_header", "ic_footer", "ic_bar", "ic_report", "ic_feed", "signup", "dm_send", "dm_open", "avatar_set", "block", "quote_share", "quote_card"]);
        const evs = [...new Set(Array.isArray(b.ev) ? b.ev.slice(0, 30).map(String) : [])].filter((x) => EV.has(x));
        const a = Math.max(0, Math.min(1800, parseInt(b.a, 10) || 0)), sc = Math.max(0, Math.min(100, parseInt(b.sc, 10) || 0));
        if (!(await allow(db, `hit|${ih}`, 3000, 864e5, now))) return json(req, { ok: false });
        const hour = new Date(now + 9 * 3600e3).getUTCHours();
        const q = [
          db.prepare("INSERT INTO an_seen (day, vh, app) VALUES (?, ?, ?) ON CONFLICT(day, vh) DO UPDATE SET app = MAX(app, excluded.app)").bind(today, actor.slice(-16), app),
          db.prepare(`INSERT INTO an_page (day, path, t, pv, secs, mob, entries, scroll, scroll_n, app) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day, path) DO UPDATE SET pv = pv + 1, secs = secs + excluded.secs, mob = mob + excluded.mob, entries = entries + excluded.entries, scroll = scroll + excluded.scroll, scroll_n = scroll_n + excluded.scroll_n, app = app + excluded.app`)
            .bind(today, path, t, a, m, s === 1 ? 1 : 0, sc, sc ? 1 : 0, app),
          db.prepare("INSERT INTO an_tech (day, os, br, pv, sess) VALUES (?, ?, ?, 1, ?) ON CONFLICT(day, os, br) DO UPDATE SET pv = pv + 1, sess = sess + excluded.sess").bind(today, os, br, s === 1 ? 1 : 0),
          db.prepare("INSERT INTO an_hour (day, h, pv) VALUES (?, ?, 1) ON CONFLICT(day, h) DO UPDATE SET pv = pv + 1").bind(today, hour),
        ];
        if (s === 1) q.push(db.prepare("INSERT INTO an_entry (day, path, src, n) VALUES (?, ?, ?, 1) ON CONFLICT(day, path, src) DO UPDATE SET n = n + 1").bind(today, path, src));
        for (const e of evs) q.push(db.prepare("INSERT INTO an_event (day, ev, n) VALUES (?, ?, 1) ON CONFLICT(day, ev) DO UPDATE SET n = n + 1").bind(today, e));
        if (s <= 2) q.push(db.prepare(`INSERT INTO an_src (day, src, sess, multi, newv) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(day, src) DO UPDATE SET sess = sess + excluded.sess, multi = multi + excluded.multi, newv = newv + excluded.newv`)
            .bind(today, src, s === 1 ? 1 : 0, s === 2 ? 1 : 0, s === 1 ? n : 0));
        // ---- 유입 분석(세분화): 채널 > 세부 출처, 랜딩 페이지 × 세부 출처, 리퍼러 도메인, UTM 캠페인, 출처별 전환 ----
        const CH = new Set(["search", "ai", "youtube", "social", "messenger", "community", "referral", "email", "direct", "internal"]);
        const ch = CH.has(b.ch) ? b.ch : "direct";
        const sd = /^[a-z0-9.-]{1,40}$/.test(String(b.sd || "")) ? String(b.sd) : src;
        let lp = String(b.lp || path).slice(0, 100).toLowerCase(); if (!PATHS.test(lp) || lp === "/admin/") lp = "/(기타)";
        const eng = a >= 30 ? 1 : 0;
        q.push(db.prepare(`INSERT INTO an_acq (day, ch, src, pv, secs, sess, multi, deep, newv, mob, app, engaged) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day, ch, src) DO UPDATE SET pv = pv + 1, secs = secs + excluded.secs, sess = sess + excluded.sess, multi = multi + excluded.multi, deep = deep + excluded.deep,
            newv = newv + excluded.newv, mob = mob + excluded.mob, app = app + excluded.app, engaged = engaged + excluded.engaged`)
          .bind(today, ch, sd, a, s === 1 ? 1 : 0, s === 2 ? 1 : 0, s === 3 ? 1 : 0, s === 1 ? n : 0, s === 1 ? m : 0, s === 1 ? app : 0, eng));
        q.push(db.prepare(`INSERT INTO an_land (day, path, src, sess, multi, pv, secs) VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(day, path, src) DO UPDATE SET sess = sess + excluded.sess, multi = multi + excluded.multi, pv = pv + 1, secs = secs + excluded.secs`)
          .bind(today, lp, sd, s === 1 ? 1 : 0, s === 2 ? 1 : 0, a));
        const rh = String(b.rh || "").toLowerCase();
        if (s === 1 && /^[a-z0-9.-]{3,80}$/.test(rh)) q.push(db.prepare("INSERT INTO an_ref (day, host, sess) VALUES (?, ?, 1) ON CONFLICT(day, host) DO UPDATE SET sess = sess + 1").bind(today, rh));
        const U = b.u && typeof b.u === "object" ? b.u : null;
        const ut = (x) => String(x || "").toLowerCase().replace(/[^a-z0-9가-힣_.\-]/g, "").slice(0, 60);
        if (U && (ut(U.s) || ut(U.c))) q.push(db.prepare(`INSERT INTO an_camp (day, src, med, camp, cont, sess, pv, secs, multi) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(day, src, med, camp, cont) DO UPDATE SET sess = sess + excluded.sess, pv = pv + 1, secs = secs + excluded.secs, multi = multi + excluded.multi`)
          .bind(today, ut(U.s) || "-", ut(U.m) || "-", ut(U.c) || "-", ut(U.t) || "-", s === 1 ? 1 : 0, a, s === 2 ? 1 : 0));
        for (const e of evs) q.push(db.prepare("INSERT INTO an_srcev (day, src, ev, n) VALUES (?, ?, ?, 1) ON CONFLICT(day, src, ev) DO UPDATE SET n = n + 1").bind(today, sd, e));
        if (Math.random() < 0.003) q.push(db.prepare("DELETE FROM an_seen WHERE day < ?").bind(kstDay(now - 35 * 864e5)));
        if (Math.random() < 0.001) for (const tb of ["an_ref", "an_land", "an_camp", "an_srcev"]) q.push(db.prepare(`DELETE FROM ${tb} WHERE day < ?`).bind(kstDay(now - 400 * 864e5)));
        await db.batch(q);
        return json(req, { ok: true });
      }

      // ---------- 검색어 ----------
      if (p === "/v1/search" && req.method === "POST") {
        const { q, miss } = await readJson(req);
        const term = cleanText(q, 20).toLowerCase().replace(/\s+/g, " ");
        if (term.length < 2 || needsHold(term)) return json(req, { ok: false });
        if (miss) { // 결과가 없던 검색어: 하루 한 사람 한 번만
          if (await allow(db, `miss|${ih}|${term}`, 1, 864e5, now))
            await db.prepare("INSERT INTO search_miss (day, q, n) VALUES (?, ?, 1) ON CONFLICT(day, q) DO UPDATE SET n = n + 1").bind(kstDay(now), term).run();
          return json(req, { ok: true });
        }
        const day = kstDay(now);
        const seen = await db.prepare("INSERT OR IGNORE INTO search_seen (day, q, ih) VALUES (?, ?, ?)").bind(day, term, ih).run();
        if (seen.meta?.changes) {
          await db.prepare("INSERT INTO searches (day, q, n) VALUES (?, ?, 1) ON CONFLICT(day, q) DO UPDATE SET n = n + 1").bind(day, term).run();
        }
        return json(req, { ok: true });
      }
      if (p === "/v1/trending" && req.method === "GET") {
        const days = Math.min(30, Math.max(1, parseInt(url.searchParams.get("days") || "7", 10) || 7));
        const since = kstDay(now - (days - 1) * 864e5);
        const r = await db.prepare("SELECT q, SUM(n) AS n FROM searches WHERE day >= ? GROUP BY q ORDER BY n DESC LIMIT 40").bind(since).all();
        return json(req, { days, items: r.results || [] }, 200, { "Cache-Control": "public, max-age=300" });
      }

      // ---------- 댓글 ----------
      // 사이트 전체 최근 댓글(게시 상태만). 홈 화면 '최근 댓글'용
      if (p === "/v1/comments/recent" && req.method === "GET") {
        const limit = Math.min(10, Math.max(1, parseInt(url.searchParams.get("limit") || "5", 10) || 5));
        const board = url.searchParams.get("kind") === "board";
        const r = await db.prepare(`SELECT id, slug, nick, body, likes, created, uid FROM comments WHERE status = 'ok' ${board ? "AND slug LIKE 'b-%' AND parent_id IS NULL AND pinned = 0" : ""} ORDER BY created DESC LIMIT ?`).bind(limit).all();
        const items = (r.results || []).map((c) => ({ id: c.id, slug: c.slug, nick: c.nick, uid: c.uid || null, body: c.body.length > 80 ? c.body.slice(0, 80) + "…" : c.body, likes: c.likes, created: c.created }));
        return json(req, { items }, 200, { "Cache-Control": "public, max-age=60" });
      }
      if (p === "/v1/comments" && req.method === "GET") {
        const slug = url.searchParams.get("slug") || "";
        if (!SLUG_RE.test(slug)) return json(req, { error: "slug" }, 400);
        const sort = url.searchParams.get("sort") === "top" ? "likes DESC, created DESC" : "created DESC";
        const list = await db.prepare(`SELECT * FROM comments WHERE slug = ? AND status = 'ok' ORDER BY pinned DESC, ${sort} LIMIT 200`).bind(slug).all();
        const best = await db.prepare("SELECT * FROM comments WHERE slug = ? AND status = 'ok' AND parent_id IS NULL AND pinned = 0 AND likes >= ? ORDER BY likes DESC, created ASC LIMIT ?")
          .bind(slug, LIMITS.bestMinLikes, LIMITS.bestCount).all();
        const liked = await db.prepare("SELECT l.cid FROM comment_likes l JOIN comments c ON c.id = l.cid WHERE c.slug = ? AND l.ih = ?").bind(slug, actor).all();
        return json(req, {
          comments: (list.results || []).map((c) => publicComment(c, actor)),
          best: (best.results || []).map((c) => publicComment(c, actor)),
          liked: (liked.results || []).map((x) => x.cid),
          me: `익명#${actor.slice(-4)}`,
        });
      }
      if (p === "/v1/comments" && req.method === "POST") {
        const b = await readJson(req);
        const slug = b.slug || "";
        if (!SLUG_RE.test(slug)) return json(req, { error: "slug" }, 400);
        // 커뮤니티 하나: 모든 글은 종목 묶음(b-티커)이나 b-talk에 올린다. 리포트 이야기는 리포트를 공유·인용한 커뮤니티 글로
        if (!isBoard(slug)) return json(req, { error: "community", message: "리포트 댓글은 이제 커뮤니티 글로 올립니다. 화면을 새로 고쳐 주세요." }, 400);
        if (b.website) return json(req, { ok: true, status: "held" }); // 로봇이 채우는 숨은 칸
        if (typeof b.t === "number" && b.t < LIMITS.minTypingMs) return json(req, { error: "too_fast", message: "조금 천천히 다시 시도해 주세요." }, 429);
        const body = cleanText(b.body, LIMITS.bodyMax + 1);
        if (body.length < LIMITS.bodyMin) return json(req, { error: "short", message: "두 글자 이상 써 주세요." }, 400);
        if (body.length > LIMITS.bodyMax) return json(req, { error: "long", message: `${LIMITS.bodyMax}자까지 쓸 수 있습니다.` }, 400);
        const me = await userByActor(db, actor);
        if (me && me.status !== "ok") return json(req, { error: "banned", message: "이용이 제한된 계정입니다." }, 403);
        // 종토방·라운지도 로그인 없이(익명) 쓸 수 있다. 익명 글은 기기 기준 도배 제한과 자동 보류 규칙을 그대로 받는다
        let nick = cleanText(b.nick, LIMITS.nickMax).replace(/\s+/g, " ");
        if (!nick || /운영자|관리자|김박사/.test(nick) || needsHold(nick)) nick = `익명#${actor.slice(-4)}`;
        if (me) nick = me.nick; // 계정이 있으면 계정 닉네임으로
        if (me && now - me.created < ACCOUNT.newMs && isBoard(slug)) { // 새 계정은 종토방 글을 천천히
          const nb = await db.prepare("SELECT COUNT(*) AS d, MAX(created) AS last FROM comments WHERE uid = ? AND slug LIKE 'b-%' AND created > ?").bind(me.id, now - 864e5).first();
          if ((nb?.d || 0) >= ACCOUNT.newPostsPerDay || (nb?.last && now - nb.last < ACCOUNT.newPostGapMs))
            return json(req, { error: "rate", message: "새 계정은 10분에 한 번, 하루 5개까지 쓸 수 있습니다." }, 429);
        }
        // 도배 막기: 기기 기준(1분 2개·하루 30개) + 같은 IP 기준은 넉넉하게(통신사 공용 IP는 여러 사람이 함께 쓴다)
        const mine = await db.prepare("SELECT SUM(created > ?) AS m, COUNT(*) AS d FROM comments WHERE did = ? AND created > ?")
          .bind(now - 60e3, actor, now - 864e5).first();
        const sameIp = await db.prepare("SELECT SUM(created > ?) AS m, COUNT(*) AS d FROM comments WHERE ih = ? AND created > ?")
          .bind(now - 60e3, ih, now - 864e5).first();
        if ((mine?.m || 0) >= LIMITS.perMinute || (mine?.d || 0) >= LIMITS.perDay ||
            (sameIp?.m || 0) >= LIMITS.perMinute * 5 || (sameIp?.d || 0) >= LIMITS.perDay * 5)
          return json(req, { error: "rate", message: "잠시 뒤에 다시 써 주세요." }, 429);
        // 답글: 한 단계만. 답글에 단 답글은 원래 댓글 아래로 모은다
        let parent = null, parentUid = null, parentDid = null;
        if (b.parent != null) {
          const pc = await db.prepare("SELECT id, slug, status, parent_id, uid, did FROM comments WHERE id = ?").bind(parseInt(b.parent, 10) || 0).first();
          if (!pc || pc.slug !== slug || pc.status !== "ok") return json(req, { error: "parent", message: "답글을 달 댓글을 찾지 못했습니다." }, 400);
          parent = pc.parent_id || pc.id; parentUid = pc.uid; parentDid = pc.did;
        }
        // 인용: 리포트나 남의 글의 일부(300자까지)를 붙여 새 글로 올린다(답글에는 붙이지 않음)
        let q = null, qTarget = null;
        if (b.quote && !parent) {
          const qt = cleanText(b.quote.text, 301).replace(/\s+/g, " ");
          // 리포트는 문장 없이 통째로 공유할 수도 있다(빈 글자 = 리포트 카드만 붙임)
          const share = b.quote.kind === "r" && qt === "";
          if (!share && (qt.length < 2 || qt.length > 300)) return json(req, { error: "quote", message: "인용할 부분은 2~300자로 골라 주세요." }, 400);
          if (b.quote.kind === "r" && SLUG_RE.test(String(b.quote.ref || "")) && !String(b.quote.ref).startsWith("b-")) q = { kind: "r", ref: String(b.quote.ref), text: qt };
          else if (b.quote.kind === "p") {
            qTarget = await db.prepare("SELECT id, uid, did, slug, body, status FROM comments WHERE id = ?").bind(parseInt(b.quote.ref, 10) || 0).first();
            const norm = (x) => String(x || "").replace(/\s+/g, " ").replace(/…$/, "").trim();
            if (!qTarget || qTarget.status !== "ok" || !isBoard(qTarget.slug) || !norm(qTarget.body).includes(norm(qt)))
              return json(req, { error: "quote", message: "인용할 글을 찾지 못했습니다." }, 400);
            q = { kind: "p", ref: String(qTarget.id), text: qt };
          } else return json(req, { error: "quote" }, 400);
        }
        const known = await mentionsOf(db, body);
        const status = needsHold(stripMentions(body, known)) || (q && needsHold(q.text)) ? "held" : "ok";
        const r = await db.prepare("INSERT INTO comments (slug, nick, body, ih, did, uid, created, status, parent_id, q_kind, q_ref, q_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(slug, nick, body, ih, actor, me ? me.id : null, now, status, parent, q ? q.kind : null, q ? q.ref : null, q ? q.text : null).run();
        if (status === "ok" && parent && parentUid && parentDid !== actor) await notify(db, parentUid, "reply", parent, slug, nick, now);
        if (status === "ok" && qTarget && qTarget.uid && qTarget.did !== actor) await notify(db, qTarget.uid, "quote", r.meta?.last_row_id, slug, nick, now);
        if (status === "ok" && me && known.length) { // @멘션 알림(계정 글만, 나·차단 관계 제외)
          for (const u of known) if (u.id !== me.id && !(await blockedEither(db, me.id, u.id))) await notify(db, u.id, "mention", r.meta?.last_row_id, slug, nick, now);
        }
        return json(req, {
          ok: true, status, id: r.meta?.last_row_id, nick,
          message: status === "held" ? "링크·연락처·홍보로 보이는 내용이 있어 확인 뒤 게시됩니다." : "",
        });
      }
      const m = p.match(/^\/v1\/comments\/(\d+)\/(like|report)$/);
      if (m && req.method === "POST") {
        const cid = parseInt(m[1], 10);
        const c = await db.prepare("SELECT id, did, status FROM comments WHERE id = ?").bind(cid).first();
        if (!c || c.status !== "ok") return json(req, { error: "not_found" }, 404);
        if (m[2] === "like") {
          if (c.did && c.did === actor) return json(req, { error: "own", message: "내 댓글에는 좋아요를 누를 수 없습니다." }, 400);
          if (!(await allow(db, `like|${ih}`, 300, 864e5, now))) return json(req, { error: "rate", message: "잠시 뒤에 다시 눌러 주세요." }, 429);
          const ins = await db.prepare("INSERT OR IGNORE INTO comment_likes (cid, ih) VALUES (?, ?)").bind(cid, actor).run();
          if (ins.meta?.changes) {
            await db.prepare("UPDATE comments SET likes = likes + 1 WHERE id = ?").bind(cid).run();
            const full = await db.prepare("SELECT uid, slug FROM comments WHERE id = ?").bind(cid).first();
            if (full?.uid) await notify(db, full.uid, "like", cid, full.slug, "", now);
          }
          else {
            await db.prepare("DELETE FROM comment_likes WHERE cid = ? AND ih = ?").bind(cid, actor).run(); // 한 번 더 누르면 취소
            await db.prepare("UPDATE comments SET likes = MAX(likes - 1, 0) WHERE id = ?").bind(cid).run();
          }
          const row = await db.prepare("SELECT likes FROM comments WHERE id = ?").bind(cid).first();
          return json(req, { likes: row.likes, liked: !!ins.meta?.changes });
        }
        // 신고로 숨기는 힘이 크므로, 기기 번호를 바꿔도 같은 IP(오늘)에서는 같은 댓글을 한 번만 신고할 수 있다
        const ipOnce = await allow(db, `rep|${cid}|${ih}`, 1, 864e5, now);
        const ins = ipOnce ? await db.prepare("INSERT OR IGNORE INTO comment_reports (cid, ih) VALUES (?, ?)").bind(cid, actor).run() : { meta: { changes: 0 } };
        if (ins.meta?.changes) {
          await db.prepare("UPDATE comments SET reports = reports + 1, status = CASE WHEN reports + 1 >= ? THEN 'hidden' ELSE status END WHERE id = ?")
            .bind(LIMITS.reportHide, cid).run();
        }
        return json(req, { ok: true });
      }
      if (p.startsWith("/v1/comments/") && p.endsWith("/delete") && req.method === "POST") {
        const cid = parseInt(p.split("/")[3], 10);
        const r = await db.prepare("UPDATE comments SET status = 'deleted' WHERE id = ? AND did = ?").bind(cid, actor).run();
        return json(req, { ok: !!r.meta?.changes });
      }

      // ---------- 계정(계정 키) ----------
      // ---------- 로그인 ----------
      const am0 = p.match(/^\/v1\/auth\/(google|kakao)\/(start|callback)$/);
      if (am0 && req.method === "GET") {
        const [, prov, step] = am0;
        if (!providers(env).includes(prov)) return json(req, { error: "provider", message: "이 로그인은 아직 준비 중입니다." }, 404);
        const redirectUri = `${url.origin}/v1/auth/${prov}/callback`;
        if (step === "start") {
          if (!(await allow(db, `login|${ih}`, 30, 3600e3, now))) return json(req, { error: "rate" }, 429);
          const state = randHex(16);
          await db.prepare("INSERT INTO oauth_state (state, provider, ret, exp) VALUES (?, ?, ?, ?)").bind(state, prov, safeReturn(url.searchParams.get("return")), now + 600e3).run();
          const q = prov === "google"
            ? new URLSearchParams({ client_id: env.GOOGLE_CLIENT_ID, redirect_uri: redirectUri, response_type: "code", scope: "openid", state, prompt: "select_account" })
            : new URLSearchParams({ client_id: env.KAKAO_REST_KEY, redirect_uri: redirectUri, response_type: "code", state });
          return redirect((prov === "google" ? "https://accounts.google.com/o/oauth2/v2/auth?" : "https://kauth.kakao.com/oauth/authorize?") + q);
        }
        const st = await db.prepare("SELECT provider, ret, exp FROM oauth_state WHERE state = ?").bind(url.searchParams.get("state") || "").first();
        await db.prepare("DELETE FROM oauth_state WHERE state = ? OR exp < ?").bind(url.searchParams.get("state") || "", now).run();
        const back = (r, flag) => { const [path, hash] = r.split("#"); return `${SITE}${path}${path.includes("?") ? "&" : "?"}login=${flag}${hash ? "#" + hash : ""}`; };
        if (!st || st.provider !== prov || st.exp < now || !url.searchParams.get("code")) return redirect(back("/", "fail"));
        let subject = null;
        try { subject = await oauthSubject(prov, url.searchParams.get("code"), env, redirectUri); } catch { subject = null; }
        if (!subject) return redirect(back(st.ret, "fail"));
        const oActor = "o-" + (await sha256hex(`${env.SALT || "dev-salt"}|oauth|${subject}`)).slice(0, 30);
        const token = randHex(32);
        await db.prepare("INSERT INTO sessions (th, actor, created, exp) VALUES (?, ?, ?, ?)").bind(await sha256hex(token), oActor, now, now + SESSION_DAYS * 864e5).run();
        if (Math.random() < 0.05) await db.prepare("DELETE FROM sessions WHERE exp < ?").bind(now).run();
        return redirect(back(st.ret, "ok"), { "Set-Cookie": `kw_s=${token}; Path=/; Max-Age=${SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax` });
      }
      if (p === "/v1/auth/logout" && req.method === "POST") {
        if (session) await db.prepare("DELETE FROM sessions WHERE th = ?").bind(session.th).run();
        return json(req, { ok: true }, 200, { "Set-Cookie": clearCookie });
      }

      // ---------- 계정 ----------
      if (p === "/v1/me" && req.method === "GET") {
        const me = session ? await userByActor(db, actor) : null;
        const base = { providers: providers(env), loggedIn: !!session };
        if (!me) return json(req, { ...base, user: null }, 200, { "Cache-Control": "no-store" });
        const [un, dmc, bl] = await Promise.all([
          db.prepare("SELECT COUNT(*) AS n FROM notifs WHERE uid = ? AND seen = 0").bind(me.id).first(),
          dmUnread(db, me.id),
          db.prepare("SELECT blocked FROM blocks WHERE blocker = ? LIMIT 500").bind(me.id).all(),
        ]);
        return json(req, { ...base, user: { id: me.id, nick: me.nick, bio: me.bio, created: me.created, status: me.status, nickNext: nickNext(me), av: me.av || 0, dmPref: me.dm_pref || "all" },
          unread: un?.n || 0, ...dmc, blocked: (bl.results || []).map((x) => x.blocked) }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/me" && req.method === "POST") {
        if (!session) return json(req, { error: "login", message: "구글 또는 카카오로 로그인한 뒤 계정을 만들 수 있습니다." }, 401);
        const b = await readJson(req);
        const bio = cleanText(b.bio, ACCOUNT.bioMax + 1).replace(/\s+/g, " ");
        if (bio.length > ACCOUNT.bioMax) return json(req, { error: "bio", message: `소개는 ${ACCOUNT.bioMax}자까지입니다.` }, 400);
        if (bio && needsHold(bio)) return json(req, { error: "bio", message: "소개에는 링크·연락처·홍보 문구를 넣을 수 없습니다." }, 400);
        const me = await userByActor(db, actor);
        if (me) {
          const nn = typeof b.nick === "string" ? b.nick.trim() : "";
          if (nn && nn !== me.nick) { // 닉네임 변경: 14일에 한 번(사칭·혼란 막기)
            if (me.status !== "ok") return json(req, { error: "banned", message: "이용이 제한된 계정입니다." }, 403);
            if (now < nickNext(me)) return json(req, { error: "nick_wait", message: `닉네임은 14일에 한 번 바꿀 수 있습니다. ${kstDay(nickNext(me))}부터 다시 바꿀 수 있습니다.`, nickNext: nickNext(me) }, 429);
            const prob = nickProblem(nn);
            if (prob) return json(req, { error: "nick", message: prob }, 400);
            const up = await db.prepare("UPDATE OR IGNORE users SET nick = ?, nick_lc = ?, nick_changed = ? WHERE id = ?").bind(nn, nn.toLowerCase(), now, me.id).run();
            if (!up.meta?.changes) return json(req, { error: "taken", message: "이미 쓰는 닉네임입니다." }, 409);
            await db.prepare("UPDATE comments SET nick = ? WHERE uid = ?").bind(nn, me.id).run(); // 지난 글의 이름도 함께
          }
          if (["all", "following", "none"].includes(b.dmPref)) await db.prepare("UPDATE users SET dm_pref = ? WHERE id = ?").bind(b.dmPref, me.id).run();
          if (typeof b.bio === "string") await db.prepare("UPDATE users SET bio = ? WHERE id = ?").bind(bio, me.id).run();
          const u = await userByActor(db, actor);
          return json(req, { ok: true, user: { id: u.id, nick: u.nick, bio: u.bio, created: u.created, status: u.status, nickNext: nickNext(u), av: u.av || 0, dmPref: u.dm_pref || "all" } });
        }
        const nick = String(b.nick || "").trim();
        const prob = nickProblem(nick);
        if (prob) return json(req, { error: "nick", message: prob }, 400);
        if (!(await allow(db, `acct|${ih}`, ACCOUNT.createPerIpDay, 864e5, now))) return json(req, { error: "rate", message: "오늘은 이 네트워크에서 더 만들 수 없습니다." }, 429);
        const ins = await db.prepare("INSERT OR IGNORE INTO users (actor, nick, nick_lc, bio, created) VALUES (?, ?, ?, ?, ?)").bind(actor, nick, nick.toLowerCase(), bio, now).run();
        if (!ins.meta?.changes) return json(req, { error: "taken", message: "이미 쓰는 닉네임입니다." }, 409);
        const u = await userByActor(db, actor);
        // 이 기기에서 로그인 전에 쓴 익명 댓글을 계정으로 옮긴다
        if (devActor && !devActor.startsWith("ip-")) await db.prepare("UPDATE comments SET uid = ?, nick = ?, did = ? WHERE did = ? AND uid IS NULL").bind(u.id, nick, actor, devActor).run();
        return json(req, { ok: true, user: u });
      }
      if (p === "/v1/me/delete" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { ok: false });
        const { all } = await readJson(req);
        await db.batch([
          all ? db.prepare("UPDATE comments SET status = 'deleted' WHERE uid = ?").bind(me.id)
              : db.prepare("UPDATE comments SET uid = NULL, did = NULL, nick = '탈퇴한 사용자' WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM follows WHERE follower = ? OR followee = ?").bind(me.id, me.id),
          db.prepare("DELETE FROM reposts WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM topic_follows WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM notifs WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM avatars WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM blocks WHERE blocker = ? OR blocked = ?").bind(me.id, me.id),
          db.prepare("DELETE FROM user_reports WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM dm_reports WHERE mid IN (SELECT m.id FROM dm_msgs m JOIN dm_threads t ON t.id = m.tid WHERE t.a = ? OR t.b = ?)").bind(me.id, me.id),
          db.prepare("DELETE FROM dm_msgs WHERE tid IN (SELECT id FROM dm_threads WHERE a = ? OR b = ?)").bind(me.id, me.id),
          db.prepare("DELETE FROM dm_threads WHERE a = ? OR b = ?").bind(me.id, me.id),
          db.prepare("DELETE FROM users WHERE id = ?").bind(me.id),
          db.prepare("DELETE FROM sessions WHERE actor = ?").bind(actor),
        ]);
        return json(req, { ok: true }, 200, { "Set-Cookie": clearCookie });
      }
      const um = p.match(/^\/v1\/users\/(\d+)$/);
      if (um && req.method === "GET") {
        const u = await db.prepare("SELECT id, nick, bio, created, status, av, dm_pref FROM users WHERE id = ?").bind(parseInt(um[1], 10)).first();
        if (!u || u.status !== "ok") return json(req, { error: "not_found" }, 404);
        const me = await userByActor(db, actor);
        const [st, fr, fg, posts, fol, rps] = await Promise.all([
          db.prepare("SELECT COUNT(*) AS n, COALESCE(SUM(likes), 0) AS likes FROM comments WHERE uid = ? AND status = 'ok'").bind(u.id).first(),
          db.prepare("SELECT COUNT(*) AS n FROM follows WHERE followee = ?").bind(u.id).first(),
          db.prepare("SELECT COUNT(*) AS n FROM follows WHERE follower = ?").bind(u.id).first(),
          db.prepare("SELECT id, slug, body, likes, created, parent_id, q_kind, q_ref, q_text FROM comments WHERE uid = ? AND status = 'ok' ORDER BY created DESC LIMIT 30").bind(u.id).all(),
          me ? db.prepare("SELECT 1 AS y FROM follows WHERE follower = ? AND followee = ?").bind(me.id, u.id).first() : null,
          db.prepare(`SELECT r.kind, r.ref, r.created, c.id AS pid, c.slug, c.nick, c.uid AS puid, c.body FROM reposts r
            LEFT JOIN comments c ON r.kind = 'p' AND c.id = CAST(r.ref AS INTEGER) AND c.status = 'ok'
            WHERE r.uid = ? ORDER BY r.created DESC LIMIT 30`).bind(u.id).all(),
        ]);
        return json(req, {
          user: { id: u.id, nick: u.nick, bio: u.bio, created: u.created, av: u.av || 0 },
          stats: { posts: st?.n || 0, likes: st?.likes || 0, followers: fr?.n || 0, following: fg?.n || 0 },
          following: !!fol, self: !!me && me.id === u.id,
          followsMe: me ? !!(await db.prepare("SELECT 1 AS y FROM follows WHERE follower = ? AND followee = ?").bind(u.id, me.id).first()) : false,
          blocked: me ? !!(await db.prepare("SELECT 1 AS y FROM blocks WHERE blocker = ? AND blocked = ?").bind(me.id, u.id).first()) : false,
          items: (posts.results || []).map((c) => ({ id: c.id, slug: c.slug, body: c.body, likes: c.likes, created: c.created, reply: !!c.parent_id, quote: quoteOf(c) })),
          reposts: (rps.results || []).filter((x) => x.kind === "r" || x.pid).map((x) => x.kind === "r" ? { kind: "r", slug: x.ref, at: x.created }
            : { kind: "p", at: x.created, post: { id: x.pid, slug: x.slug, nick: x.nick, uid: x.puid || null, body: x.body } }),
        }, 200, { "Cache-Control": "no-store" });
      }
      // 리포스트(다시 올리기): 계정이 있어야 한다. 같은 것을 다시 누르면 취소
      if (p === "/v1/repost" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me || me.status !== "ok") return json(req, { error: "account", message: "로그인하면 리포스트할 수 있습니다." }, 401);
        const { kind, ref } = await readJson(req);
        let key = "", target = null;
        if (kind === "r" && SLUG_RE.test(String(ref || "")) && !String(ref).startsWith("b-")) key = String(ref);
        else if (kind === "p") {
          target = await db.prepare("SELECT id, uid, slug, status, parent_id, pinned FROM comments WHERE id = ?").bind(parseInt(ref, 10) || 0).first();
          if (!target || target.status !== "ok" || target.parent_id || target.pinned || !isBoard(target.slug)) return json(req, { error: "target", message: "리포스트할 수 없는 글입니다." }, 400);
          if (target.uid === me.id) return json(req, { error: "own", message: "내 글은 리포스트할 수 없습니다." }, 400);
          key = String(target.id);
        } else return json(req, { error: "target" }, 400);
        const ins = await db.prepare("INSERT OR IGNORE INTO reposts (uid, kind, ref, created) VALUES (?, ?, ?, ?)").bind(me.id, kind, key, now).run();
        if (ins.meta?.changes) {
          if (!(await allow(db, `repost|${me.id}`, 100, 864e5, now))) {
            await db.prepare("DELETE FROM reposts WHERE uid = ? AND kind = ? AND ref = ?").bind(me.id, kind, key).run();
            return json(req, { error: "rate", message: "오늘은 더 리포스트할 수 없습니다." }, 429);
          }
          if (target && target.uid) await notify(db, target.uid, "repost", target.id, target.slug, me.nick, now);
        } else await db.prepare("DELETE FROM reposts WHERE uid = ? AND kind = ? AND ref = ?").bind(me.id, kind, key).run();
        const n = await db.prepare("SELECT COUNT(*) AS n FROM reposts WHERE kind = ? AND ref = ?").bind(kind, key).first();
        return json(req, { reposted: !!ins.meta?.changes, count: n?.n || 0 });
      }
      // ---------- 종목·테마 팔로우 ----------
      const TOPIC_RE = { t: /^[A-Z0-9.]{1,10}$/, th: /^[a-z0-9-]{2,40}$/ };
      if (p === "/v1/topics" && req.method === "GET") { // 내가 팔로우한 종목·테마
        const me = await userByActor(db, actor);
        if (!me) return json(req, { items: [] }, 200, { "Cache-Control": "no-store" });
        const r = await db.prepare("SELECT kind, key, created FROM topic_follows WHERE uid = ? ORDER BY created DESC LIMIT 200").bind(me.id).all();
        return json(req, { items: r.results || [] }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/topics" && req.method === "POST") { // 팔로우 / 다시 누르면 취소
        const me = await userByActor(db, actor);
        if (!me || me.status !== "ok") return json(req, { error: "account", message: "로그인하면 종목·테마를 팔로우할 수 있습니다." }, 401);
        const { kind, key } = await readJson(req);
        if (!TOPIC_RE[kind] || !TOPIC_RE[kind].test(String(key || ""))) return json(req, { error: "topic" }, 400);
        const ins = await db.prepare("INSERT OR IGNORE INTO topic_follows (uid, kind, key, created) SELECT ?, ?, ?, ? WHERE (SELECT COUNT(*) FROM topic_follows WHERE uid = ?) < 200")
          .bind(me.id, kind, key, now, me.id).run();
        if (!ins.meta?.changes) {
          const del = await db.prepare("DELETE FROM topic_follows WHERE uid = ? AND kind = ? AND key = ?").bind(me.id, kind, key).run();
          if (!del.meta?.changes) return json(req, { error: "limit", message: "종목·테마는 200개까지 팔로우할 수 있습니다." }, 429);
        }
        const n = await db.prepare("SELECT COUNT(*) AS n FROM topic_follows WHERE kind = ? AND key = ?").bind(kind, key).first();
        return json(req, { following: !!ins.meta?.changes, followers: n?.n || 0 });
      }
      if (p === "/v1/topics/stats" && req.method === "GET") { // 여러 종목·테마의 팔로워 수와 내가 팔로우했는지. keys=t:PLTR,th:quantum
        const keys = (url.searchParams.get("keys") || "").split(",").map((x) => x.split(":")).filter(([k, v]) => TOPIC_RE[k] && TOPIC_RE[k].test(v || "")).slice(0, 40);
        const out = {};
        if (keys.length) {
          const me = await userByActor(db, actor);
          const cond = keys.map(() => "(kind = ? AND key = ?)").join(" OR "), args = keys.flat();
          const [cnt, mine] = await Promise.all([
            db.prepare(`SELECT kind, key, COUNT(*) AS n FROM topic_follows WHERE ${cond} GROUP BY kind, key`).bind(...args).all(),
            me ? db.prepare(`SELECT kind, key FROM topic_follows WHERE uid = ? AND (${cond})`).bind(me.id, ...args).all() : { results: [] },
          ]);
          for (const [k, v] of keys) out[k + ":" + v] = { followers: 0, following: false };
          for (const r of cnt.results || []) out[r.kind + ":" + r.key].followers = r.n;
          for (const r of mine.results || []) out[r.kind + ":" + r.key].following = true;
        }
        return json(req, { stats: out }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/follow" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me || me.status !== "ok") return json(req, { error: "account", message: "계정을 만든 뒤 팔로우할 수 있습니다." }, 401);
        const { uid } = await readJson(req);
        const target = await db.prepare("SELECT id, status FROM users WHERE id = ?").bind(parseInt(uid, 10) || 0).first();
        if (!target || target.status !== "ok" || target.id === me.id) return json(req, { error: "target" }, 400);
        if (await blockedEither(db, me.id, target.id)) return json(req, { error: "blocked", message: "차단 관계에서는 팔로우할 수 없습니다." }, 403);
        const ins = await db.prepare("INSERT OR IGNORE INTO follows (follower, followee, created) VALUES (?, ?, ?)").bind(me.id, target.id, now).run();
        if (ins.meta?.changes) {
          if (!(await allow(db, `follow|${me.id}`, ACCOUNT.followPerDay, 864e5, now))) {
            await db.prepare("DELETE FROM follows WHERE follower = ? AND followee = ?").bind(me.id, target.id).run();
            return json(req, { error: "rate", message: "오늘은 더 팔로우할 수 없습니다." }, 429);
          }
          await notify(db, target.id, "follow", me.id, "", me.nick, now);
        } else await db.prepare("DELETE FROM follows WHERE follower = ? AND followee = ?").bind(me.id, target.id).run();
        const fr = await db.prepare("SELECT COUNT(*) AS n FROM follows WHERE followee = ?").bind(target.id).first();
        return json(req, { following: !!ins.meta?.changes, followers: fr?.n || 0 });
      }
      if (p === "/v1/feed/following" && req.method === "GET") {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { items: [] }, 200, { "Cache-Control": "no-store" });
        const r = await db.prepare(`SELECT c.id, c.slug, c.nick, c.uid, c.body, c.likes, c.created FROM comments c JOIN follows f ON f.followee = c.uid
          WHERE f.follower = ? AND c.status = 'ok' ORDER BY c.created DESC LIMIT 30`).bind(me.id).all();
        return json(req, { items: (r.results || []).map((c) => ({ ...c, body: c.body.length > 120 ? c.body.slice(0, 120) + "…" : c.body })) }, 200, { "Cache-Control": "no-store" });
      }
      // ---------- 홈 피드(쓰레드·트위터식): 종토방·라운지의 원글. tab=all(모두) | following(내가 팔로우한 사람 + 나) ----------
      if ((p === "/v1/feed" || p === "/v1/feed/new") && req.method === "GET") {
        const following = url.searchParams.get("tab") === "following";
        const me = await userByActor(db, actor);
        if (following && !me) return json(req, p === "/v1/feed" ? { items: [], more: false } : { n: 0 }, 200, { "Cache-Control": "no-store" });
        // 팔로잉 탭: 팔로우한 사람 + 나 + 팔로우한 종목·테마의 종토방(화면이 boards=b-pltr,b-ionq로 알려 줌)
        const boards = following ? (url.searchParams.get("boards") || "").split(",").filter((x) => /^b-[a-z0-9.-]{1,12}$/.test(x)).slice(0, 80) : [];
        let where = `c.slug LIKE 'b-%' AND c.parent_id IS NULL AND c.pinned = 0 AND c.status = 'ok'` +
          (following ? ` AND (c.uid = ? OR c.uid IN (SELECT followee FROM follows WHERE follower = ?)${boards.length ? ` OR c.slug IN (${boards.map(() => "?").join(",")})` : ""})` : "");
        const fb = following ? [me.id, me.id, ...boards] : [];
        // 범위: board=b-티커(그 종목 커뮤니티 글) · about=리포트 주소(그 리포트를 공유·인용한 글)
        const scopeBoard = (url.searchParams.get("board") || "").toLowerCase();
        const scopeAbout = url.searchParams.get("about") || "";
        let scoped = false;
        if (!following && /^b-[a-z0-9.-]{1,12}$/.test(scopeBoard)) { where += " AND c.slug = ?"; fb.push(scopeBoard); scoped = true; }
        if (!following && SLUG_RE.test(scopeAbout) && !isBoard(scopeAbout)) { where += " AND c.q_kind = 'r' AND c.q_ref = ?"; fb.push(scopeAbout); scoped = true; }
        if (p === "/v1/feed/new") { // 새 글 알림 줄: 이 시각 뒤에 올라온 글 수(최대 99)
          const since = Math.max(0, parseInt(url.searchParams.get("since") || String(now), 10) || 0);
          const r = await db.prepare(`SELECT COUNT(*) AS n FROM (SELECT 1 FROM comments c WHERE ${where} AND c.created > ? AND (c.did IS NULL OR c.did != ?) LIMIT 99)`).bind(...fb, since, actor).first();
          return json(req, { n: r?.n || 0 }, 200, { "Cache-Control": "no-store" });
        }
        const limit = Math.min(30, Math.max(1, parseInt(url.searchParams.get("limit") || "20", 10) || 20));
        const cols = `c.id, c.slug, c.nick, c.uid, c.body, c.likes, c.created, c.did, c.q_kind, c.q_ref, c.q_text,
            (SELECT COUNT(*) FROM comments x WHERE x.parent_id = c.id AND x.status = 'ok') AS replies,
            EXISTS(SELECT 1 FROM comment_likes l WHERE l.cid = c.id AND l.ih = ?) AS liked,
            (SELECT COUNT(*) FROM reposts rp WHERE rp.kind = 'p' AND rp.ref = CAST(c.id AS TEXT)) AS reposts,
            EXISTS(SELECT 1 FROM reposts rq WHERE rq.kind = 'p' AND rq.ref = CAST(c.id AS TEXT) AND rq.uid = ?) AS reposted`;
        let rows = null, more = false, usedHot = false;
        // ---- 하나의 피드(tab=mix): 추천과 팔로잉을 한 줄로 섞는다 ----
        // 점수 = 반응 × 나와의 관계 × 신선도(팔로우한 사람 +3, 팔로우한 종목·테마 +0.8, 최근 반응한 사람 +0.7, 나를 팔로우한 사람 +0.4). 반응은 로그(인기 글이 끝없이 위에 머물지 않게), 관계는 팔로우한 사람·종목·테마,
        // 최근 내가 좋아요·답글한 사람, 나를 팔로우한 사람. 팔로우한 사람의 글은 더 천천히 식는다. 고른 뒤 같은 사람·같은 종토방이 몰리지 않게 펼친다.
        if (url.searchParams.get("tab") === "mix" && !scoped) {
          const off = Math.max(0, Math.min(300, parseInt(url.searchParams.get("offset") || "0", 10) || 0));
          const mixBoards = (url.searchParams.get("boards") || "").split(",").filter((x) => /^b-[a-z0-9.-]{1,12}$/.test(x)).slice(0, 80);
          const mid = me ? me.id : 0;
          const [cand, fol, fme, inter, blk] = await Promise.all([
            db.prepare(`SELECT ${cols} FROM comments c WHERE c.slug LIKE 'b-%' AND c.parent_id IS NULL AND c.pinned = 0 AND c.status = 'ok'
                AND (c.created > ? OR (c.uid IS NOT NULL AND c.uid IN (SELECT followee FROM follows WHERE follower = ?) AND c.created > ?)) ORDER BY c.created DESC LIMIT 400`)
              .bind(actor, mid, now - 14 * 864e5, mid, now - 30 * 864e5).all(),
            me ? db.prepare("SELECT followee AS id FROM follows WHERE follower = ?").bind(mid).all() : { results: [] },
            me ? db.prepare("SELECT follower AS id FROM follows WHERE followee = ?").bind(mid).all() : { results: [] },
            // 최근 30일 내가 좋아요·답글한 사람(관심의 신호)
            db.prepare(`SELECT DISTINCT c.uid AS id FROM comment_likes l JOIN comments c ON c.id = l.cid WHERE l.ih = ? AND c.uid IS NOT NULL
                UNION SELECT DISTINCT p2.uid FROM comments r JOIN comments p2 ON p2.id = r.parent_id WHERE r.did = ? AND r.created > ? AND p2.uid IS NOT NULL`).bind(actor, actor, now - 30 * 864e5).all(),
            me ? db.prepare("SELECT blocked AS id FROM blocks WHERE blocker = ? UNION SELECT blocker FROM blocks WHERE blocked = ?").bind(mid, mid).all() : { results: [] },
          ]);
          const setOf = (r) => new Set((r.results || []).map((x) => x.id));
          const F = setOf(fol), FM = setOf(fme), I = setOf(inter), B = setOf(blk), TB = new Set(mixBoards);
          const scoreOf = (c) => {
            if (c.uid && B.has(c.uid)) return -1;
            const h = Math.max(0, (now - c.created) / 3600e3);
            const eng = 1 + Math.log1p(c.likes + 2 * c.replies + 3 * (c.reposts || 0));
            const followed = !!c.uid && F.has(c.uid);
            let aff = 1;
            if (followed) aff += 3;
            if (TB.has(c.slug)) aff += 0.8;
            if (c.uid && I.has(c.uid)) aff += 0.7;
            if (c.uid && FM.has(c.uid)) aff += 0.4;
            const mine = !!c.did && c.did === actor;
            if (mine) aff = h < 1 ? 6 : 0.6;          // 방금 쓴 내 글은 맨 위, 지난 내 글은 덜
            if (c.liked) aff *= 0.6;                  // 이미 좋아요한 글은 본 글로 보고 조금 내린다
            return eng * aff / Math.pow(h + 2, followed ? 1.1 : 1.35);
          };
          const scored = (cand.results || []).map((c) => ({ c, s: scoreOf(c) })).filter((x) => x.s >= 0).sort((a, b) => b.s - a.s);
          // 펼치기: 매번 남은 글 중 '점수 × 몰림 벌점'이 가장 큰 글을 고른다(최근 3개에 같은 사람 ×0.35, 최근 2개에 같은 종토방 ×0.7)
          const out = [], pool = scored.slice(0, 300);
          while (pool.length && out.length < off + limit + 1) {
            let bi = 0, bv = -1;
            for (let i = 0; i < Math.min(pool.length, 40); i++) {
              const x = pool[i].c; let v = pool[i].s;
              if (out.slice(-3).some((y) => (y.uid || y.did) === (x.uid || x.did))) v *= 0.35;
              if (out.slice(-2).some((y) => y.slug === x.slug)) v *= 0.7;
              if (v > bv) { bv = v; bi = i; }
            }
            out.push(pool.splice(bi, 1)[0].c);
          }
          if (out.length) { rows = out.slice(off, off + limit); more = out.length > off + limit || pool.length > 0; usedHot = true; }
          else rows = [];
        }
        // 추천 탭(rank=hot): 최근 7일 글을 반응(좋아요·답글)과 신선도로 줄 세운다(쓰레드 '추천'처럼). 7일 안 글이 없으면 최신순
        const hot = !following && url.searchParams.get("rank") === "hot";
        if (hot) {
          const off = Math.max(0, Math.min(300, parseInt(url.searchParams.get("offset") || "0", 10) || 0));
          const r = await db.prepare(`SELECT ${cols} FROM comments c WHERE ${where} AND c.created > ? ORDER BY c.created DESC LIMIT 300`).bind(actor, me ? me.id : 0, ...fb, now - 7 * 864e5).all();
          const scored = (r.results || []).map((c) => ({ c, s: (c.likes + 2 * c.replies + 1) / Math.pow((now - c.created) / 3600e3 + 2, 1.5) }))
            .sort((a, b) => b.s - a.s).map((x) => x.c);
          if (scored.length) { rows = scored.slice(off, off + limit); more = scored.length > off + limit; usedHot = true; }
        }
        if (!rows) {
          const before = parseInt(url.searchParams.get("before") || "0", 10) || now + 1;
          const r = await db.prepare(`SELECT ${cols} FROM comments c WHERE ${where} AND c.created < ? ORDER BY c.created DESC LIMIT ?`).bind(actor, me ? me.id : 0, ...fb, before, limit + 1).all();
          const all = r.results || []; rows = all.slice(0, limit); more = all.length > limit;
        }
        // 답글이 있는 글은 대표 답글 하나(좋아요 많은 순 → 먼저 단 순)를 미리 보여 준다
        const withRe = rows.filter((c) => c.replies > 0).map((c) => c.id);
        const tops = {};
        if (withRe.length) {
          const tr = await db.prepare(`SELECT parent_id, id, nick, uid, body, likes FROM (SELECT parent_id, id, nick, uid, body, likes,
              ROW_NUMBER() OVER (PARTITION BY parent_id ORDER BY likes DESC, created ASC) AS rn FROM comments
              WHERE status = 'ok' AND parent_id IN (${withRe.map(() => "?").join(",")})) WHERE rn = 1`).bind(...withRe).all();
          for (const x of tr.results || []) tops[x.parent_id] = { id: x.id, nick: x.nick, uid: x.uid || null, body: x.body.length > 120 ? x.body.slice(0, 120) + "…" : x.body, likes: x.likes };
        }
        const pub = (c) => ({ id: c.id, slug: c.slug, nick: c.nick, uid: c.uid || null, body: c.body, likes: c.likes, created: c.created, replies: c.replies, liked: !!c.liked, mine: !!c.did && c.did === actor, top: tops[c.id] || null, reposts: c.reposts || 0, reposted: !!c.reposted, quote: quoteOf(c) });
        const items = rows.map(pub);
        // 팔로잉 탭 첫 화면: 내가 팔로우한 사람이 리포스트한 리포트·글도 함께(쓰레드의 '○○님이 리포스트함')
        let reposts = [];
        if ((following || (url.searchParams.get("tab") === "mix" && me && !parseInt(url.searchParams.get("offset") || "0", 10))) && !url.searchParams.get("before")) {
          const rr = (await db.prepare(`SELECT r.uid, u.nick, r.kind, r.ref, r.created FROM reposts r JOIN follows f ON f.followee = r.uid JOIN users u ON u.id = r.uid
              WHERE f.follower = ? AND u.status = 'ok' ORDER BY r.created DESC LIMIT 20`).bind(me.id).all()).results || [];
          const pids = rr.filter((x) => x.kind === "p").map((x) => parseInt(x.ref, 10)).filter(Boolean);
          const prow = {};
          if (pids.length) {
            for (const c of (await db.prepare(`SELECT ${cols} FROM comments c WHERE c.status = 'ok' AND c.id IN (${pids.map(() => "?").join(",")})`).bind(actor, me.id, ...pids).all()).results || []) prow[c.id] = c;
          }
          reposts = rr.map((x) => x.kind === "r" ? { type: "report", slug: x.ref, rp: { nick: x.nick, uid: x.uid, at: x.created } }
            : prow[x.ref] ? { ...pub(prow[x.ref]), rp: { nick: x.nick, uid: x.uid, at: x.created } } : null).filter(Boolean);
        }
        // 종목 커뮤니티 첫 화면: 운영자 공지(고정 글)를 맨 위에
        let pinned = [];
        if (scoped && scopeBoard && !url.searchParams.get("before") && !parseInt(url.searchParams.get("offset") || "0", 10)) {
          pinned = ((await db.prepare(`SELECT ${cols} FROM comments c WHERE c.slug = ? AND c.parent_id IS NULL AND c.pinned = 1 AND c.status = 'ok' ORDER BY c.created DESC LIMIT 2`).bind(actor, me ? me.id : 0, scopeBoard).all()).results || []).map((c) => ({ ...pub(c), pinned: true }));
        }
        return json(req, { items, more, hot: usedHot, reposts, pinned }, 200, { "Cache-Control": "no-store" });
      }
      // 글 하나와 답글(글 상세 화면). 답글 번호로 열면 원글을 보여 준다
      const pm = p.match(/^\/v1\/post\/(\d+)$/);
      if (pm && req.method === "GET") {
        let c = await db.prepare("SELECT * FROM comments WHERE id = ? AND status = 'ok'").bind(parseInt(pm[1], 10)).first();
        if (c && c.parent_id) c = await db.prepare("SELECT * FROM comments WHERE id = ? AND status = 'ok'").bind(c.parent_id).first();
        if (!c) return json(req, { error: "not_found" }, 404, { "Cache-Control": "no-store" });
        const [rs, lk] = await Promise.all([
          db.prepare("SELECT * FROM comments WHERE parent_id = ? AND status = 'ok' ORDER BY created ASC LIMIT 200").bind(c.id).all(),
          db.prepare("SELECT l.cid FROM comment_likes l JOIN comments x ON x.id = l.cid WHERE (x.id = ? OR x.parent_id = ?) AND l.ih = ?").bind(c.id, c.id, actor).all(),
        ]);
        const me2 = session ? await userByActor(db, actor) : null;
        const rpn = await db.prepare("SELECT COUNT(*) AS n, SUM(uid = ?) AS mine FROM reposts WHERE kind = 'p' AND ref = ?").bind(me2 ? me2.id : 0, String(c.id)).first();
        return json(req, {
          post: { ...publicComment(c, actor), slug: c.slug, reposts: rpn?.n || 0, reposted: !!rpn?.mine },
          replies: (rs.results || []).map((x) => publicComment(x, actor)),
          liked: (lk.results || []).map((x) => x.cid),
        }, 200, { "Cache-Control": "no-store" });
      }
      // 팔로우 추천: 최근 30일 받은 좋아요·글이 많은 사람(나와 이미 팔로우한 사람 제외)
      if (p === "/v1/users/suggest" && req.method === "GET") {
        const me = await userByActor(db, actor);
        const mid = me ? me.id : 0;
        const r = await db.prepare(`SELECT u.id, u.nick, u.bio, COALESCE(SUM(c.likes), 0) AS likes, COUNT(c.id) AS posts FROM users u
            JOIN comments c ON c.uid = u.id AND c.status = 'ok' AND c.created > ?
            WHERE u.status = 'ok' AND u.id != ? AND u.id NOT IN (SELECT followee FROM follows WHERE follower = ?)
            GROUP BY u.id ORDER BY likes DESC, posts DESC, u.id DESC LIMIT 5`).bind(now - 30 * 864e5, mid, mid).all();
        return json(req, { items: r.results || [] }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/notifications" && req.method === "GET") {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { items: [], unread: 0 }, 200, { "Cache-Control": "no-store" });
        const r = await db.prepare("SELECT type, ref, slug, from_nick, n, updated, seen FROM notifs WHERE uid = ? ORDER BY updated DESC LIMIT 30").bind(me.id).all();
        const items = r.results || [];
        return json(req, { items, unread: items.filter((x) => !x.seen).length }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/notifications/read" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (me) await db.prepare("UPDATE notifs SET seen = 1 WHERE uid = ?").bind(me.id).run();
        if (me && Math.random() < 0.05) await db.prepare("DELETE FROM notifs WHERE uid = ? AND seen = 1 AND updated < ?").bind(me.id, now - 30 * 864e5).run();
        return json(req, { ok: true });
      }

      // ---------- 공유 미리보기: 종토방·라운지 글(/s/p/번호)과 프로필(/s/u/번호) ----------
      // 글·프로필 화면은 브라우저가 API로 채우는 정적 페이지라 카카오톡·쓰레드·X 미리보기가 '글 | 김박사 월드'로만 나온다.
      // 공유 버튼은 이 주소를 쓰고, 미리보기 로봇에는 글 내용으로 만든 제목·설명·그림을, 사람에게는 바로 그 글로 넘겨 준다.
      const shm = p.match(/^\/s\/(p|u)\/(\d+)$/);
      if (shm && req.method === "GET") {
        const esc = (x) => String(x || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
        const cut = (x, n) => { x = String(x || "").replace(/\s+/g, " ").trim(); return x.length > n ? x.slice(0, n - 1) + "…" : x; };
        const id = parseInt(shm[2], 10), q = "utm_source=share&utm_medium=link";
        let title = "김박사 월드", desc = "주가가 왜 그렇게 움직였는지, 공시와 실적으로 쓴 무료 리포트와 투자자 커뮤니티", img = `${SITE}/static/og-default.png`, to = `${SITE}/`;
        if (shm[1] === "p") {
          let c = await db.prepare("SELECT id, slug, nick, uid, body, parent_id, status FROM comments WHERE id = ?").bind(id).first();
          if (c && c.status === "ok" && /^b-/.test(c.slug)) {
            const code = c.slug.slice(2), board = code === "talk" ? "커뮤니티" : `$${code.toUpperCase()} 커뮤니티`;
            const replies = await db.prepare("SELECT COUNT(*) AS n FROM comments WHERE parent_id = ? AND status = 'ok'").bind(c.parent_id || c.id).first();
            title = `${c.nick}님 · ${board}`;
            desc = cut(c.body, 110) + (replies?.n ? ` (답글 ${replies.n}개)` : "");
            img = `${SITE}/og/b-${code}.png`; to = `${SITE}/p/?id=${c.parent_id || c.id}&${q}`;
          }
        } else {
          const u = await db.prepare("SELECT id, nick, bio, av, status FROM users WHERE id = ?").bind(id).first();
          if (u && u.status === "ok") {
            const st = await db.prepare("SELECT (SELECT COUNT(*) FROM follows WHERE followee = ?) AS f, (SELECT COUNT(*) FROM comments WHERE uid = ? AND status = 'ok') AS n").bind(u.id, u.id).first();
            title = `${u.nick}님의 프로필 · 김박사 월드`;
            desc = cut(u.bio || "김박사 월드에서 종목 이야기를 나누는 투자자", 80) + ` · 팔로워 ${st?.f || 0} · 글 ${st?.n || 0}`;
            if (u.av) img = `${url.origin}/v1/avatar/${u.id}?v=${u.av}`;
            to = `${SITE}/u/?id=${u.id}&${q}`;
          }
        }
        const big = !img.includes("/v1/avatar/");
        const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><meta name="description" content="${esc(desc)}"><meta name="robots" content="noindex">
<meta property="og:site_name" content="김박사 월드"><meta property="og:locale" content="ko_KR"><meta property="og:type" content="article">
<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(desc)}"><meta property="og:url" content="${esc(url.origin + p)}">
<meta property="og:image" content="${esc(img)}">${big ? '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">' : ""}
<meta name="twitter:card" content="${big ? "summary_large_image" : "summary"}"><meta name="twitter:title" content="${esc(title)}"><meta name="twitter:description" content="${esc(desc)}"><meta name="twitter:image" content="${esc(img)}">
<link rel="canonical" href="${esc(to.split("?")[0] + (to.includes("?id=") ? "?id=" + to.split("?id=")[1].split("&")[0] : ""))}">
<style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e2e8f0;display:grid;place-items:center;min-height:100vh;margin:0}a{color:#f59e0b}</style>
</head><body><p><a href="${esc(to)}">김박사 월드에서 보기 →</a></p><script>location.replace(${JSON.stringify(to)})</script></body></html>`;
        return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=300" } });
      }

      // ---------- 프로필 사진 ----------
      const avm = p.match(/^\/v1\/avatar\/(\d+)$/);
      if (avm && req.method === "GET") { // <img>로 직접 부른다. 버전(?v=)이 맞으면 1년 캐시
        const uid = parseInt(avm[1], 10), v = parseInt(url.searchParams.get("v") || "0", 10) || 0;
        const cache = typeof caches !== "undefined" ? caches.default : null;
        if (cache && v) { const hit = await cache.match(req.url); if (hit) return hit; }
        // raw=1: 운영자가 신고로 내려간 사진을 확인할 때(운영자 계정만, 캐시 안 함)
        let raw = false;
        if (url.searchParams.get("raw") && session) { const me = await userByActor(db, actor); raw = !!me && !!(await db.prepare("SELECT 1 AS y FROM owners WHERE uid = ?").bind(me.id).first()); }
        if (raw) {
          const r0 = await db.prepare("SELECT mime, data FROM avatars WHERE uid = ?").bind(uid).first();
          return r0 ? new Response(fromB64(r0.data), { headers: { "Content-Type": r0.mime, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } }) : new Response("", { status: 404 });
        }
        const row = await db.prepare("SELECT a.mime, a.data, a.v FROM avatars a JOIN users u ON u.id = a.uid WHERE a.uid = ? AND u.status = 'ok' AND u.av = a.v").bind(uid).first();
        if (!row) return new Response("", { status: 404, headers: { "Cache-Control": "public, max-age=300", "Access-Control-Allow-Origin": "*" } });
        const res = new Response(fromB64(row.data), { headers: { "Content-Type": row.mime, "Access-Control-Allow-Origin": "*", "X-Content-Type-Options": "nosniff",
          "Cache-Control": v === row.v ? "public, max-age=31536000, immutable" : "public, max-age=300" } });
        if (cache && v === row.v) await cache.put(req.url, res.clone());
        return res;
      }
      if (p === "/v1/avatars" && req.method === "GET") { // 여러 사람의 사진 버전(화면이 글자 동그라미를 사진으로 바꿀 때)
        const ids = [...new Set((url.searchParams.get("ids") || "").split(",").map((x) => parseInt(x, 10)).filter((x) => x > 0))].slice(0, 100);
        const out = {};
        if (ids.length) for (const r of (await db.prepare(`SELECT id, av FROM users WHERE av > 0 AND status = 'ok' AND id IN (${ids.map(() => "?").join(",")})`).bind(...ids).all()).results || []) out[r.id] = r.av;
        return json(req, { av: out }, 200, { "Cache-Control": "public, max-age=60" });
      }
      if (p === "/v1/me/avatar" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me || me.status !== "ok") return json(req, { error: "account", message: "로그인한 계정만 사진을 올릴 수 있습니다." }, 401);
        if (+(req.headers.get("Content-Length") || 0) > AVATAR_MAX) return json(req, { error: "size", message: "사진이 너무 큽니다." }, 413);
        const u8 = new Uint8Array(await req.arrayBuffer());
        if (u8.length > AVATAR_MAX || u8.length < 100) return json(req, { error: "size", message: "사진을 올리지 못했습니다. 다른 사진으로 해 보세요." }, 400);
        const mime = imageMime(u8);
        if (!mime) return json(req, { error: "type", message: "JPG·PNG·WEBP 사진만 올릴 수 있습니다." }, 400);
        if (!(await allow(db, `av|${me.id}`, 10, 864e5, now))) return json(req, { error: "rate", message: "사진은 하루 10번까지 바꿀 수 있습니다." }, 429);
        await db.batch([
          db.prepare("INSERT INTO avatars (uid, mime, data, v, reports) VALUES (?, ?, ?, ?, 0) ON CONFLICT(uid) DO UPDATE SET mime = excluded.mime, data = excluded.data, v = excluded.v, reports = 0").bind(me.id, mime, toB64(u8), now),
          db.prepare("UPDATE users SET av = ? WHERE id = ?").bind(now, me.id),
          db.prepare("DELETE FROM user_reports WHERE uid = ? AND what = 'avatar'").bind(me.id),
        ]);
        return json(req, { ok: true, av: now });
      }
      if (p === "/v1/me/avatar/delete" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { ok: false }, 401);
        await db.batch([db.prepare("DELETE FROM avatars WHERE uid = ?").bind(me.id), db.prepare("UPDATE users SET av = 0 WHERE id = ?").bind(me.id)]);
        return json(req, { ok: true, av: 0 });
      }
      // 이용자 신고: 사진(3명이 신고하면 사진을 내림) · 닉네임·소개(운영자 검토)
      const urm = p.match(/^\/v1\/users\/(\d+)\/report$/);
      if (urm && req.method === "POST") {
        const uid = parseInt(urm[1], 10), { what } = await readJson(req);
        if (!["avatar", "profile"].includes(what)) return json(req, { error: "what" }, 400);
        const t = await db.prepare("SELECT id, av FROM users WHERE id = ? AND status = 'ok'").bind(uid).first();
        if (!t) return json(req, { error: "not_found" }, 404);
        const me = await userByActor(db, actor);
        if (me && me.id === uid) return json(req, { error: "own" }, 400);
        if (!(await allow(db, `urep|${uid}|${what}|${ih}`, 1, 864e5, now))) return json(req, { ok: true });
        const ins = await db.prepare("INSERT OR IGNORE INTO user_reports (uid, by_actor, what, created) VALUES (?, ?, ?, ?)").bind(uid, actor, what, now).run();
        if (ins.meta?.changes && what === "avatar" && t.av) {
          const n = await db.prepare("SELECT COUNT(*) AS n FROM user_reports WHERE uid = ? AND what = 'avatar'").bind(uid).first();
          await db.prepare("UPDATE avatars SET reports = ? WHERE uid = ?").bind(n?.n || 0, uid).run();
          if ((n?.n || 0) >= LIMITS.reportHide) await db.prepare("UPDATE users SET av = 0 WHERE id = ?").bind(uid).run(); // 사진만 내린다(운영자가 보고 되돌릴 수 있음)
        }
        return json(req, { ok: true });
      }
      // ---------- 차단: 다시 누르면 해제. 차단하면 서로 팔로우가 풀리고 쪽지를 주고받을 수 없다 ----------
      if (p === "/v1/block" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { error: "account", message: "로그인하면 차단할 수 있습니다." }, 401);
        const uid = parseInt((await readJson(req)).uid, 10) || 0;
        if (!uid || uid === me.id || !(await db.prepare("SELECT 1 AS y FROM users WHERE id = ?").bind(uid).first())) return json(req, { error: "target" }, 400);
        const ins = await db.prepare("INSERT OR IGNORE INTO blocks (blocker, blocked, created) SELECT ?, ?, ? WHERE (SELECT COUNT(*) FROM blocks WHERE blocker = ?) < 500").bind(me.id, uid, now, me.id).run();
        if (ins.meta?.changes) await db.prepare("DELETE FROM follows WHERE (follower = ? AND followee = ?) OR (follower = ? AND followee = ?)").bind(me.id, uid, uid, me.id).run();
        else await db.prepare("DELETE FROM blocks WHERE blocker = ? AND blocked = ?").bind(me.id, uid).run();
        return json(req, { blocked: !!ins.meta?.changes });
      }
      if (p === "/v1/blocks" && req.method === "GET") {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { items: [] }, 200, { "Cache-Control": "no-store" });
        const r = await db.prepare("SELECT u.id, u.nick, u.av, b.created FROM blocks b JOIN users u ON u.id = b.blocked WHERE b.blocker = ? ORDER BY b.created DESC LIMIT 500").bind(me.id).all();
        return json(req, { items: r.results || [] }, 200, { "Cache-Control": "no-store" });
      }
      // ---------- 팔로워·팔로잉 목록 ----------
      const flm = p.match(/^\/v1\/users\/(\d+)\/follows$/);
      if (flm && req.method === "GET") {
        const uid = parseInt(flm[1], 10), type = url.searchParams.get("type") === "following" ? "following" : "followers";
        const before = parseInt(url.searchParams.get("before") || "0", 10) || now + 1;
        const me = await userByActor(db, actor);
        const col = type === "following" ? ["followee", "follower"] : ["follower", "followee"]; // [보여 줄 사람, 이 프로필]
        const r = await db.prepare(`SELECT u.id, u.nick, u.bio, u.av, f.created,
            EXISTS(SELECT 1 FROM follows x WHERE x.follower = ? AND x.followee = u.id) AS following
            FROM follows f JOIN users u ON u.id = f.${col[0]} WHERE f.${col[1]} = ? AND u.status = 'ok' AND f.created < ? ORDER BY f.created DESC LIMIT 51`).bind(me ? me.id : 0, uid, before).all();
        const rows = r.results || [];
        return json(req, { type, items: rows.slice(0, 50).map((x) => ({ ...x, following: !!x.following, self: !!me && me.id === x.id })), more: rows.length > 50 }, 200, { "Cache-Control": "no-store" });
      }
      // ---------- 사용자 찾기(쪽지 상대·@멘션 고르기) ----------
      if (p === "/v1/users/search" && req.method === "GET") {
        const q = cleanText(url.searchParams.get("q"), 12).toLowerCase().replace(/[%_\\\s]/g, "");
        if (q.length < 1) return json(req, { items: [] });
        if (!(await allow(db, `usearch|${ih}`, 600, 3600e3, now))) return json(req, { items: [] }, 429);
        const r = await db.prepare(`SELECT id, nick, bio, av FROM users WHERE status = 'ok' AND nick_lc LIKE ? ORDER BY (nick_lc = ?) DESC, length(nick_lc), id LIMIT 10`).bind(q + "%", q).all();
        let items = r.results || [];
        if (items.length < 10 && q.length >= 2) {
          const more = await db.prepare(`SELECT id, nick, bio, av FROM users WHERE status = 'ok' AND nick_lc LIKE ? AND nick_lc NOT LIKE ? ORDER BY id LIMIT ?`).bind("%" + q + "%", q + "%", 10 - items.length).all();
          items = items.concat(more.results || []);
        }
        return json(req, { items }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/users/by-nick" && req.method === "GET") {
        const n = String(url.searchParams.get("n") || "").trim().toLowerCase();
        const u = NICK_RE.test(n) ? await db.prepare("SELECT id FROM users WHERE nick_lc = ? AND status = 'ok'").bind(n).first() : null;
        return u ? json(req, { id: u.id }, 200, { "Cache-Control": "public, max-age=60" }) : json(req, { error: "not_found" }, 404);
      }

      // ---------- 쪽지(DM) ----------
      if (p.startsWith("/v1/dm")) {
        const me = await userByActor(db, actor);
        if (!me) return json(req, { error: "account", message: "로그인하면 쪽지를 쓸 수 있습니다." }, 401, { "Cache-Control": "no-store" });
        const side = (t) => (t.a === me.id ? "a" : "b");
        const otherOf = (t) => (t.a === me.id ? t.b : t.a);
        const userCard = (u) => (u ? { id: u.id, nick: u.nick, av: u.status === "ok" ? u.av || 0 : 0, active: u.status === "ok" } : { id: 0, nick: "탈퇴한 사용자", av: 0, active: false });
        const getThread = async (tid) => {
          const t = await db.prepare("SELECT * FROM dm_threads WHERE id = ?").bind(tid).first();
          return t && (t.a === me.id || t.b === me.id) ? t : null;
        };
        const getUser = (id) => db.prepare("SELECT id, nick, bio, av, status, dm_pref, created FROM users WHERE id = ?").bind(id).first();
        if (p === "/v1/dm" && req.method === "GET") { // 대화 목록
          const r = await db.prepare(`SELECT t.*, u.nick AS o_nick, u.av AS o_av, u.status AS o_status FROM dm_threads t
              LEFT JOIN users u ON u.id = CASE WHEN t.a = ? THEN t.b ELSE t.a END
              WHERE (t.a = ? AND t.last_id > t.a_del) OR (t.b = ? AND t.last_id > t.b_del) ORDER BY t.last_at DESC LIMIT 100`).bind(me.id, me.id, me.id).all();
          const items = (r.results || []).map((t) => {
            const sd = side(t), read = t[sd + "_read"];
            return {
              id: t.id, other: userCard(t.o_nick != null ? { id: otherOf(t), nick: t.o_nick, av: t.o_av, status: t.o_status } : null),
              last: { body: t.last_body, at: t.last_at, mine: t.last_from === me.id },
              unread: t.last_from !== me.id && t.last_id > read, request: !t.accepted && t.starter !== me.id, pending: !t.accepted && t.starter === me.id,
            };
          });
          return json(req, { items, ...(await dmUnread(db, me.id)) }, 200, { "Cache-Control": "no-store" });
        }
        const wm = p.match(/^\/v1\/dm\/with\/(\d+)$/);
        if (wm && req.method === "GET") { // 이 사람과의 대화방(없으면 null)과 보낼 수 있는지
          const o = await getUser(parseInt(wm[1], 10));
          if (!o) return json(req, { error: "not_found" }, 404);
          const [x, y] = pair(me.id, o.id);
          const t = await db.prepare("SELECT * FROM dm_threads WHERE a = ? AND b = ?").bind(x, y).first();
          const perm = await dmPermission(db, me, o, t, now);
          return json(req, { tid: t ? t.id : null, other: userCard(o), can: perm.can, reason: perm.reason || "", request: !!perm.request }, 200, { "Cache-Control": "no-store" });
        }
        const tm = p.match(/^\/v1\/dm\/(\d+)$/);
        if (tm && req.method === "GET") { // 대화 내용. after=번호(새 쪽지만), before=번호(이전 쪽지)
          const t = await getThread(parseInt(tm[1], 10));
          if (!t) return json(req, { error: "not_found" }, 404, { "Cache-Control": "no-store" });
          const sd = side(t), del = t[sd + "_del"];
          const after = parseInt(url.searchParams.get("after") || "0", 10) || 0, before = parseInt(url.searchParams.get("before") || "0", 10) || 0;
          const r = before
            ? await db.prepare("SELECT * FROM dm_msgs WHERE tid = ? AND id > ? AND id < ? ORDER BY id DESC LIMIT 50").bind(t.id, del, before).all()
            : await db.prepare("SELECT * FROM dm_msgs WHERE tid = ? AND id > ? ORDER BY id DESC LIMIT 50").bind(t.id, Math.max(del, after)).all();
          const msgs = (r.results || []).reverse();
          if (t.last_id > t[sd + "_read"]) await db.prepare(`UPDATE dm_threads SET ${sd}_read = last_id WHERE id = ?`).bind(t.id).run();
          const o = await getUser(otherOf(t));
          const perm = await dmPermission(db, me, o, t, now);
          const oRead = t[(sd === "a" ? "b" : "a") + "_read"];
          return json(req, {
            thread: { id: t.id, other: userCard(o), accepted: !!t.accepted, request: !t.accepted && t.starter !== me.id, pending: !t.accepted && t.starter === me.id, can: perm.can, reason: perm.reason || "", seenUpTo: oRead },
            items: msgs.map((m) => ({ id: m.id, mine: m.sender === me.id, body: m.status === "ok" ? m.body : "", status: m.status, at: m.created })),
            more: !after && msgs.length === 50,
          }, 200, { "Cache-Control": "no-store" });
        }
        if (p === "/v1/dm/send" && req.method === "POST") {
          const b = await readJson(req);
          const body = cleanText(b.body, DM.bodyMax + 1);
          if (body.length < 1) return json(req, { error: "short", message: "내용을 써 주세요." }, 400);
          if (body.length > DM.bodyMax) return json(req, { error: "long", message: `쪽지는 ${DM.bodyMax}자까지 쓸 수 있습니다.` }, 400);
          const prob = dmProblem(body);
          if (prob) return json(req, { error: "blocked_content", message: prob }, 400);
          let t = b.tid ? await getThread(parseInt(b.tid, 10)) : null;
          const oid = t ? otherOf(t) : parseInt(b.to, 10) || 0;
          const o = await getUser(oid);
          const [x, y] = pair(me.id, oid);
          if (!t && o) t = await db.prepare("SELECT * FROM dm_threads WHERE a = ? AND b = ?").bind(x, y).first();
          const perm = await dmPermission(db, me, o, t, now);
          if (!perm.can) return json(req, { error: "cannot", message: perm.reason }, 403);
          if (!(await allow(db, `dm|${me.id}`, DM.perHour, 3600e3, now)) || !(await allow(db, `dmd|${me.id}`, DM.perDay, 864e5, now)))
            return json(req, { error: "rate", message: "쪽지를 너무 많이 보냈습니다. 잠시 뒤에 다시 보내 주세요." }, 429);
          if (!t) {
            if (perm.request && !(await allow(db, `dmreq|${me.id}`, DM.reqPerDay, 864e5, now))) return json(req, { error: "rate", message: "처음 보는 사람에게는 하루 10명까지 쪽지를 보낼 수 있습니다." }, 429);
            await db.prepare("INSERT OR IGNORE INTO dm_threads (a, b, starter, accepted, created, last_at) VALUES (?, ?, ?, ?, ?, ?)").bind(x, y, me.id, perm.request ? 0 : 1, now, now).run();
            t = await db.prepare("SELECT * FROM dm_threads WHERE a = ? AND b = ?").bind(x, y).first();
          }
          const accept = !t.accepted && (perm.accepting || perm.theyFollowMe);
          const ins = await db.prepare("INSERT INTO dm_msgs (tid, sender, body, created) VALUES (?, ?, ?, ?)").bind(t.id, me.id, body, now).run();
          const mid = ins.meta?.last_row_id, sd = side(t);
          await db.prepare(`UPDATE dm_threads SET last_at = ?, last_id = ?, last_from = ?, last_body = ?, ${sd}_read = ?${accept ? ", accepted = 1" : ""} WHERE id = ?`)
            .bind(now, mid, me.id, body.length > 80 ? body.slice(0, 80) + "…" : body, mid, t.id).run();
          return json(req, { ok: true, id: mid, tid: t.id, accepted: !!(t.accepted || accept), at: now });
        }
        const am2 = p.match(/^\/v1\/dm\/(\d+)\/(accept|delete)$/);
        if (am2 && req.method === "POST") {
          const t = await getThread(parseInt(am2[1], 10));
          if (!t) return json(req, { error: "not_found" }, 404);
          const sd = side(t);
          if (am2[2] === "accept") {
            if (t.starter !== me.id) await db.prepare("UPDATE dm_threads SET accepted = 1 WHERE id = ?").bind(t.id).run();
            return json(req, { ok: true });
          }
          // 대화 삭제: 내 화면에서만 지운다. 둘 다 지우면 서버에서도 지운다
          await db.prepare(`UPDATE dm_threads SET ${sd}_del = last_id, ${sd}_read = last_id WHERE id = ?`).bind(t.id).run();
          const t2 = await db.prepare("SELECT * FROM dm_threads WHERE id = ?").bind(t.id).first();
          if (t2 && t2.a_del >= t2.last_id && t2.b_del >= t2.last_id) {
            const reported = await db.prepare("SELECT 1 AS y FROM dm_reports r JOIN dm_msgs m ON m.id = r.mid WHERE m.tid = ? AND r.reviewed = 0").bind(t.id).first();
            if (!reported) await db.batch([db.prepare("DELETE FROM dm_msgs WHERE tid = ?").bind(t.id), db.prepare("DELETE FROM dm_threads WHERE id = ?").bind(t.id)]);
          }
          return json(req, { ok: true });
        }
        const mm = p.match(/^\/v1\/dm\/msg\/(\d+)\/(delete|report)$/);
        if (mm && req.method === "POST") {
          const m = await db.prepare("SELECT * FROM dm_msgs WHERE id = ?").bind(parseInt(mm[1], 10)).first();
          const t = m ? await getThread(m.tid) : null;
          if (!m || !t) return json(req, { error: "not_found" }, 404);
          if (mm[2] === "delete") { // 보낸 사람만, 내용을 지운다(상대 화면에는 '삭제된 쪽지')
            if (m.sender !== me.id) return json(req, { error: "own" }, 403);
            await db.prepare("UPDATE dm_msgs SET status = 'deleted', body = '' WHERE id = ?").bind(m.id).run();
            if (t.last_id === m.id) await db.prepare("UPDATE dm_threads SET last_body = '삭제된 쪽지' WHERE id = ?").bind(t.id).run();
            return json(req, { ok: true });
          }
          if (m.sender === me.id) return json(req, { error: "own" }, 400);
          await db.prepare("INSERT OR IGNORE INTO dm_reports (mid, by_uid, created) VALUES (?, ?, ?)").bind(m.id, me.id, now).run();
          return json(req, { ok: true, message: "신고했습니다. 운영자가 확인합니다. 원하시면 이 사람을 차단할 수도 있어요." });
        }
        return json(req, { error: "not_found" }, 404);
      }

      // ---------- 운영자 애널리틱스: 운영자 계정(owners) 로그인 또는 관리 토큰 ----------
      if (p === "/v1/admin/analytics" && req.method === "GET") {
        const auth = req.headers.get("Authorization") || "";
        let ok = !!env.ADMIN_TOKEN && safeEqual(auth, `Bearer ${env.ADMIN_TOKEN}`);
        if (!ok && session) {
          const me = await userByActor(db, actor);
          ok = !!me && !!(await db.prepare("SELECT 1 AS y FROM owners WHERE uid = ?").bind(me.id).first());
        }
        if (!ok) return json(req, { error: "owner", message: "운영자 계정만 볼 수 있습니다." }, 403, { "Cache-Control": "no-store" });
        return json(req, await analytics(db, now, parseInt(url.searchParams.get("days") || "30", 10)), 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/admin/whoami" && req.method === "GET") { // 화면이 운영자 여부만 묻는다
        const me = session ? await userByActor(db, actor) : null;
        const own = me ? !!(await db.prepare("SELECT 1 AS y FROM owners WHERE uid = ?").bind(me.id).first()) : false;
        return json(req, { loggedIn: !!session, user: me ? { id: me.id, nick: me.nick } : null, owner: own }, 200, { "Cache-Control": "no-store" });
      }

      // ---------- 신고 처리(운영자 계정 로그인 또는 관리 토큰): 신고된 쪽지는 공개 기록(Actions)에 남기지 않고 운영 통계 화면에서만 본다 ----------
      if (p === "/v1/admin/reports" || /^\/v1\/admin\/(dm\/\d+|users\/\d+\/(avatar|profile))$/.test(p)) {
        const auth = req.headers.get("Authorization") || "";
        let ok = !!env.ADMIN_TOKEN && safeEqual(auth, `Bearer ${env.ADMIN_TOKEN}`);
        if (!ok && session) { const me = await userByActor(db, actor); ok = !!me && !!(await db.prepare("SELECT 1 AS y FROM owners WHERE uid = ?").bind(me.id).first()); }
        if (!ok) return json(req, { error: "owner" }, 403, { "Cache-Control": "no-store" });
      // 신고된 쪽지·프로필(사진·닉네임·소개). 쪽지는 신고된 것만 운영자가 본다
      if (p === "/v1/admin/reports" && req.method === "GET") {
        const [dm, ur] = await Promise.all([
          db.prepare(`SELECT m.id, m.tid, m.sender, su.nick AS sender_nick, m.body, m.status, m.created, COUNT(r.by_uid) AS n, MIN(r.created) AS first
              FROM dm_reports r JOIN dm_msgs m ON m.id = r.mid LEFT JOIN users su ON su.id = m.sender WHERE r.reviewed = 0 GROUP BY m.id ORDER BY first DESC LIMIT 100`).all(),
          db.prepare(`SELECT u.id, u.nick, u.bio, u.av, (SELECT v FROM avatars a WHERE a.uid = u.id) AS av_stored, ur.what, COUNT(*) AS n, MAX(ur.created) AS last FROM user_reports ur JOIN users u ON u.id = ur.uid
              GROUP BY ur.uid, ur.what ORDER BY last DESC LIMIT 100`).all(),
        ]);
        return json(req, { dm: dm.results || [], users: ur.results || [] });
      }
      const adm = p.match(/^\/v1\/admin\/dm\/(\d+)$/);
      if (adm && req.method === "POST") { // 신고 쪽지 처리: hidden(가림) | ok(문제 없음)
        const { status } = await readJson(req);
        if (!["ok", "hidden"].includes(status)) return json(req, { error: "status" }, 400);
        const mid = parseInt(adm[1], 10);
        await db.batch([
          db.prepare("UPDATE dm_msgs SET status = ? WHERE id = ? AND status != 'deleted'").bind(status, mid),
          db.prepare("UPDATE dm_reports SET reviewed = 1 WHERE mid = ?").bind(mid),
        ]);
        return json(req, { ok: true });
      }
      const aav = p.match(/^\/v1\/admin\/users\/(\d+)\/(avatar|profile)$/);
      if (aav && req.method === "POST") { // 사진 내리기·되돌리기, 프로필 신고 정리
        const id = parseInt(aav[1], 10), { action } = await readJson(req);
        if (aav[2] === "avatar") {
          if (action === "remove") await db.batch([db.prepare("DELETE FROM avatars WHERE uid = ?").bind(id), db.prepare("UPDATE users SET av = 0 WHERE id = ?").bind(id)]);
          else if (action === "restore") await db.prepare("UPDATE users SET av = (SELECT v FROM avatars WHERE uid = ?) WHERE id = ? AND EXISTS(SELECT 1 FROM avatars WHERE uid = ?)").bind(id, id, id).run();
          else return json(req, { error: "action" }, 400);
          await db.prepare("DELETE FROM user_reports WHERE uid = ? AND what = 'avatar'").bind(id).run();
        } else {
          if (action === "clear_bio") await db.prepare("UPDATE users SET bio = '' WHERE id = ?").bind(id).run();
          await db.prepare("DELETE FROM user_reports WHERE uid = ? AND what = 'profile'").bind(id).run();
        }
        return json(req, { ok: true });
      }
        return json(req, { error: "not_found" }, 404);
      }
      // ---------- 관리 (Authorization: Bearer ADMIN_TOKEN) ----------
      if (p.startsWith("/v1/admin/")) {
        const auth = req.headers.get("Authorization") || "";
        if (!env.ADMIN_TOKEN || !safeEqual(auth, `Bearer ${env.ADMIN_TOKEN}`)) return json(req, { error: "auth" }, 401);
        if (p === "/v1/admin/queue" && req.method === "GET") {
          const r = await db.prepare("SELECT id, slug, nick, uid, body, likes, reports, status, created FROM comments WHERE status IN ('held','hidden') ORDER BY created DESC LIMIT 200").all();
          return json(req, { items: r.results || [] });
        }
        const au = p.match(/^\/v1\/admin\/users\/(\d+)$/);
        if (au && req.method === "POST") { // 계정 정지·해제. 정지하면 그 계정 글도 모두 숨긴다
          const { status } = await readJson(req);
          if (!["ok", "banned"].includes(status)) return json(req, { error: "status" }, 400);
          const id = parseInt(au[1], 10);
          await db.batch([
            db.prepare("UPDATE users SET status = ? WHERE id = ?").bind(status, id),
            db.prepare(`UPDATE comments SET status = ? WHERE uid = ? AND status = ?`).bind(status === "banned" ? "hidden" : "ok", id, status === "banned" ? "ok" : "hidden"),
          ]);
          return json(req, { ok: true });
        }
        const am = p.match(/^\/v1\/admin\/comments\/(\d+)$/);
        if (am && req.method === "POST") {
          const { status } = await readJson(req);
          if (!["ok", "held", "hidden", "deleted"].includes(status)) return json(req, { error: "status" }, 400);
          const r = await db.prepare("UPDATE comments SET status = ?, reviewed = 1, reports = CASE WHEN ? = 'ok' THEN 0 ELSE reports END WHERE id = ?").bind(status, status, parseInt(am[1], 10)).run();
          return json(req, { ok: !!r.meta?.changes });
        }
      }
      if (p === "/v1/health") return json(req, { ok: true });
      return json(req, { error: "not_found" }, 404);
    } catch (e) {
      return json(req, { error: "server" }, 500);
    }
  },
};
