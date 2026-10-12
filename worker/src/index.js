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

function publicComment(c, actor) {
  return { id: c.id, nick: c.nick, body: c.body, likes: c.likes, created: c.created, parent: c.parent_id || null, uid: c.uid || null, pinned: !!c.pinned, mine: !!actor && !!c.did && c.did === actor };
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
const ACCOUNT = { createPerIpDay: 3, newMs: 864e5, newPostsPerDay: 5, newPostGapMs: 10 * 60e3, followPerDay: 200, bioMax: 80 };

async function userByActor(db, actor) {
  return db.prepare("SELECT id, nick, bio, created, status FROM users WHERE actor = ?").bind(actor).first();
}
// 알림: 같은 대상·종류는 한 줄로 모으고 개수만 늘린다(좋아요 100개 → 알림 1줄)
async function notify(db, uid, type, ref, slug, fromNick, now) {
  if (!uid) return;
  await db.prepare(`INSERT INTO notifs (uid, type, ref, slug, from_nick, n, updated, seen) VALUES (?, ?, ?, ?, ?, 1, ?, 0)
    ON CONFLICT(uid, type, ref) DO UPDATE SET n = CASE WHEN seen = 1 THEN 1 ELSE n + 1 END, from_nick = excluded.from_nick, updated = excluded.updated, seen = 0`)
    .bind(uid, type, String(ref), slug || "", fromNick || "", now).run();
}

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
        const [v, l, c, mine, top] = await Promise.all([
          db.prepare(`SELECT slug, n FROM views_total WHERE slug IN (${q})`).bind(...slugs).all(),
          db.prepare(`SELECT slug, n FROM likes_total WHERE slug IN (${q})`).bind(...slugs).all(),
          db.prepare(`SELECT slug, COUNT(*) AS n FROM comments WHERE status = 'ok' AND slug IN (${q}) GROUP BY slug`).bind(...slugs).all(),
          db.prepare(`SELECT slug FROM post_likes WHERE ih = ? AND slug IN (${q})`).bind(actor, ...slugs).all(),
          db.prepare(`SELECT slug, nick, body, likes, created FROM (SELECT slug, nick, body, likes, created,
              ROW_NUMBER() OVER (PARTITION BY slug ORDER BY likes DESC, created DESC) AS rn
              FROM comments WHERE status = 'ok' AND parent_id IS NULL AND slug IN (${q})) WHERE rn = 1`).bind(...slugs).all(),
        ]);
        const stats = {};
        for (const s of slugs) stats[s] = { views: 0, likes: 0, comments: 0, liked: false, top: null };
        for (const r of v.results || []) stats[r.slug].views = r.n;
        for (const r of l.results || []) stats[r.slug].likes = r.n;
        for (const r of c.results || []) stats[r.slug].comments = r.n;
        for (const r of mine.results || []) stats[r.slug].liked = true;
        for (const r of top.results || []) stats[r.slug].top = { nick: r.nick, body: r.body.length > 70 ? r.body.slice(0, 70) + "…" : r.body, likes: r.likes, created: r.created };
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
        const SLOTS = new Set(["report_mid", "report_products", "report_late", "report_end", "list", "feed_inline", "thread_inline", "rail"]);
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

      // ---------- 검색어 ----------
      if (p === "/v1/search" && req.method === "POST") {
        const { q } = await readJson(req);
        const term = cleanText(q, 20).toLowerCase().replace(/\s+/g, " ");
        if (term.length < 2 || needsHold(term)) return json(req, { ok: false });
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
        if (b.website) return json(req, { ok: true, status: "held" }); // 로봇이 채우는 숨은 칸
        if (typeof b.t === "number" && b.t < LIMITS.minTypingMs) return json(req, { error: "too_fast", message: "조금 천천히 다시 시도해 주세요." }, 429);
        const body = cleanText(b.body, LIMITS.bodyMax + 1);
        if (body.length < LIMITS.bodyMin) return json(req, { error: "short", message: "두 글자 이상 써 주세요." }, 400);
        if (body.length > LIMITS.bodyMax) return json(req, { error: "long", message: `${LIMITS.bodyMax}자까지 쓸 수 있습니다.` }, 400);
        const me = await userByActor(db, actor);
        if (me && me.status !== "ok") return json(req, { error: "banned", message: "이용이 제한된 계정입니다." }, 403);
        // 종토방은 로그인(구글·카카오)이 켜져 있으면 계정이 있어야 쓴다. 로그인을 준비하는 동안에는 익명으로도 쓸 수 있다
        if (isBoard(slug) && !me && providers(env).length) return json(req, { error: "account", message: "종토방 글은 로그인한 뒤 쓸 수 있습니다." }, 401);
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
        const status = needsHold(body) ? "held" : "ok";
        const r = await db.prepare("INSERT INTO comments (slug, nick, body, ih, did, uid, created, status, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(slug, nick, body, ih, actor, me ? me.id : null, now, status, parent).run();
        if (status === "ok" && parent && parentUid && parentDid !== actor) await notify(db, parentUid, "reply", parent, slug, nick, now);
        return json(req, {
          ok: true, status, id: r.meta?.last_row_id,
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
        const un = await db.prepare("SELECT COUNT(*) AS n FROM notifs WHERE uid = ? AND seen = 0").bind(me.id).first();
        return json(req, { ...base, user: { id: me.id, nick: me.nick, bio: me.bio, created: me.created, status: me.status }, unread: un?.n || 0 }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/me" && req.method === "POST") {
        if (!session) return json(req, { error: "login", message: "구글 또는 카카오로 로그인한 뒤 계정을 만들 수 있습니다." }, 401);
        const b = await readJson(req);
        const bio = cleanText(b.bio, ACCOUNT.bioMax + 1).replace(/\s+/g, " ");
        if (bio.length > ACCOUNT.bioMax) return json(req, { error: "bio", message: `소개는 ${ACCOUNT.bioMax}자까지입니다.` }, 400);
        if (bio && needsHold(bio)) return json(req, { error: "bio", message: "소개에는 링크·연락처·홍보 문구를 넣을 수 없습니다." }, 400);
        const me = await userByActor(db, actor);
        if (me) { // 소개만 바꿀 수 있다(닉네임은 사칭·혼란을 막으려고 고정)
          await db.prepare("UPDATE users SET bio = ? WHERE id = ?").bind(bio, me.id).run();
          return json(req, { ok: true, user: { ...me, bio } });
        }
        const nick = String(b.nick || "").trim();
        if (!NICK_RE.test(nick)) return json(req, { error: "nick", message: "닉네임은 한글·영문·숫자·_ 2~12자입니다." }, 400);
        if (/운영자|관리자|김박사|admin|drkim|kimworld/i.test(nick) || needsHold(nick)) return json(req, { error: "nick", message: "쓸 수 없는 닉네임입니다." }, 400);
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
          db.prepare("DELETE FROM notifs WHERE uid = ?").bind(me.id),
          db.prepare("DELETE FROM users WHERE id = ?").bind(me.id),
          db.prepare("DELETE FROM sessions WHERE actor = ?").bind(actor),
        ]);
        return json(req, { ok: true }, 200, { "Set-Cookie": clearCookie });
      }
      const um = p.match(/^\/v1\/users\/(\d+)$/);
      if (um && req.method === "GET") {
        const u = await db.prepare("SELECT id, nick, bio, created, status FROM users WHERE id = ?").bind(parseInt(um[1], 10)).first();
        if (!u || u.status !== "ok") return json(req, { error: "not_found" }, 404);
        const me = await userByActor(db, actor);
        const [st, fr, fg, posts, fol] = await Promise.all([
          db.prepare("SELECT COUNT(*) AS n, COALESCE(SUM(likes), 0) AS likes FROM comments WHERE uid = ? AND status = 'ok'").bind(u.id).first(),
          db.prepare("SELECT COUNT(*) AS n FROM follows WHERE followee = ?").bind(u.id).first(),
          db.prepare("SELECT COUNT(*) AS n FROM follows WHERE follower = ?").bind(u.id).first(),
          db.prepare("SELECT id, slug, body, likes, created, parent_id FROM comments WHERE uid = ? AND status = 'ok' ORDER BY created DESC LIMIT 30").bind(u.id).all(),
          me ? db.prepare("SELECT 1 AS y FROM follows WHERE follower = ? AND followee = ?").bind(me.id, u.id).first() : null,
        ]);
        return json(req, {
          user: { id: u.id, nick: u.nick, bio: u.bio, created: u.created },
          stats: { posts: st?.n || 0, likes: st?.likes || 0, followers: fr?.n || 0, following: fg?.n || 0 },
          following: !!fol, self: !!me && me.id === u.id,
          items: (posts.results || []).map((c) => ({ id: c.id, slug: c.slug, body: c.body, likes: c.likes, created: c.created, reply: !!c.parent_id })),
        }, 200, { "Cache-Control": "no-store" });
      }
      if (p === "/v1/follow" && req.method === "POST") {
        const me = await userByActor(db, actor);
        if (!me || me.status !== "ok") return json(req, { error: "account", message: "계정을 만든 뒤 팔로우할 수 있습니다." }, 401);
        const { uid } = await readJson(req);
        const target = await db.prepare("SELECT id, status FROM users WHERE id = ?").bind(parseInt(uid, 10) || 0).first();
        if (!target || target.status !== "ok" || target.id === me.id) return json(req, { error: "target" }, 400);
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
