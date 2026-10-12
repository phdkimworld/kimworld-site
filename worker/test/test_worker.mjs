// API 검사: node worker/test/test_worker.mjs
// Cloudflare D1과 같은 모양(prepare/bind/first/all/run/batch)을 node 내장 SQLite로 흉내 내어 실제 코드를 돌린다.
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import worker, { needsHold } from "../src/index.js";

const sqlite = new DatabaseSync(":memory:");
sqlite.exec(readFileSync(new URL("../migrations/0001_init.sql", import.meta.url), "utf8"));
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
const env = { DB, SALT: "test-salt", ADMIN_TOKEN: "adm" };

let fails = 0;
const check = (cond, msg) => { console.log((cond ? "  ok  " : "  FAIL ") + msg); if (!cond) fails++; };
async function call(method, path, { body, ip = "1.1.1.1", auth, origin = "https://drkimworld.com" } = {}) {
  const headers = { "CF-Connecting-IP": ip, Origin: origin, "Content-Type": "application/json" };
  if (auth) headers.Authorization = auth;
  const res = await worker.fetch(new Request("https://api.drkimworld.com" + path, { method, headers, body: body ? JSON.stringify(body) : undefined }), env);
  return { status: res.status, data: await res.json().catch(() => null), headers: res.headers };
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
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", nick: "개미1", body: "정부 지분 얘기 흥미롭네요", t: 8000 } });
check(r.data.ok && r.data.status === "ok", "일반 댓글 바로 게시");
const c1 = r.data.id;
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", nick: "홍보", body: "무료 종목 추천 카톡 문의주세요 010-1234-5678", t: 8000 }, ip: "4.4.4.4" });
check(r.data.status === "held" && /확인 뒤/.test(r.data.message), "연락처·추천 문구는 자동 보류");
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "링크 https://x.example 확인", t: 8000 }, ip: "5.5.5.5" });
check(r.data.status === "held", "링크는 자동 보류");
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "봇", website: "spam", t: 9000 }, ip: "6.6.6.6" });
const bot = (await DB.prepare("SELECT COUNT(*) AS n FROM comments WHERE ih IN (SELECT ih FROM comments) AND body = '봇'").first()).n;
check(bot === 0, "숨은 칸을 채운 로봇 글은 저장 안 함");
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "너무 빠름", t: 500 }, ip: "7.7.7.7" });
check(r.status === 429, "쓰기 시작 3초 안에 보내면 거절");
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", nick: "운영자", body: "운영자 사칭 시험", t: 8000 }, ip: "8.8.8.8" });
let list = await call("GET", "/v1/comments?slug=rgti-2026-10", { ip: "8.8.8.8" });
check(list.data.comments.some((c) => c.nick.startsWith("익명#") && c.body.includes("사칭")), "운영자·김박사 닉네임은 익명으로 바뀜");
check(list.data.comments.every((c) => !("ih" in c)), "해시값은 화면에 보내지 않음");
await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "두 번째", t: 8000 }, ip: "9.9.9.9" });
await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "세 번째", t: 8000 }, ip: "9.9.9.9" });
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "네 번째", t: 8000 }, ip: "9.9.9.9" });
check(r.status === 429, "1분에 2개 넘으면 잠시 막음");
r = await call("POST", "/v1/comments", { body: { slug: "rgti-2026-10", body: "<script>alert(1)</script> 그대로 글자로", t: 8000 }, ip: "10.0.0.1" });
list = await call("GET", "/v1/comments?slug=rgti-2026-10");
check(list.data.comments.length === 5 && !list.data.comments.some((c) => /010|https/.test(c.body)), "보류 글은 목록에 안 나옴(게시 5, 보류 2)");

