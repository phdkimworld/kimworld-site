// API 검사: node worker/test/test_worker.mjs
// Cloudflare D1과 같은 모양(prepare/bind/first/all/run/batch)을 node 내장 SQLite로 흉내 내어 실제 코드를 돌린다.
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import worker, { needsHold } from "../src/index.js";

const sqlite = new DatabaseSync(":memory:");
import { readdirSync } from "node:fs";
for (const f of readdirSync(new URL("../migrations/", import.meta.url)).filter((x) => x.endsWith(".sql")).sort())
  sqlite.exec(readFileSync(new URL("../migrations/" + f, import.meta.url), "utf8"));
function stmt(sql, args = []) {
  return {
    bind: (...a) => stmt(sql, a),
    first: async () => sqlite.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: sqlite.prepare(sql).all(...args) }),
    run: async () => {
      const r = sqlite.prepare(sql).run(...args);
      return { meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
    },
  };
}
const DB = { prepare: (sql) => stmt(sql), batch: async (list) => Promise.all(list.map((s) => s.run())) };
const env = { DB, SALT: "test-salt", ADMIN_TOKEN: "adm", GOOGLE_CLIENT_ID: "gid", GOOGLE_CLIENT_SECRET: "gsec", KAKAO_REST_KEY: "kkey" };
// 구글·카카오 서버 흉내
const b64u = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
globalThis.fetch = async (u, opt = {}) => {
  u = String(u);
  if (u.startsWith("https://oauth2.googleapis.com/token")) {
    const code = new URLSearchParams(String(opt.body)).get("code");
    if (code === "bad") return new Response(JSON.stringify({ error: "invalid_grant" }));
    const aud = code === "wrongaud" ? "other" : "gid";
    return new Response(JSON.stringify({ id_token: "h." + b64u({ iss: "https://accounts.google.com", aud, sub: "g-" + code }) + ".s" }));
  }
  if (u.startsWith("https://kauth.kakao.com/oauth/token")) return new Response(JSON.stringify({ access_token: "at-" + new URLSearchParams(String(opt.body)).get("code") }));
  if (u.startsWith("https://kapi.kakao.com/v2/user/me")) return new Response(JSON.stringify({ id: 4242 }));
  throw new Error("unexpected fetch " + u);
};

let fails = 0;
const check = (cond, msg) => { console.log((cond ? "  ok  " : "  FAIL ") + msg); if (!cond) fails++; };
// 기기 번호(d=)는 따로 주지 않으면 IP마다 다른 기기로 본다(기존 검사가 "IP = 사람"으로 짜여 있어서)
const devOf = (ip) => ("dev" + ip.replace(/\./g, "_") + "_".repeat(30)).slice(0, 30);
async function call(method, path, { body, ip = "1.1.1.1", dev, auth, cookie, origin = "https://drkimworld.com" } = {}) {
  const headers = { "CF-Connecting-IP": ip, Origin: origin, "Content-Type": "application/json" };
  if (auth) headers.Authorization = auth;
  if (cookie) headers.Cookie = cookie;
  const d = dev === null ? "" : (dev || devOf(ip));
  const u = "https://api.drkimworld.com" + path + (d ? (path.includes("?") ? "&" : "?") + "d=" + d : "");
  const res = await worker.fetch(new Request(u, { method, headers, body: body ? JSON.stringify(body) : undefined }), env);
  return { status: res.status, data: await res.json().catch(() => null), headers: res.headers };
}
// 소셜 로그인: 시작 → (구글·카카오 화면) → 돌아오기. 쿠키를 돌려준다
async function login(prov, code, ip = "80.0.0.1", ret = "/t/xndu/#board") {
  const st = await call("GET", `/v1/auth/${prov}/start?return=${encodeURIComponent(ret)}`, { ip, dev: null });
  const state = new URL(st.headers.get("Location")).searchParams.get("state");
  const cb = await call("GET", `/v1/auth/${prov}/callback?code=${code}&state=${state}`, { ip, dev: null });
  const sc = cb.headers.get("Set-Cookie") || "";
  return { cookie: (sc.match(/kw_s=[0-9a-f]{64}/) || [""])[0], location: cb.headers.get("Location"), start: st.headers.get("Location") };
}

console.log("조회수");
let r = await call("POST", "/v1/view", { body: { slug: "rgti-2026-10" } });
check(r.data.views === 1, "첫 조회 1");
r = await call("POST", "/v1/view", { body: { slug: "rgti-2026-10" } });
check(r.data.views === 1, "같은 사람 같은 날 다시 보면 그대로");
r = await call("POST", "/v1/view", { body: { slug: "rgti-2026-10" }, ip: "2.2.2.2" });
check(r.data.views === 2, "다른 사람이면 2");
await call("POST", "/v1/view", { body: { slug: "soun-2026-10" }, ip: "3.3.3.3" });
r = await call("POST", "/v1/view", { body: { slug: "../etc" } });
check(r.status === 400, "이상한 주소는 거절");
r = await call("GET", "/v1/popular?days=7&limit=5");
check(r.data.items[0].slug === "rgti-2026-10" && r.data.items[0].n === 2 && r.data.items.length === 2, "7일 인기 순서");
check(r.headers.get("Access-Control-Allow-Origin") === "https://drkimworld.com", "사이트 주소에서만 읽기 허용(CORS)");
r = await call("GET", "/v1/stats?slugs=rgti-2026-10,soun-2026-10,none-2026-01");
check(r.data.stats["rgti-2026-10"].views === 2 && r.data.stats["none-2026-01"].views === 0, "여러 글 조회수 한 번에");
const ipRow = (await DB.prepare("SELECT * FROM view_seen").all()).results.map((x) => JSON.stringify(x)).join();
check(!ipRow.includes("1.1.1.1"), "IP 원문은 저장하지 않음");

console.log("댓글");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", nick: "개미1", body: "정부 지분 얘기 흥미롭네요", t: 8000 } });
check(r.data.ok && r.data.status === "ok", "일반 댓글 바로 게시");
const c1 = r.data.id;
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", nick: "홍보", body: "무료 종목 추천 카톡 문의주세요 010-1234-5678", t: 8000 }, ip: "4.4.4.4" });
check(r.data.status === "held" && /확인 뒤/.test(r.data.message), "연락처·추천 문구는 자동 보류");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "링크 https://x.example 확인", t: 8000 }, ip: "5.5.5.5" });
check(r.data.status === "held", "링크는 자동 보류");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "봇", website: "spam", t: 9000 }, ip: "6.6.6.6" });
const bot = (await DB.prepare("SELECT COUNT(*) AS n FROM comments WHERE ih IN (SELECT ih FROM comments) AND body = '봇'").first()).n;
check(bot === 0, "숨은 칸을 채운 로봇 글은 저장 안 함");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "너무 빠름", t: 500 }, ip: "7.7.7.7" });
check(r.status === 429, "쓰기 시작 3초 안에 보내면 거절");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", nick: "운영자", body: "운영자 사칭 시험", t: 8000 }, ip: "8.8.8.8" });
let list = await call("GET", "/v1/comments?slug=b-rgti", { ip: "8.8.8.8" });
check(list.data.comments.some((c) => c.nick.startsWith("익명#") && c.body.includes("사칭")), "운영자·김박사 닉네임은 익명으로 바뀜");
check(list.data.comments.every((c) => !("ih" in c)), "해시값은 화면에 보내지 않음");
await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "두 번째", t: 8000 }, ip: "9.9.9.9" });
await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "세 번째", t: 8000 }, ip: "9.9.9.9" });
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "네 번째", t: 8000 }, ip: "9.9.9.9" });
check(r.status === 429, "1분에 2개 넘으면 잠시 막음");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "<script>alert(1)</script> 그대로 글자로", t: 8000 }, ip: "10.0.0.1" });
list = await call("GET", "/v1/comments?slug=b-rgti");
check(list.data.comments.length === 5 && !list.data.comments.some((c) => /010|https/.test(c.body)), "보류 글은 목록에 안 나옴(게시 5, 보류 2)");

