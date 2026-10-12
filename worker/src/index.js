// 김박사 월드 API (Cloudflare Worker + D1)
// - 조회수: 같은 사람(해시)·같은 글은 하루 한 번만 센다
// - 댓글: 닉네임만(회원 가입 없음), 링크·연락처·리딩방 유도 문구는 자동 보류, 신고 3건이면 숨김
// - 좋아요·신고: 같은 사람은 댓글마다 한 번
// - 검색어: 하루 한 사람 한 번만 세서 '요즘 찾는 종목'에 쓴다(화면에는 사이트 종목·테마와 맞는 것만 보인다)
// 원래 IP는 저장하지 않는다. SALT(비밀값)로 만든 해시만 남긴다.

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

function publicComment(c, ih) {
  return { id: c.id, nick: c.nick, body: c.body, likes: c.likes, created: c.created, mine: !!ih && c.ih === ih };
}

async function readJson(req) {
  try {
    const t = await req.text();
    return t.length > 4000 ? {} : JSON.parse(t || "{}");
  } catch {
    return {};
  }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) });
    const now = Date.now();
    const ip = req.headers.get("CF-Connecting-IP") || "0.0.0.0";
    const ih = (await sha256hex(`${env.SALT || "dev-salt"}|${ip}`)).slice(0, 24);
    const db = env.DB;
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
        const slugs = (url.searchParams.get("slugs") || "").split(",").filter((s) => SLUG_RE.test(s)).slice(0, 60);
        if (!slugs.length) return json(req, { stats: {} });
        const q = slugs.map(() => "?").join(",");
        const v = await db.prepare(`SELECT slug, n FROM views_total WHERE slug IN (${q})`).bind(...slugs).all();
        const c = await db.prepare(`SELECT slug, COUNT(*) AS n FROM comments WHERE status = 'ok' AND slug IN (${q}) GROUP BY slug`).bind(...slugs).all();
        const stats = {};
        for (const s of slugs) stats[s] = { views: 0, comments: 0 };
        for (const r of v.results || []) stats[r.slug].views = r.n;
        for (const r of c.results || []) stats[r.slug].comments = r.n;
        return json(req, { stats }, 200, { "Cache-Control": "public, max-age=60" });
      }
      if (p === "/v1/popular" && req.method === "GET") {
        const days = Math.min(30, Math.max(1, parseInt(url.searchParams.get("days") || "7", 10) || 7));
        const limit = Math.min(20, Math.max(1, parseInt(url.searchParams.get("limit") || "5", 10) || 5));
        const since = kstDay(now - (days - 1) * 864e5);
        const r = await db.prepare("SELECT slug, SUM(n) AS n FROM views_daily WHERE day >= ? GROUP BY slug ORDER BY n DESC LIMIT ?").bind(since, limit).all();
        return json(req, { days, items: r.results || [] }, 200, { "Cache-Control": "public, max-age=300" });
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
      if (p === "/v1/comments" && req.method === "GET") {
        const slug = url.searchParams.get("slug") || "";
        if (!SLUG_RE.test(slug)) return json(req, { error: "slug" }, 400);
        const sort = url.searchParams.get("sort") === "top" ? "likes DESC, created DESC" : "created DESC";
        const list = await db.prepare(`SELECT * FROM comments WHERE slug = ? AND status = 'ok' ORDER BY ${sort} LIMIT 200`).bind(slug).all();
        const best = await db.prepare("SELECT * FROM comments WHERE slug = ? AND status = 'ok' AND likes >= ? ORDER BY likes DESC, created ASC LIMIT ?")
          .bind(slug, LIMITS.bestMinLikes, LIMITS.bestCount).all();
        const liked = await db.prepare("SELECT l.cid FROM comment_likes l JOIN comments c ON c.id = l.cid WHERE c.slug = ? AND l.ih = ?").bind(slug, ih).all();
        return json(req, {
          comments: (list.results || []).map((c) => publicComment(c, ih)),
          best: (best.results || []).map((c) => publicComment(c, ih)),
          liked: (liked.results || []).map((x) => x.cid),
          me: `익명#${ih.slice(0, 4)}`,
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
        let nick = cleanText(b.nick, LIMITS.nickMax).replace(/\s+/g, " ");
        if (!nick || /운영자|관리자|김박사/.test(nick) || needsHold(nick)) nick = `익명#${ih.slice(0, 4)}`;
        const recent = await db.prepare("SELECT SUM(created > ?) AS m, COUNT(*) AS d FROM comments WHERE ih = ? AND created > ?")
          .bind(now - 60e3, ih, now - 864e5).first();
        if ((recent?.m || 0) >= LIMITS.perMinute || (recent?.d || 0) >= LIMITS.perDay)
          return json(req, { error: "rate", message: "잠시 뒤에 다시 써 주세요." }, 429);
        const status = needsHold(body) ? "held" : "ok";
        const r = await db.prepare("INSERT INTO comments (slug, nick, body, ih, created, status) VALUES (?, ?, ?, ?, ?, ?)")
          .bind(slug, nick, body, ih, now, status).run();
        return json(req, {
          ok: true, status, id: r.meta?.last_row_id,
          message: status === "held" ? "링크·연락처·홍보로 보이는 내용이 있어 확인 뒤 게시됩니다." : "",
        });
      }
      const m = p.match(/^\/v1\/comments\/(\d+)\/(like|report)$/);
      if (m && req.method === "POST") {
        const cid = parseInt(m[1], 10);
        const c = await db.prepare("SELECT id, ih, status FROM comments WHERE id = ?").bind(cid).first();
        if (!c || c.status !== "ok") return json(req, { error: "not_found" }, 404);
        if (m[2] === "like") {
          if (c.ih === ih) return json(req, { error: "own", message: "내 댓글에는 좋아요를 누를 수 없습니다." }, 400);
          const ins = await db.prepare("INSERT OR IGNORE INTO comment_likes (cid, ih) VALUES (?, ?)").bind(cid, ih).run();
          if (ins.meta?.changes) await db.prepare("UPDATE comments SET likes = likes + 1 WHERE id = ?").bind(cid).run();
          else {
            await db.prepare("DELETE FROM comment_likes WHERE cid = ? AND ih = ?").bind(cid, ih).run(); // 한 번 더 누르면 취소
            await db.prepare("UPDATE comments SET likes = MAX(likes - 1, 0) WHERE id = ?").bind(cid).run();
          }
          const row = await db.prepare("SELECT likes FROM comments WHERE id = ?").bind(cid).first();
          return json(req, { likes: row.likes, liked: !!ins.meta?.changes });
        }
        const ins = await db.prepare("INSERT OR IGNORE INTO comment_reports (cid, ih) VALUES (?, ?)").bind(cid, ih).run();
        if (ins.meta?.changes) {
          await db.prepare("UPDATE comments SET reports = reports + 1, status = CASE WHEN reports + 1 >= ? THEN 'hidden' ELSE status END WHERE id = ?")
            .bind(LIMITS.reportHide, cid).run();
        }
        return json(req, { ok: true });
      }
      if (p.startsWith("/v1/comments/") && p.endsWith("/delete") && req.method === "POST") {
        const cid = parseInt(p.split("/")[3], 10);
        const r = await db.prepare("UPDATE comments SET status = 'deleted' WHERE id = ? AND ih = ?").bind(cid, ih).run();
        return json(req, { ok: !!r.meta?.changes });
      }

      // ---------- 관리 (Authorization: Bearer ADMIN_TOKEN) ----------
      if (p.startsWith("/v1/admin/")) {
        const auth = req.headers.get("Authorization") || "";
        if (!env.ADMIN_TOKEN || auth !== `Bearer ${env.ADMIN_TOKEN}`) return json(req, { error: "auth" }, 401);
        if (p === "/v1/admin/queue" && req.method === "GET") {
          const r = await db.prepare("SELECT id, slug, nick, body, likes, reports, status, created FROM comments WHERE status IN ('held','hidden') ORDER BY created DESC LIMIT 200").all();
          return json(req, { items: r.results || [] });
        }
        const am = p.match(/^\/v1\/admin\/comments\/(\d+)$/);
        if (am && req.method === "POST") {
          const { status } = await readJson(req);
          if (!["ok", "held", "hidden", "deleted"].includes(status)) return json(req, { error: "status" }, 400);
          const r = await db.prepare("UPDATE comments SET status = ?, reports = CASE WHEN ? = 'ok' THEN 0 ELSE reports END WHERE id = ?").bind(status, status, parseInt(am[1], 10)).run();
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