console.log("좋아요·인기 댓글");
for (const ip of ["11.0.0.1", "11.0.0.2", "11.0.0.3"]) await call("POST", `/v1/comments/${c1}/like`, { ip });
r = await call("POST", `/v1/comments/${c1}/like`, { ip: "11.0.0.3" });
check(r.data.likes === 2 && r.data.liked === false, "같은 사람이 다시 누르면 취소");
r = await call("POST", `/v1/comments/${c1}/like`, { ip: "11.0.0.3" });
check(r.data.likes === 3 && r.data.liked === true, "다시 누르면 좋아요");
r = await call("POST", `/v1/comments/${c1}/like`, { ip: "1.1.1.1" });
check(r.status === 400, "내 댓글에는 좋아요 불가");
list = await call("GET", "/v1/comments?slug=rgti-2026-10&sort=top", { ip: "11.0.0.1" });
check(list.data.best.length === 1 && list.data.best[0].id === c1, "좋아요 3개 이상이면 베스트 댓글");
check(list.data.comments[0].id === c1, "인기순 정렬");
check(list.data.liked.includes(c1), "내가 누른 좋아요 표시");

console.log("신고·삭제·관리");
const victim = list.data.comments.find((c) => c.body.includes("두 번째")).id;
for (const ip of ["12.0.0.1", "12.0.0.2"]) await call("POST", `/v1/comments/${victim}/report`, { ip });
await call("POST", `/v1/comments/${victim}/report`, { ip: "12.0.0.2" });
list = await call("GET", "/v1/comments?slug=rgti-2026-10");
check(list.data.comments.some((c) => c.id === victim), "같은 사람 중복 신고는 한 번만(2건이면 유지)");
await call("POST", `/v1/comments/${victim}/report`, { ip: "12.0.0.3" });
list = await call("GET", "/v1/comments?slug=rgti-2026-10");
check(!list.data.comments.some((c) => c.id === victim), "신고 3건이면 숨김");
r = await call("POST", `/v1/comments/${c1}/delete`, { ip: "9.9.9.9" });
check(r.data.ok === false, "남의 댓글은 삭제 불가");
r = await call("GET", "/v1/admin/queue");
check(r.status === 401, "관리 기능은 토큰 없으면 거절");
r = await call("GET", "/v1/admin/queue", { auth: "Bearer adm" });
check(r.data.items.length === 3, "관리 대기열: 보류 2 + 숨김 1");
r = await call("POST", `/v1/admin/comments/${victim}`, { auth: "Bearer adm", body: { status: "ok" } });
list = await call("GET", "/v1/comments?slug=rgti-2026-10");
check(r.data.ok && list.data.comments.some((c) => c.id === victim), "관리자가 다시 게시");
r = await call("POST", `/v1/comments/${c1}/delete`, { ip: "1.1.1.1" });
list = await call("GET", "/v1/comments?slug=rgti-2026-10");
check(r.data.ok && !list.data.comments.some((c) => c.id === c1), "내 댓글은 내가 삭제");

console.log("검색어");
for (const ip of ["20.0.0.1", "20.0.0.2", "20.0.0.3"]) await call("POST", "/v1/search", { body: { q: "리게티" }, ip });
await call("POST", "/v1/search", { body: { q: "리게티" }, ip: "20.0.0.3" });
await call("POST", "/v1/search", { body: { q: "IONQ" }, ip: "20.0.0.1" });
await call("POST", "/v1/search", { body: { q: "카톡 리딩방" }, ip: "20.0.0.1" });
r = await call("GET", "/v1/trending?days=7");
check(r.data.items[0].q === "리게티" && r.data.items[0].n === 3, "하루 한 사람 한 번만 세서 순위");
check(r.data.items.some((x) => x.q === "ionq") && !r.data.items.some((x) => x.q.includes("카톡")), "소문자로 묶고, 홍보성 검색어는 안 셈");

check(needsHold("문의 01012345678") && !needsHold("정부가 지분 10%를 샀다"), "보류 판정 규칙");
console.log(fails ? `\n실패 ${fails}개` : "\n모두 통과");
process.exit(fails ? 1 : 0);