console.log("좋아요·인기 댓글");
for (const ip of ["11.0.0.1", "11.0.0.2", "11.0.0.3"]) await call("POST", `/v1/comments/${c1}/like`, { ip });
r = await call("POST", `/v1/comments/${c1}/like`, { ip: "11.0.0.3" });
check(r.data.likes === 2 && r.data.liked === false, "같은 사람이 다시 누르면 취소");
r = await call("POST", `/v1/comments/${c1}/like`, { ip: "11.0.0.3" });
check(r.data.likes === 3 && r.data.liked === true, "다시 누르면 좋아요");
r = await call("POST", `/v1/comments/${c1}/like`, { ip: "1.1.1.1" });
check(r.status === 400, "내 댓글에는 좋아요 불가");
list = await call("GET", "/v1/comments?slug=b-rgti&sort=top", { ip: "11.0.0.1" });
check(list.data.best.length === 1 && list.data.best[0].id === c1, "좋아요 3개 이상이면 베스트 댓글");
check(list.data.comments[0].id === c1, "인기순 정렬");
check(list.data.liked.includes(c1), "내가 누른 좋아요 표시");

console.log("신고·삭제·관리");
const victim = list.data.comments.find((c) => c.body.includes("두 번째")).id;
for (const ip of ["12.0.0.1", "12.0.0.2"]) await call("POST", `/v1/comments/${victim}/report`, { ip });
await call("POST", `/v1/comments/${victim}/report`, { ip: "12.0.0.2" });
list = await call("GET", "/v1/comments?slug=b-rgti");
check(list.data.comments.some((c) => c.id === victim), "같은 사람 중복 신고는 한 번만(2건이면 유지)");
await call("POST", `/v1/comments/${victim}/report`, { ip: "12.0.0.3" });
list = await call("GET", "/v1/comments?slug=b-rgti");
check(!list.data.comments.some((c) => c.id === victim), "신고 3건이면 숨김");
r = await call("POST", `/v1/comments/${c1}/delete`, { ip: "9.9.9.9" });
check(r.data.ok === false, "남의 댓글은 삭제 불가");
r = await call("GET", "/v1/admin/queue");
check(r.status === 401, "관리 기능은 토큰 없으면 거절");
r = await call("GET", "/v1/admin/queue", { auth: "Bearer adm" });
check(r.data.items.length === 3, "관리 대기열: 보류 2 + 숨김 1");
r = await call("POST", `/v1/admin/comments/${victim}`, { auth: "Bearer adm", body: { status: "ok" } });
list = await call("GET", "/v1/comments?slug=b-rgti");
check(r.data.ok && list.data.comments.some((c) => c.id === victim), "관리자가 다시 게시");
r = await call("POST", `/v1/comments/${c1}/delete`, { ip: "1.1.1.1" });
list = await call("GET", "/v1/comments?slug=b-rgti");
check(r.data.ok && !list.data.comments.some((c) => c.id === c1), "내 댓글은 내가 삭제");

console.log("홈 화면용");
r = await call("GET", "/v1/comments/recent?limit=3");
check(r.data.items.length === 3 && r.data.items.every((c) => !("ih" in c) && c.slug && !/010|https/.test(c.body)), "최근 댓글 3개(보류·숨김 제외, 해시 없음)");
check(r.data.items[0].created >= r.data.items[1].created, "최근 댓글은 새 글 먼저");
r = await call("GET", "/v1/popular?days=1&limit=50");
check(r.data.items[0].today === 2 && r.data.days === 1, "오늘 조회수(today) 함께 보냄");

console.log("리포트 좋아요·답글·피드 숫자");
r = await call("POST", "/v1/like", { body: { slug: "rgti-2026-10" }, ip: "30.0.0.1" });
check(r.data.likes === 1 && r.data.liked === true, "리포트 좋아요");
await call("POST", "/v1/like", { body: { slug: "rgti-2026-10" }, ip: "30.0.0.2" });
r = await call("POST", "/v1/like", { body: { slug: "rgti-2026-10" }, ip: "30.0.0.1" });
check(r.data.likes === 1 && r.data.liked === false, "다시 누르면 취소");
list = await call("GET", "/v1/comments?slug=b-rgti");
const root = list.data.comments.find((c) => !c.parent).id;
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "답글입니다", parent: root, t: 8000 }, ip: "31.0.0.1" });
check(r.data.ok, "답글 등록");
const reply = r.data.id;
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "답글의 답글", parent: reply, t: 8000 }, ip: "31.0.0.2" });
list = await call("GET", "/v1/comments?slug=b-rgti");
check(list.data.comments.filter((c) => c.parent === root).length === 2, "답글의 답글은 원래 댓글 아래로(한 단계)");
r = await call("POST", "/v1/comments", { body: { slug: "b-soun", body: "다른 글 답글", parent: root, t: 8000 }, ip: "31.0.0.3" });
check(r.status === 400, "다른 글의 댓글에는 답글 불가");
// 커뮤니티 하나: 리포트에 바로 다는 댓글은 없고, 리포트를 공유(문장 없이)·인용한 커뮤니티 글이 '이 리포트 이야기'
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "리포트에 바로 다는 댓글", t: 8000 }, ip: "32.0.0.1" });
check(r.status === 400 && r.data.error === "community", "리포트 주소로는 글을 못 씀(커뮤니티 글로)");
r = await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "이 리포트 정리 좋네요", quote: { kind: "r", ref: "rgti-2026-10", text: "" }, t: 8000 }, ip: "32.0.0.2" });
check(r.data.ok && r.data.status === "ok", "리포트 공유 글(인용 문장 없이)");
const shareId = r.data.id;
await call("POST", `/v1/comments/${shareId}/like`, { ip: "32.0.0.3" });
r = await call("POST", "/v1/comments", { body: { slug: "b-talk", body: "핵심은 여기", quote: { kind: "r", ref: "rgti-2026-10", text: "정부 지분 참여 가능성" }, t: 8000 }, ip: "32.0.0.4" });
check(r.data.ok, "리포트 인용 글(종목 없이 올려도 됨)");
await call("POST", "/v1/comments", { body: { slug: "b-rgti", body: "공유 글에 단 답글", parent: shareId, t: 8000 }, ip: "32.0.0.5" });
r = await call("POST", "/v1/comments", { body: { slug: "b-talk", body: "빈 인용", quote: { kind: "p", ref: shareId, text: "" }, t: 8000 }, ip: "32.0.0.6" });
check(r.status === 400, "남의 글 인용은 문장이 있어야 함");
r = await call("GET", "/v1/feed?about=rgti-2026-10");
check(r.data.items.length === 2 && r.data.items.every((x) => x.quote && x.quote.ref === "rgti-2026-10") && r.data.items.some((x) => x.quote.text === ""), "리포트 이야기 목록 = 그 리포트를 공유·인용한 글(답글 제외)");
r = await call("GET", "/v1/feed?board=b-rgti");
check(r.data.items.length >= 2 && r.data.items.every((x) => x.slug === "b-rgti"), "종목 커뮤니티 목록");
r = await call("GET", "/v1/stats?slugs=rgti-2026-10,soun-2026-10", { ip: "30.0.0.2" });
const st = r.data.stats["rgti-2026-10"];
check(st.likes === 1 && st.liked === true && st.comments === 2 && st.top && st.top.id === shareId, "리포트 숫자: 좋아요·내 좋아요·이야기 글 수·대표 글(좋아요 많은 것)");
check(r.data.stats["soun-2026-10"].top === null && r.headers.get("Cache-Control") === "no-store", "댓글 없으면 대표 댓글 없음, 개인별 값이라 캐시 안 함");

console.log("통신사 공용 IP(여러 사람이 같은 IP)");
r = await call("POST", "/v1/comments", { body: { slug: "b-cgnat", body: "A가 쓴 댓글", t: 8000 }, ip: "50.0.0.1", dev: "deviceA_aaaaaaaaaaaaaaaaaaaa" });
const ca = r.data.id;
list = await call("GET", "/v1/comments?slug=b-cgnat", { ip: "50.0.0.1", dev: "deviceB_bbbbbbbbbbbbbbbbbbbb" });
check(list.data.comments[0].mine === false, "같은 IP의 다른 사람에게는 '내 댓글'로 안 보임");
r = await call("POST", `/v1/comments/${ca}/delete`, { ip: "50.0.0.1", dev: "deviceB_bbbbbbbbbbbbbbbbbbbb" });
check(r.data.ok === false, "같은 IP의 다른 사람은 삭제 불가");
r = await call("POST", `/v1/comments/${ca}/like`, { ip: "50.0.0.1", dev: "deviceB_bbbbbbbbbbbbbbbbbbbb" });
check(r.data.likes === 1, "같은 IP의 다른 사람도 좋아요 가능");
r = await call("POST", "/v1/comments", { body: { slug: "b-cgnat", body: "B도 씀", t: 8000 }, ip: "50.0.0.1", dev: "deviceB_bbbbbbbbbbbbbbbbbbbb" });
check(r.data.ok, "같은 IP의 다른 사람도 댓글 가능(1분 2개는 기기 기준)");
list = await call("GET", "/v1/comments?slug=b-cgnat", { ip: "50.0.0.1", dev: "deviceA_aaaaaaaaaaaaaaaaaaaa" });
check(list.data.comments.find((c) => c.id === ca).mine === true, "쓴 사람에게는 '내 댓글'");
await call("POST", `/v1/comments/${ca}/report`, { ip: "60.0.0.1", dev: "rep1_xxxxxxxxxxxxxxxxxxxxxxx" });
await call("POST", `/v1/comments/${ca}/report`, { ip: "60.0.0.1", dev: "rep2_xxxxxxxxxxxxxxxxxxxxxxx" });
await call("POST", `/v1/comments/${ca}/report`, { ip: "60.0.0.1", dev: "rep3_xxxxxxxxxxxxxxxxxxxxxxx" });
list = await call("GET", "/v1/comments?slug=b-cgnat");
check(list.data.comments.some((c) => c.id === ca), "기기 번호만 바꿔 같은 IP에서 신고 3번 해도 숨겨지지 않음");
const rows = JSON.stringify((await DB.prepare("SELECT * FROM comments").all()).results) + JSON.stringify((await DB.prepare("SELECT * FROM view_seen").all()).results);
check(!rows.includes("50.0.0.1") && !rows.includes("deviceA"), "IP·기기 번호 원문은 저장 안 함");
const pep = await DB.prepare("SELECT COUNT(*) AS n FROM peppers").first();
check(pep.n === 1, "그날의 무작위 값 하나만 보관");
r = await call("GET", "/v1/admin/queue", { auth: "Bearer adx" });
check(r.status === 401, "관리 토큰이 한 글자만 달라도 거절");

console.log("소셜 로그인·계정·종토방·팔로우·알림");
let r0 = await call("GET", "/v1/me", { ip: "80.0.0.1" });
check(r0.data.user === null && r0.data.loggedIn === false && r0.data.providers.join() === "google,kakao", "처음엔 로그인 안 됨, 켜진 로그인 종류");
const LA = await login("google", "alice");
check(LA.start.startsWith("https://accounts.google.com/") && LA.start.includes("scope=openid&") && !LA.start.includes("email"), "구글은 회원 번호(openid)만 요청");
check(/^kw_s=[0-9a-f]{64}$/.test(LA.cookie) && LA.location === "https://drkimworld.com/t/xndu/?login=ok#board", "로그인 뒤 쿠키를 받고 원래 자리로");
const bad = await login("google", "wrongaud");
check(!bad.cookie && bad.location.includes("login=fail"), "다른 앱의 토큰은 거절");
let r1 = await call("GET", `/v1/auth/google/callback?code=alice&state=forged`, { ip: "80.0.0.1" });
check(!r1.headers.get("Set-Cookie") && r1.headers.get("Location").includes("login=fail"), "위조한 state 거절");
r1 = await call("POST", "/v1/me", { body: { nick: "퀀텀개미" }, ip: "80.0.0.1" });
check(r1.status === 401, "로그인 없이 계정 만들기 불가");
await call("POST", "/v1/comments", { body: { slug: "b-pre", body: "로그인 전 익명 댓글", t: 8000 }, ip: "80.0.0.1", dev: "devAlice_aaaaaaaaaaaaaaaaaa" });
r1 = await call("POST", "/v1/me", { body: { nick: "운영자" }, ip: "80.0.0.1", cookie: LA.cookie, dev: "devAlice_aaaaaaaaaaaaaaaaaa" });
check(r1.status === 400, "운영자 사칭 닉네임 거절");
r1 = await call("POST", "/v1/me", { body: { nick: "퀀텀개미", bio: "양자컴퓨팅 공부 중" }, ip: "80.0.0.1", cookie: LA.cookie, dev: "devAlice_aaaaaaaaaaaaaaaaaa" });
check(r1.data.ok && r1.data.user.nick === "퀀텀개미", "로그인 후 닉네임 정하기");
const uA = r1.data.user.id;
r1 = await call("POST", "/v1/me", { body: { nick: "퀀텀개미" }, ip: "80.0.0.1", cookie: LA.cookie, origin: "https://evil.example" });
check(r1.status === 403, "다른 사이트에서 보낸 로그인 요청 거절");
list = await call("GET", "/v1/comments?slug=b-pre", { ip: "80.0.0.1", cookie: LA.cookie });
check(list.data.comments.some((c) => c.uid === uA && c.nick === "퀀텀개미" && c.mine), "로그인 전 이 기기의 댓글이 계정으로 이어지고 '내 글'");
sqlite.exec("DELETE FROM comments"); // 앞의 시험 글은 지운다(아래 피드 순위·새 계정 제한 시험이 깨끗한 상태에서 돌게)
const LA2 = await login("google", "alice", "80.0.0.9");
r1 = await call("GET", "/v1/me", { ip: "80.0.0.9", cookie: LA2.cookie, dev: "otherdevice_xxxxxxxxxxxxxx" });
check(r1.data.user && r1.data.user.id === uA, "다른 기기에서 같은 구글 계정으로 로그인하면 같은 계정");
const LB = await login("kakao", "bob", "80.0.0.2");
check(LB.start.startsWith("https://kauth.kakao.com/oauth/authorize?") && !LB.start.includes("scope"), "카카오는 동의 항목 없이(회원 번호만)");
r1 = await call("POST", "/v1/me", { body: { nick: "장투러" }, ip: "80.0.0.2", cookie: LB.cookie });
const uB = r1.data.user.id;
// 닉네임 변경: 14일에 한 번, 규칙·중복 검사, 지난 글 이름도 함께
r1 = await call("POST", "/v1/me", { body: { nick: "장기투자자" }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.status === 429 && r1.data.error === "nick_wait", "가입 직후에는 14일 동안 닉네임 변경 불가");
sqlite.exec(`UPDATE users SET created = created - 15 * 86400000 WHERE id = ${uB}`);
r1 = await call("POST", "/v1/me", { body: { nick: "퀀텀개미" }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.status === 409, "남이 쓰는 닉네임으로는 못 바꿈");
r1 = await call("POST", "/v1/me", { body: { nick: "김박사짱" }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.status === 400, "운영자 흉내 닉네임으로는 못 바꿈");
r1 = await call("POST", "/v1/me", { body: { nick: "장기투자자", bio: "소개" }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.data.ok && r1.data.user.nick === "장기투자자" && r1.data.user.nickNext > Date.now() + 13 * 864e5, "14일 지나면 바꿀 수 있고 다음 변경은 14일 뒤");
r1 = await call("POST", "/v1/me", { body: { nick: "장투러" }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.status === 429, "바꾼 뒤 14일 안에는 다시 못 바꿈");
r1 = await call("POST", "/v1/me", { body: { bio: "소개만 바꾸기" }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.data.ok && r1.data.user.bio === "소개만 바꾸기", "소개는 언제든 바꿈");
sqlite.exec(`UPDATE users SET nick = '장투러', nick_lc = '장투러' WHERE id = ${uB}`); // 이후 검사를 위해 원래대로
r1 = await call("POST", "/v1/comments", { body: { slug: "b-xndu", body: "로그인 없이 종토방 글", t: 8000 }, ip: "80.0.0.3" });
check(r1.data.ok && r1.data.status === "ok", "로그인 없이도 종토방에 익명 글");
const savedKeys = [env.GOOGLE_CLIENT_ID, env.KAKAO_REST_KEY];
env.GOOGLE_CLIENT_ID = ""; env.KAKAO_REST_KEY = "";
r1 = await call("POST", "/v1/comments", { body: { slug: "b-anon", nick: "지나가던개미", body: "로그인 준비 중에는 익명 글", t: 8000 }, ip: "80.0.0.4" });
check(r1.data.ok && r1.data.status === "ok", "로그인을 아직 안 켰으면 종토방도 익명으로 씀");
[env.GOOGLE_CLIENT_ID, env.KAKAO_REST_KEY] = savedKeys;
r1 = await call("POST", "/v1/comments", { body: { slug: "b-xndu", body: "요크빌 매각 규모가 관건이네요", t: 8000 }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.ok, "계정으로 종토방 글");
const post = r1.data.id;
r1 = await call("POST", "/v1/comments", { body: { slug: "b-xndu", body: "두 번째 글", t: 8000 }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.status === 429, "새 계정은 종토방 글 10분에 한 번");
await call("POST", "/v1/comments", { body: { slug: "b-xndu", body: "동의합니다", parent: post, t: 8000 }, ip: "80.0.0.2", cookie: LB.cookie });
await call("POST", `/v1/comments/${post}/like`, { ip: "80.0.0.2", cookie: LB.cookie });
r1 = await call("POST", "/v1/follow", { body: { uid: uA }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.data.following === true && r1.data.followers === 1, "팔로우");
r1 = await call("GET", "/v1/me", { ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.unread === 3, "알림 3개: 답글·좋아요·팔로우");
await call("POST", "/v1/notifications/read", { ip: "80.0.0.1", cookie: LA.cookie });
r1 = await call("GET", "/v1/feed/following", { ip: "80.0.0.2", cookie: LB.cookie });
check(r1.data.items.length >= 1 && r1.data.items.every((x) => x.uid === uA), "팔로잉 소식");
r1 = await call("GET", `/v1/users/${uA}`, { ip: "80.0.0.2", cookie: LB.cookie });
check(r1.data.user.nick === "퀀텀개미" && r1.data.following === true && !("actor" in r1.data.user), "프로필(로그인 정보는 안 보냄)");
sqlite.exec("INSERT INTO comments (slug, nick, body, ih, did, created, status, pinned) VALUES ('b-xndu', '김박사 월드', '[공지] 종토방 규칙', 'notice', 'notice', 1, 'ok', 1)");
list = await call("GET", "/v1/comments?slug=b-xndu&sort=new");
check(list.data.comments[0].pinned === true && list.data.comments[0].nick === "김박사 월드", "공지는 맨 위");
r1 = await call("GET", "/v1/comments/recent?kind=board&limit=5");
check(r1.data.items.length >= 1 && !r1.data.items.some((x) => x.body.includes("공지")), "홈 종토방 새 글에는 공지 제외");
// 홈 피드: 종토방·라운지 원글만(답글·공지·리포트 댓글 제외), 팔로잉 탭, 더 보기, 새 글 수, 글 상세, 팔로우 추천
sqlite.exec(`UPDATE users SET created = created - 3 * 86400000 WHERE id = ${uB}`); // 새 계정 제한이 끝난 뒤로
r1 = await call("POST", "/v1/comments", { body: { slug: "b-talk", body: "라운지 첫 글입니다", t: 8000 }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.data.ok, "라운지(종목 없는 글)도 계정으로 씀");
const talk = r1.data.id;
let fd = await call("GET", "/v1/feed?tab=all", { ip: "80.0.0.7" });
check(fd.data.items.length >= 2 && fd.data.items[0].id === talk && fd.data.items.every((x) => x.slug.startsWith("b-")), "피드: 최신 원글부터, 종토방·라운지만");
check(!fd.data.items.some((x) => /공지|동의합니다/.test(x.body)), "피드에 공지·답글은 안 나옴");
const fp = fd.data.items.find((x) => x.id === post);
check(fp && fp.replies === 1 && fp.likes === 1 && fp.liked === false, "피드 글마다 답글 수·좋아요 수");
fd = await call("GET", "/v1/feed?tab=all", { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.items.find((x) => x.id === post).liked === true && fd.data.items.find((x) => x.id === talk).mine === true, "내가 누른 좋아요·내 글 표시");
fd = await call("GET", "/v1/feed?tab=all&rank=hot", { ip: "80.0.0.7" });
check(fd.data.hot === true && fd.data.items[0].id === post && fd.data.items[0].top && fd.data.items[0].top.body === "동의합니다", "추천 순위: 반응 많은 글이 위, 대표 답글 미리보기");
const hot2 = await call("GET", "/v1/feed?tab=all&rank=hot&limit=1&offset=1", { ip: "80.0.0.7" });
check(hot2.data.items.length === 1 && hot2.data.items[0].id !== post, "추천 순위 더 보기는 순번으로");
fd = await call("GET", "/v1/feed?tab=all&limit=1", { ip: "80.0.0.7" });
check(fd.data.items.length === 1 && fd.data.more === true, "한 번에 정한 개수만, 더 있으면 more");
const fd2 = await call("GET", `/v1/feed?tab=all&limit=1&before=${fd.data.items[0].created}`, { ip: "80.0.0.7" });
check(fd2.data.items.length === 1 && fd2.data.items[0].id !== fd.data.items[0].id, "더 보기는 그 앞 시각부터");
fd = await call("GET", "/v1/feed?tab=following", { ip: "80.0.0.7" });
check(fd.data.items.length === 0, "로그인 안 하면 팔로잉 탭은 비어 있음");
fd = await call("GET", "/v1/feed?tab=following", { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.items.some((x) => x.uid === uA) && fd.data.items.some((x) => x.id === talk) && fd.data.items.every((x) => x.uid === uA || x.uid === uB), "팔로잉 탭: 팔로우한 사람 + 내 글");
fd = await call("GET", "/v1/feed/new?tab=all&since=0", { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.n >= 1 && fd.data.n < 4, "새 글 수(내 글은 빼고 셈)");
fd = await call("GET", "/v1/feed/new?tab=all&since=" + (Date.now() + 1000), { ip: "80.0.0.7" });
check(fd.data.n === 0, "그 뒤 새 글 없으면 0");
const rpl = (await call("GET", `/v1/comments?slug=b-xndu&sort=new`)).data.comments.find((c) => c.body === "동의합니다");
fd = await call("GET", `/v1/post/${rpl.id}`, { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.post.id === post && fd.data.post.slug === "b-xndu" && fd.data.replies.length === 1 && fd.data.replies[0].mine && fd.data.liked.includes(post), "글 상세: 답글 번호로 열어도 원글 + 답글, 내 좋아요");
fd = await call("GET", `/v1/post/999999`);
check(fd.status === 404, "없는 글은 404");
// 리포스트: 리포트·남의 글, 다시 누르면 취소, 내 글 불가, 로그인 필요, 알림·프로필·팔로잉 피드
r1 = await call("POST", "/v1/repost", { body: { kind: "r", ref: "xndu-2026-10" }, ip: "80.0.0.7" });
check(r1.status === 401, "로그인 없이 리포스트 불가");
r1 = await call("POST", "/v1/repost", { body: { kind: "p", ref: talk }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.status === 400, "내 글은 리포스트 불가");
r1 = await call("POST", "/v1/repost", { body: { kind: "p", ref: talk }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.reposted === true && r1.data.count === 1, "남의 글 리포스트");
r1 = await call("POST", "/v1/repost", { body: { kind: "r", ref: "xndu-2026-10" }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.reposted === true, "리포트 리포스트");
r1 = await call("POST", "/v1/repost", { body: { kind: "r", ref: "b-xndu" }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.status === 400, "종토방 묶음 이름은 리포트로 리포스트 불가");
fd = await call("GET", "/v1/stats?slugs=xndu-2026-10", { ip: "80.0.0.1", cookie: LA.cookie });
check(fd.data.stats["xndu-2026-10"].reposts === 1 && fd.data.stats["xndu-2026-10"].reposted === true, "리포트 리포스트 수·내가 했는지");
fd = await call("GET", "/v1/feed?tab=all", { ip: "80.0.0.1", cookie: LA.cookie });
check(fd.data.items.find((x) => x.id === talk).reposts === 1 && fd.data.items.find((x) => x.id === talk).reposted === true, "피드 글에 리포스트 수·내가 했는지");
fd = await call("GET", "/v1/feed?tab=following", { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.reposts.some((x) => x.type === "report" && x.slug === "xndu-2026-10" && x.rp.uid === uA) && fd.data.reposts.some((x) => x.id === talk && x.rp.nick), "팔로잉 탭에 팔로우한 사람의 리포스트");
fd = await call("GET", `/v1/users/${uA}`, { ip: "80.0.0.7" });
check(fd.data.reposts.length === 2 && fd.data.reposts.some((x) => x.kind === "p" && x.post.id === talk), "프로필에 리포스트 목록");
fd = await call("GET", "/v1/notifications", { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.items.some((x) => x.type === "repost" && x.ref === String(talk)), "글쓴이에게 리포스트 알림");
r1 = await call("POST", "/v1/repost", { body: { kind: "r", ref: "xndu-2026-10" }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.reposted === false && r1.data.count === 0, "다시 누르면 리포스트 취소");
// 인용: 리포트·남의 글 일부를 붙여 새 글. 남의 글은 실제로 있는 문장만, 홍보 문구는 보류, 글쓴이에게 알림
r1 = await call("POST", "/v1/comments", { body: { slug: "b-xndu", body: "이 대목이 핵심 같아요", quote: { kind: "r", ref: "xndu-2026-10", text: "요크빌 매각 대금이 현금의 절반을 넘는다" }, t: 8000 }, ip: "80.0.0.21" });
check(r1.data.ok && r1.data.status === "ok", "리포트 일부 인용해 글쓰기(익명도 가능)");
const qid = r1.data.id;
fd = await call("GET", `/v1/post/${qid}`);
check(fd.data.post.quote && fd.data.post.quote.kind === "r" && fd.data.post.quote.text.includes("요크빌"), "글 상세에 인용 부분");
r1 = await call("POST", "/v1/comments", { body: { slug: "b-talk", body: "공감합니다", quote: { kind: "p", ref: talk, text: "라운지 첫 글" }, t: 8000 }, ip: "80.0.0.22" });
check(r1.data.ok, "남의 글 일부 인용");
fd = await call("GET", "/v1/notifications", { ip: "80.0.0.2", cookie: LB.cookie });
check(fd.data.items.some((x) => x.type === "quote"), "인용되면 글쓴이에게 알림");
r1 = await call("POST", "/v1/comments", { body: { slug: "b-talk", body: "지어낸 인용", quote: { kind: "p", ref: talk, text: "원글에 없는 문장입니다" }, t: 8000 }, ip: "80.0.0.23" });
check(r1.status === 400, "원글에 없는 문장은 인용 불가(조작 방지)");
r1 = await call("POST", "/v1/comments", { body: { slug: "b-talk", body: "좋은 정보", quote: { kind: "r", ref: "xndu-2026-10", text: "카톡 오픈채팅 문의 주세요" }, t: 8000 }, ip: "80.0.0.24" });
check(r1.data.status === "held", "인용 부분에 홍보 문구가 있으면 보류");
fd = await call("GET", "/v1/feed?tab=all", { ip: "80.0.0.7" });
check(fd.data.items.some((x) => x.id === qid && x.quote && x.quote.ref === "xndu-2026-10"), "피드 글에 인용 표시");
// 종목·테마 팔로우: 로그인 필요, 다시 누르면 취소, 팔로워 수, 팔로잉 피드에 그 종토방 글
r1 = await call("POST", "/v1/topics", { body: { kind: "t", key: "XNDU" }, ip: "80.0.0.7" });
check(r1.status === 401, "로그인 없이 종목 팔로우 불가");
r1 = await call("POST", "/v1/topics", { body: { kind: "t", key: "x'; drop" }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.status === 400, "이상한 종목 이름 거절");
r1 = await call("POST", "/v1/topics", { body: { kind: "th", key: "quantum" }, ip: "80.0.0.1", cookie: LA.cookie });
r1 = await call("POST", "/v1/topics", { body: { kind: "t", key: "ANON" }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.following === true && r1.data.followers === 1, "종목 팔로우");
fd = await call("GET", "/v1/topics", { ip: "80.0.0.1", cookie: LA.cookie });
check(fd.data.items.length === 2 && fd.data.items.some((x) => x.kind === "th" && x.key === "quantum"), "내가 팔로우한 종목·테마 목록");
fd = await call("GET", "/v1/topics/stats?keys=t:ANON,th:quantum,t:NONE", { ip: "80.0.0.1", cookie: LA.cookie });
check(fd.data.stats["t:ANON"].followers === 1 && fd.data.stats["t:ANON"].following && fd.data.stats["t:NONE"].followers === 0, "팔로워 수·내가 했는지");
fd = await call("GET", "/v1/feed?tab=following&boards=b-anon", { ip: "80.0.0.1", cookie: LA.cookie });
check(fd.data.items.some((x) => x.slug === "b-anon"), "팔로잉 탭에 팔로우한 종목 종토방 글");
fd = await call("GET", "/v1/feed?tab=following", { ip: "80.0.0.1", cookie: LA.cookie });
check(!fd.data.items.some((x) => x.slug === "b-anon"), "종목을 안 넘기면 그 종토방 글은 없음");
r1 = await call("POST", "/v1/topics", { body: { kind: "t", key: "ANON" }, ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.following === false && r1.data.followers === 0, "다시 누르면 종목 팔로우 취소");
fd = await call("GET", "/v1/users/suggest", { ip: "80.0.0.7" });
check(fd.data.items.length >= 1 && fd.data.items[0].id === uA && !("actor" in fd.data.items[0]), "팔로우 추천: 좋아요 많이 받은 사람부터(로그인 정보 없음)");
fd = await call("GET", "/v1/users/suggest", { ip: "80.0.0.2", cookie: LB.cookie });
check(!fd.data.items.some((x) => x.id === uA || x.id === uB), "이미 팔로우한 사람·나는 추천에서 뺌");
const dbRows = JSON.stringify((await DB.prepare("SELECT * FROM users").all()).results) + JSON.stringify((await DB.prepare("SELECT * FROM sessions").all()).results);
check(!dbRows.includes("g-alice") && !dbRows.includes("4242") && !dbRows.includes(LA.cookie.slice(5)), "구글·카카오 회원 번호와 세션 원문은 저장 안 함");
await call("POST", `/v1/admin/users/${uB}`, { auth: "Bearer adm", body: { status: "banned" } });
r1 = await call("POST", "/v1/comments", { body: { slug: "b-pre", body: "정지 후 글", t: 8000 }, ip: "80.0.0.2", cookie: LB.cookie });
check(r1.status === 403, "정지 계정은 글 못 씀");
r1 = await call("POST", "/v1/auth/logout", { ip: "80.0.0.9", cookie: LA2.cookie });
check((r1.headers.get("Set-Cookie") || "").includes("Max-Age=0"), "로그아웃하면 쿠키 지움");
r1 = await call("GET", "/v1/me", { ip: "80.0.0.9", cookie: LA2.cookie });
check(r1.data.loggedIn === false, "로그아웃한 세션은 더 못 씀");
r1 = await call("POST", "/v1/me/delete", { body: { all: false }, ip: "80.0.0.1", cookie: LA.cookie });
list = await call("GET", "/v1/comments?slug=b-xndu");
check(r1.data.ok && list.data.comments.some((c) => c.nick === "탈퇴한 사용자" && !c.uid), "탈퇴: 계정 지우고 글은 '탈퇴한 사용자'로");
r1 = await call("GET", "/v1/me", { ip: "80.0.0.1", cookie: LA.cookie });
check(r1.data.loggedIn === false, "탈퇴하면 로그인도 끝남");

console.log("운영 통계");
r = await call("POST", "/v1/hit", { body: { p: "/r/rgti-2026-10/", r: "youtube", m: 1, n: 1, s: 1, a: 120, sc: 80 }, ip: "91.0.0.1" });
check(r.data.ok, "방문 기록 받음");
await call("POST", "/v1/hit", { body: { p: "/", r: "youtube", m: 1, n: 0, s: 2, a: 30, sc: 40 }, ip: "91.0.0.1" });
await call("POST", "/v1/hit", { body: { p: "/r/rgti-2026-10/?utm=x<script>", r: "BAD HOST!", m: 0, n: 1, s: 1, a: 99999, sc: 500 }, ip: "91.0.0.2" });
await call("POST", "/v1/hit", { body: { p: "/admin/", s: 1 }, ip: "91.0.0.3" });
let an = await call("GET", "/v1/admin/analytics?days=7", { ip: "91.0.0.1" });
check(an.status === 403, "운영자가 아니면 통계 거절");
an = await call("GET", "/v1/admin/analytics?days=7", { auth: "Bearer adm" });
const T = an.data.totals;
check(T.pv === 3 && T.uv === 2 && T.sess === 2 && T.multi === 1 && T.newv === 2, "페이지뷰·방문자·세션·2페이지 이상·처음 온 방문 집계(운영자 화면 방문은 안 셈)");
check(T.secs === 120 + 30 + 1800, "체류 시간은 한 페이지 30분까지만");
check(an.data.sources.find((x) => x.src === "youtube").sess === 1 && an.data.sources.some((x) => x.src === "direct"), "유입 경로(이상한 값은 직접 방문으로)");
check(an.data.pages.some((x) => x.path === "/(기타)") && an.data.pages.find((x) => x.path === "/r/rgti-2026-10/").scroll === 80, "모르는 주소는 기타로, 스크롤 100% 넘지 않음");
check(an.data.series.length === 7 && an.data.active.dau === 2 && an.data.community.users >= 1, "날짜 축 7일, 오늘 방문자, 가입자 수");
check(!JSON.stringify((await DB.prepare("SELECT * FROM an_seen").all()).results).includes("91.0.0"), "방문 기록에 IP 없음");
// 확장 통계: 앱으로 연 방문·기기·행동 이벤트·유입 페이지·검색 실패
await call("POST", "/v1/hit", { body: { p: "/r/rgti-2026-10/", r: "youtube", m: 1, n: 1, s: 1, a: 60, sc: 50, app: 1, os: "android", br: "chrome", ev: ["installed", "share", "share", "hack<script>"] }, ip: "91.0.0.6" });
await call("POST", "/v1/search", { body: { q: "팔란티어", miss: 1 }, ip: "91.0.0.6" });
await call("POST", "/v1/search", { body: { q: "팔란티어", miss: 1 }, ip: "91.0.0.6" });
an = await call("GET", "/v1/admin/analytics?days=7", { auth: "Bearer adm" });
check(an.data.app.users30 === 1 && an.data.app.pv === 1 && an.data.events.installed === 1 && an.data.events.share === 1 && !("hack<script>" in an.data.events), "앱 사용자·설치·이벤트(한 페이지 같은 이벤트는 1번, 모르는 이름은 버림)");
check(an.data.tech.some((x) => x.os === "android" && x.br === "chrome") && an.data.entries.some((x) => x.path === "/r/rgti-2026-10/" && x.src === "youtube"), "운영체제·브라우저, 유튜브 → 리포트 첫 페이지");
check(an.data.misses.length === 1 && an.data.misses[0].n === 1, "결과 없는 검색어(하루 한 사람 한 번)");
check(an.data.cohorts.length >= 1 && an.data.reports.some((x) => x.slug === "rgti-2026-10" && "likes" in x), "코호트·리포트별 성과");
for (const ip of ["91.1.0.1", "91.1.0.2", "91.1.0.3"]) await call("POST", "/v1/hit", { body: { p: "/r/rgti-2026-10/", s: 1, a: 200 }, ip });
an = await call("GET", "/v1/popular/read");
check(an.data.items[0] && an.data.items[0].slug === "rgti-2026-10" && an.data.items[0].avg > 0, "이번 주 가장 오래 읽힌 리포트(3회 이상 본 것 중)");
const own = await login("google", "alice", "91.0.0.5");
r1 = await call("POST", "/v1/me", { body: { nick: "운영통계" }, ip: "91.0.0.5", cookie: own.cookie });
an = await call("GET", "/v1/admin/whoami", { ip: "91.0.0.5", cookie: own.cookie });
check(an.data.loggedIn && an.data.owner === false, "로그인해도 지정 전에는 운영자 아님");
sqlite.exec(`INSERT INTO owners (uid) VALUES (${r1.data.user.id})`);
an = await call("GET", "/v1/admin/analytics?days=30", { ip: "91.0.0.5", cookie: own.cookie });
check(an.status === 200 && an.data.days === 30 && an.data.series.length === 30, "운영자 계정은 로그인만으로 통계를 봄");

console.log("유입 분석(세분화)");
await call("POST", "/v1/hit", { body: { p: "/r/rgti-2026-10/", r: "naver", ch: "search", sd: "naver-search", rh: "m.search.naver.com", lp: "/r/rgti-2026-10/", m: 1, n: 1, s: 1, a: 50, sc: 80, ev: ["signup"] }, ip: "92.0.0.1" });
await call("POST", "/v1/hit", { body: { p: "/", r: "naver", ch: "search", sd: "naver-search", lp: "/r/rgti-2026-10/", m: 1, n: 1, s: 2, a: 10, sc: 30 }, ip: "92.0.0.1" });
await call("POST", "/v1/hit", { body: { p: "/r/ionq-2026-10/", r: "youtube", ch: "youtube", sd: "youtube", rh: "www.youtube.com", lp: "/r/ionq-2026-10/", m: 1, n: 0, s: 1, a: 200, sc: 90,
  u: { s: "YouTube", m: "video", c: "ionq-2026-10", t: "pinned<script>" } }, ip: "92.0.0.2" });
await call("POST", "/v1/hit", { body: { p: "/", r: "direct", ch: "hacker", sd: "BAD SRC!", lp: "/../etc", s: 1, a: 5 }, ip: "92.0.0.3" });
an = await call("GET", "/v1/admin/analytics?days=7", { auth: "Bearer adm" });
const A = an.data.acq;
const ns = A.sources.find((x) => x.src === "naver-search");
check(ns && ns.ch === "search" && ns.sess === 1 && ns.multi === 1 && ns.pv === 2 && ns.secs === 60 && ns.ev.signup === 1, "세부 출처: 세션·2페이지·체류·가입");
check(A.landings.some((x) => x.path === "/r/ionq-2026-10/" && x.src === "youtube" && x.sess === 1 && x.secs === 200), "랜딩 페이지 × 출처(유튜브 영상별)");
check(A.refs.some((x) => x.host === "m.search.naver.com"), "리퍼러 도메인");
check(A.campaigns.some((x) => x.src === "youtube" && x.camp === "ionq-2026-10" && x.cont === "pinnedscript"), "UTM 캠페인(이상한 글자는 지움)");
check(A.channels.some((x) => x.ch === "direct") && !A.channels.some((x) => x.ch === "hacker") && A.landings.some((x) => x.path === "/(기타)"), "모르는 채널·경로는 기본값으로");

console.log("광고 성과");
r = await call("POST", "/v1/ad/events", { body: { seg: "m.r", e: [{ g: "quantuma1b2", s: "report_end", k: "i" }, { g: "quantuma1b2", s: "report_end", k: "i" }, { g: "quantuma1b2", s: "report_end", k: "c" }, { g: "spacec3d4", s: "rail", k: "i" }, { g: "BAD!", s: "report_end", k: "i" }, { g: "x1", s: "nowhere", k: "i" }] }, ip: "90.0.0.1" });
check(r.data.ok && r.data.n === 2, "올바른 묶음·자리만 받음");
await call("POST", "/v1/ad/events", { body: { seg: "d.h", e: [{ g: "quantuma1b2", s: "report_end", k: "i" }] }, ip: "90.0.0.2" });
let st2 = (await DB.prepare("SELECT seg, imps, clicks FROM ad_stats WHERE g = 'quantuma1b2' ORDER BY seg").all()).results;
check(st2.length === 2 && st2.find((x) => x.seg === "m.r").imps === 1 && st2.find((x) => x.seg === "m.r").clicks === 1, "한 페이지에서 같은 묶음은 노출 1·클릭 1까지만, 환경별로 따로");
r = await call("POST", "/v1/ad/events", { body: { seg: "phone", e: [{ g: "quantuma1b2", s: "report_end", k: "i" }] }, ip: "90.0.0.3" });
check(r.data.ok === false, "환경 값이 이상하면 거절");
check(!JSON.stringify((await DB.prepare("SELECT * FROM ad_stats").all()).results).includes("90.0.0"), "광고 성과에는 IP 없음");

console.log("검색어");
for (const ip of ["20.0.0.1", "20.0.0.2", "20.0.0.3"]) await call("POST", "/v1/search", { body: { q: "리게티" }, ip });
await call("POST", "/v1/search", { body: { q: "리게티" }, ip: "20.0.0.3" });
await call("POST", "/v1/search", { body: { q: "IONQ" }, ip: "20.0.0.1" });
await call("POST", "/v1/search", { body: { q: "카톡 리딩방" }, ip: "20.0.0.1" });
r = await call("GET", "/v1/trending?days=7");
check(r.data.items[0].q === "리게티" && r.data.items[0].n === 3, "하루 한 사람 한 번만 세서 순위");
check(r.data.items.some((x) => x.q === "ionq") && !r.data.items.some((x) => x.q.includes("카톡")), "소문자로 묶고, 홍보성 검색어는 안 셈");

console.log("SNS: 프로필 사진·차단·멘션·쪽지");
async function mkUser(code, nick, ip) {
  const L = await login("google", code, ip);
  const r = await call("POST", "/v1/me", { body: { nick }, ip, cookie: L.cookie });
  return { cookie: L.cookie, ip, id: r.data.user.id, nick };
}
const U1 = await mkUser("dm1", "쪽지하나", "70.0.0.1"), U2 = await mkUser("dm2", "쪽지둘", "70.0.0.2"), U3 = await mkUser("dm3", "쪽지셋", "70.0.0.3");
const as = (U, m, path, body) => call(m, path, { body, ip: U.ip, cookie: U.cookie });
// 프로필 사진
async function upload(U, bytes, type = "image/webp") {
  const res = await worker.fetch(new Request("https://api.drkimworld.com/v1/me/avatar", { method: "POST", headers: { "CF-Connecting-IP": U.ip, Origin: "https://drkimworld.com", Cookie: U.cookie, "Content-Type": type }, body: bytes }), env);
  return { status: res.status, data: await res.json() };
}
const webp = new Uint8Array(400); webp.set([0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50]);
let up = await upload(U1, webp);
check(up.status === 200 && up.data.av > 0, "사진 올리기(webp)");
check((await upload(U1, new Uint8Array(400).fill(7))).status === 400, "사진이 아닌 파일은 거절");
check((await upload(U1, new Uint8Array(70000))).status >= 400, "64KB 넘으면 거절");
let img = await worker.fetch(new Request(`https://api.drkimworld.com/v1/avatar/${U1.id}?v=${up.data.av}`), env);
check(img.status === 200 && img.headers.get("Content-Type") === "image/webp" && /immutable/.test(img.headers.get("Cache-Control")) && (await img.arrayBuffer()).byteLength === 400, "사진 주소: 버전이 맞으면 1년 캐시");
let avs = await call("GET", `/v1/avatars?ids=${U1.id},${U2.id}`);
check(avs.data.av[U1.id] === up.data.av && !avs.data.av[U2.id], "여러 사람 사진 버전 한 번에");
for (const ip of ["71.0.0.1", "71.0.0.2", "71.0.0.3"]) await call("POST", `/v1/users/${U1.id}/report`, { body: { what: "avatar" }, ip });
avs = await call("GET", `/v1/avatars?ids=${U1.id}`);
check(!avs.data.av[U1.id], "사진 신고 3건이면 사진을 내림");
up = await upload(U1, webp);
// 멘션
sqlite.exec(`UPDATE users SET created = created - 2 * 86400000 WHERE id = ${U2.id}`);
r = await as(U2, "POST", "/v1/comments", { slug: "b-talk", body: "@쪽지하나 님 이 글 보셨어요? @vip_room77", t: 8000 });
check(r.data.status === "held", "없는 영문 @아이디는 여전히 보류(텔레그램 유도 막기)");
r = await as(U2, "POST", "/v1/comments", { slug: "b-talk", body: "@쪽지하나 님 의견 궁금해요", t: 8000 });
check(r.data.status === "ok", "있는 닉네임 멘션은 그대로 게시");
let nt = await as(U1, "GET", "/v1/notifications");
check(nt.data.items.some((x) => x.type === "mention" && x.from_nick === "쪽지둘"), "멘션 알림");
r = await call("GET", "/v1/users/by-nick?n=" + encodeURIComponent("쪽지하나"));
check(r.data.id === U1.id, "닉네임으로 프로필 찾기");
r = await call("GET", "/v1/users/search?q=" + encodeURIComponent("쪽지"));
check(r.data.items.length === 3 && r.data.items.every((x) => "av" in x), "사용자 찾기");
// 쪽지: 새 계정은 처음 보는 사람에게 못 보냄
r = await as(U3, "POST", "/v1/dm/send", { to: U1.id, body: "안녕하세요" });
check(r.status === 403 && /하루 뒤/.test(r.data.message), "가입 하루 안에는 처음 보는 사람에게 쪽지 불가");
sqlite.exec(`UPDATE users SET created = created - 2 * 86400000 WHERE id IN (${U1.id}, ${U3.id})`);
r = await as(U2, "POST", "/v1/dm/send", { to: U1.id, body: "오픈채팅으로 오세요 open.kakao.com/xyz" });
check(r.status === 400 && /사기 예방/.test(r.data.message), "쪽지에 링크·외부 채팅 안내 불가");
r = await as(U2, "POST", "/v1/dm/send", { to: U1.id, body: "IONQ 리포트 잘 봤어요 https://drkimworld.com/r/ionq-2026-10/" });
check(r.status === 200 && r.data.accepted === false, "처음 보는 사람에게는 요청으로(이 사이트 주소는 허용)");
const tid = r.data.tid;
r = await as(U2, "POST", "/v1/dm/send", { tid, body: "두 번째" });
check(r.status === 403 && /수락/.test(r.data.message), "수락 전에는 한 통만");
let li = await as(U1, "GET", "/v1/me");
check(li.data.dmRequests === 1 && li.data.dmUnread === 0, "받는 사람: 요청함 1(안 읽음 숫자와 따로)");
let th = await as(U1, "GET", `/v1/dm/${tid}`);
check(th.data.thread.request && th.data.items.length === 1 && !th.data.items[0].mine, "요청 내용 보기");
r = await as(U1, "POST", "/v1/dm/send", { tid, body: "네 반갑습니다" });
check(r.status === 200 && r.data.accepted, "답장하면 수락");
r = await as(U2, "POST", "/v1/dm/send", { tid, body: "감사합니다!" });
check(r.status === 200, "수락 뒤에는 자유롭게");
li = await as(U1, "GET", "/v1/me");
check(li.data.dmUnread === 1, "안 읽은 대화 1");
th = await as(U1, "GET", `/v1/dm/${tid}?after=0`);
li = await as(U1, "GET", "/v1/me");
check(th.data.items.length === 3 && li.data.dmUnread === 0, "열면 읽음");
check((await as(U3, "GET", `/v1/dm/${tid}`)).status === 404, "남의 대화는 못 봄");
// 받는 설정
await as(U3, "POST", "/v1/me", { dmPref: "none" });
r = await as(U1, "POST", "/v1/dm/send", { to: U3.id, body: "안녕" });
check(r.status === 403 && /받지 않습니다/.test(r.data.message), "쪽지 받지 않음 설정");
await as(U3, "POST", "/v1/follow", { uid: U1.id });
r = await as(U1, "POST", "/v1/dm/send", { to: U3.id, body: "안녕" });
check(r.status === 200 && r.data.accepted, "받지 않음이어도 내가 팔로우한 사람은 바로 대화");
// 신고·삭제
const mid = th.data.items.find((x) => !x.mine).id;
r = await as(U1, "POST", `/v1/dm/msg/${mid}/report`);
check(r.data.ok, "쪽지 신고");
let rep = await call("GET", "/v1/admin/reports", { auth: "Bearer adm" });
check(rep.data.dm.some((x) => x.id === mid && x.sender === U2.id), "운영자는 신고된 쪽지만 봄");
r = await as(U1, "POST", `/v1/dm/msg/${mid}/delete`);
check(r.status === 403, "남의 쪽지는 지울 수 없음");
// 차단
r = await as(U1, "POST", "/v1/block", { uid: U2.id });
check(r.data.blocked, "차단");
r = await as(U2, "POST", "/v1/dm/send", { tid, body: "왜요" });
check(r.status === 403, "차단하면 쪽지 불가");
r = await as(U2, "POST", "/v1/follow", { uid: U1.id });
check(r.status === 403, "차단하면 팔로우 불가");
li = await as(U1, "GET", "/v1/me");
check(li.data.blocked.includes(U2.id), "내 차단 목록");
r = await as(U1, "POST", "/v1/block", { uid: U2.id });
check(!r.data.blocked, "다시 누르면 차단 해제");
// 팔로워 목록
r = await call("GET", `/v1/users/${U1.id}/follows?type=followers`, { ip: U2.ip, cookie: U2.cookie });
check(r.data.items.length === 1 && r.data.items[0].id === U3.id, "팔로워 목록");
// 대화 삭제(둘 다 지우면 서버에서도). 신고 안 된 대화로 확인
const t13 = (await as(U1, "GET", `/v1/dm/with/${U3.id}`)).data.tid;
await as(U1, "POST", `/v1/dm/${t13}/delete`); await as(U3, "POST", `/v1/dm/${t13}/delete`);
check(!(await DB.prepare("SELECT 1 FROM dm_msgs WHERE tid = ?").bind(t13).first()), "둘 다 대화를 지우면 서버에서도 지움");
// 탈퇴하면 쪽지·사진도 지움
await as(U2, "POST", "/v1/me/delete", { all: true });
check(!(await DB.prepare("SELECT 1 FROM dm_msgs WHERE sender = ?").bind(U2.id).first()) && !(await DB.prepare("SELECT 1 FROM avatars WHERE uid = ?").bind(U2.id).first()), "탈퇴하면 쪽지 기록도 지움");

console.log("하나의 피드(섞기)");
{
  const V1 = await mkUser("mx1", "피드보는이", "75.0.0.1"), V2 = await mkUser("mx2", "팔로우대상", "75.0.0.2"), V3 = await mkUser("mx3", "모르는사람", "75.0.0.3"), V4 = await mkUser("mx4", "도배왕", "75.0.0.4");
  sqlite.exec(`UPDATE users SET created = created - 5 * 86400000 WHERE id IN (${V1.id}, ${V2.id}, ${V3.id}, ${V4.id})`);
  const post = async (U, body, slug = "b-talk") => (await as(U, "POST", "/v1/comments", { slug, body, t: 8000 })).data.id;
  const pFollow = await post(V2, "팔로우한 사람의 조금 지난 글");
  const pStranger = await post(V3, "모르는 사람의 새 글");
  const flood = []; for (let i = 0; i < 4; i++) { flood.push(await post(V4, "도배 " + i)); sqlite.exec(`UPDATE comments SET created = created - 60000 WHERE uid = ${V4.id}`); }
  sqlite.exec(`UPDATE comments SET created = created - 5 * 3600000 WHERE id = ${pFollow}`);
  await as(V1, "POST", "/v1/follow", { uid: V2.id });
  let f = await as(V1, "GET", "/v1/feed?tab=mix&limit=20");
  const ids = f.data.items.map((x) => x.id);
  check(ids.indexOf(pFollow) >= 0 && ids.indexOf(pFollow) < ids.indexOf(pStranger), "팔로우한 사람의 글이 모르는 사람의 더 새 글보다 위");
  const top6 = ids.slice(0, 6);
  check(top6.filter((x) => flood.includes(x)).length <= 2 && !top6.some((x, i) => i && flood.includes(x) && flood.includes(top6[i - 1])), "같은 사람 글이 위쪽에 몰리지 않게 펼침");
  await as(V1, "POST", "/v1/block", { uid: V3.id });
  f = await as(V1, "GET", "/v1/feed?tab=mix&limit=20");
  check(!f.data.items.some((x) => x.id === pStranger), "차단한 사람 글은 피드에서 빠짐");
  const g = await call("GET", "/v1/feed?tab=mix&limit=20", { ip: "75.0.0.9" });
  check(g.status === 200 && g.data.items.length > 0, "로그인 전에도 같은 피드(반응·신선도만)");
  await as(V1, "POST", "/v1/block", { uid: V3.id });
}

console.log("공유 미리보기");
{
  const pid = (await DB.prepare("SELECT id FROM comments WHERE slug = 'b-talk' AND status = 'ok' AND parent_id IS NULL ORDER BY id DESC").first()).id;
  let res = await worker.fetch(new Request("https://api.drkimworld.com/s/p/" + pid), env);
  let h = await res.text();
  check(res.status === 200 && /og:title" content="[^"]+님 · 커뮤니티"/.test(h) && h.includes("/og/b-talk.png") && h.includes("location.replace") && h.includes("utm_source=share"), "글 공유: 글 내용으로 미리보기, 사람은 글로 이동");
  check(!/<script>alert/.test(h), "미리보기 글자는 HTML로 해석하지 않음");
  res = await worker.fetch(new Request("https://api.drkimworld.com/s/p/999999"), env); h = await res.text();
  check(res.status === 200 && h.includes("og-default.png"), "없는 글은 기본 미리보기");
  res = await worker.fetch(new Request("https://api.drkimworld.com/s/u/" + U1.id), env); h = await res.text();
  check(h.includes("쪽지하나님의 프로필") && h.includes("/v1/avatar/" + U1.id), "프로필 공유: 사진이 있으면 사진");
}

{ // 0016 마이그레이션: 예전 리포트 댓글 → 그 종목 커뮤니티의 리포트 공유 글(답글·알림도 함께), 새 리포트 알림은 그대로
  const m = new DatabaseSync(":memory:");
  const files = readdirSync(new URL("../migrations/", import.meta.url)).filter((x) => x.endsWith(".sql")).sort();
  for (const f of files.filter((x) => x < "0016")) m.exec(readFileSync(new URL("../migrations/" + f, import.meta.url), "utf8"));
  m.exec(`INSERT INTO comments (id, slug, nick, body, ih, did, created, status) VALUES (1, 'ntla-2026-10', 'a', '좋은 리포트', 'h', 'd', 1, 'ok');
    INSERT INTO comments (id, slug, nick, body, ih, did, created, status, parent_id) VALUES (2, 'ntla-2026-10', 'b', '동의', 'h', 'e', 2, 'ok', 1);
    INSERT INTO comments (id, slug, nick, body, ih, did, created, status) VALUES (3, 'b-ntla', 'c', '원래 종토방 글', 'h', 'f', 3, 'ok');
    INSERT INTO comments (id, slug, nick, body, ih, did, created, status, pinned) VALUES (4, 'b-ntla', '김박사 월드', '인텔리아(NTLA) 종토방을 엽니다.

종토방 규칙', 'notice', 'notice', 0, 'ok', 1);
    INSERT INTO notifs (uid, type, ref, slug, from_nick, n, updated, seen) VALUES (9, 'reply', '1', 'ntla-2026-10', 'b', 1, 2, 0), (9, 'report', 'ntla-2026-10', '', 't', 1, 2, 0);`);
  for (const f of files.filter((x) => x >= "0016")) m.exec(readFileSync(new URL("../migrations/" + f, import.meta.url), "utf8"));
  const rows = m.prepare("SELECT id, slug, parent_id, q_kind, q_ref, q_text, body FROM comments ORDER BY id").all();
  check(rows[0].slug === "b-ntla" && rows[0].q_kind === "r" && rows[0].q_ref === "ntla-2026-10" && rows[0].q_text === "", "예전 리포트 댓글 → 종목 커뮤니티의 리포트 공유 글");
  check(rows[1].slug === "b-ntla" && rows[1].parent_id === 1 && rows[1].q_kind === null, "답글은 같은 글 아래 그대로");
  check(rows[2].q_kind === null && rows[3].body.includes("커뮤니티를 엽니다") && rows[3].body.includes("커뮤니티 규칙"), "원래 종토방 글은 그대로, 공지 이름만 바뀜");
  const ns = m.prepare("SELECT type, slug FROM notifs ORDER BY type").all();
  check(ns.find((x) => x.type === "reply").slug === "b-ntla" && ns.find((x) => x.type === "report").slug === "", "답글 알림은 새 자리로, 새 리포트 알림은 그대로");
}

check(needsHold("문의 01012345678") && !needsHold("정부가 지분 10%를 샀다"), "보류 판정 규칙");
console.log(fails ? `\n실패 ${fails}개` : "\n모두 통과");
process.exit(fails ? 1 : 0);
