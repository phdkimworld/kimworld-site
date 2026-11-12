#!/usr/bin/env python3
"""인스타그램 DM 자동 응답 (운영자 지시 2026-11-11·11-12, 명세: 미디어 저장소 skill/instagram/INSTAGRAM.md 12장).

두 가지를 한다.
  1) 댓글 키워드 → DM (Private Replies): 우리 인스타 게시물 댓글에 '리포트'·'링크'·'보내'·'dm'이 있으면
     그 게시물 리포트 링크를 DM 한 통으로 보내고(댓글당 1회, 댓글 7일 안), 댓글에 공개 답글 한 줄(3종 순환).
  2) DM 자동 답장: 사용자가 먼저 보낸 DM(24시간 창 안)에서 종목 이름·티커를 찾아 그 종목 최신 공개 리포트 링크를,
     못 찾으면 최근 리포트 3개 + '종목 이름을 보내 주시면 그 리포트를 보내 드립니다'를 보낸다.

링크: https://drkimworld.com/r/<slug>/?utm_source=ig&utm_medium=dm&utm_campaign=<slug>&utm_content=comment|reply
기록: social/dm/sent.json (공개 저장소). 댓글 ID·게시물 ID·시각·결과 코드, DM 은 메시지 ID 해시·시각·결과만.
      사용자 이름·사용자 ID·댓글/DM 내용은 저장하지 않는다(작업 로그에도 찍지 않는다).
상한: 실행당 댓글 DM 30통, 하루(한국 날짜) 전체 100통, 같은 사용자 24시간 1통(댓글 경로; 다른 게시물에 또 달면 공개 답글만),
      대화당 24시간 자동 답장 3통. 보내기 오류 3번 연속이면 그 실행을 멈춘다. 실패는 결과 코드로 남기고 다시 시도하지 않는다.

  python scripts/ig_dm.py            # 실제 실행(IG_ACCESS_TOKEN 필요, 없으면 건너뜀)
  python scripts/ig_dm.py --dry      # 보내지 않고 무엇을 보낼지만 출력(기록도 바꾸지 않음)
  python scripts/ig_dm.py --only comments|dms
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import social_publish as sp  # noqa: E402
from social_comments import pages, slug_of_file, ts  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "social" / "dm" / "sent.json"
KST = ZoneInfo("Asia/Seoul")
SITE = "https://drkimworld.com"

KEYWORDS = ("리포트", "링크", "보내", "dm")      # 공백을 지운 댓글에서 찾는다(dm 은 대소문자 무시)
COMMENT_DAYS = 7          # Private Replies 는 댓글 7일 안에만
POST_DAYS = 14            # 이 기간 안에 올린 게시물의 댓글을 본다(댓글 7일 조건은 따로)
DM_WINDOW_H = 24          # 사용자 메시지 뒤 24시간 안에만 답할 수 있다
PER_RUN_COMMENT = 30
DAILY_CAP = 100
CONV_CAP_24H = 3
MAX_ERR_STREAK = 3
BYTE_LIMIT = 1000         # 인스타 메시지 본문 한도(UTF-8 바이트)
COMMENT_DM_CHARS = 400    # 명세: 댓글 DM 한 통 400자 이내
PUBLIC_REPLIES = ("DM으로 보내 드렸어요 📩", "메시지함 확인해 주세요 🙂", "링크 보내 드렸습니다!")
GREETING = "안녕하세요, 김박사 월드입니다."
PARTS_LINE = "날짜별 기록표와 패턴 정리는 리포트 3·4부에 있습니다."
TELEGRAM_LINE = "새 리포트 알림: 텔레그램 @drkimworld"
ASK_NAME = "종목 이름을 보내 주시면 그 리포트를 보내 드립니다."
DISCLAIMER = "※ 과거 공시·보도를 정리한 교육용 분석이며 매수·매도 권유가 아닙니다. (자동 발송 메시지)"
# 면책 줄을 뺀 본문에 들어가면 안 되는 표현(매수·매도 권유, 목표가, 수익 약속, AI 언급, 가입 유도, 보유 여부, 베팅)
BANNED = ("매수하", "매도하", "매수 추천", "매도 추천", "매수 권유", "매도 권유", "매수 기회", "매수 시점", "매도 시점", "매수 타이밍", "지금 사", "사세요", "파세요", "목표가", "수익 보장", "수익을 보장", "확실한 수익", "원금 보장", "급등 확정", "급등 예상", "급등 임박",
          "AI가", "AI 가", "인공지능", "챗봇", "자동 응답 AI", "회원 가입", "회원가입", "가입하", "가입 후", "보유하", "보유 중",
          "보유중", "보유 여부", "베팅", "몰빵", "올인", "팔로우하면", "팔로우 후")


# ---------- 공통 ----------
def now_utc():
    return datetime.now(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def h(mid):
    """DM 메시지 ID 는 해시로만 남긴다."""
    return hashlib.sha256(f"ig-dm:{mid}".encode()).hexdigest()[:16]


def ig(method, path, params):
    return sp.call(sp.IG_API, method, path, params, os.environ["IG_ACCESS_TOKEN"])


def err_code(e):
    """'HTTP 400: {...}' 오류에서 code/subcode 만 뽑는다(사용자 정보·토큰 없음)."""
    s = str(e)
    m = re.search(r"\{.*", s)
    try:
        err = json.loads(m.group(0)).get("error", {}) if m else {}
    except ValueError:
        err = {}
    http = re.match(r"HTTP (\d+)", s)
    code = err.get("code") or (http.group(1) if http else "x")
    sub = err.get("error_subcode")
    return f"{code}/{sub}" if sub else str(code)


def load_state(path=None):
    p = path or STATE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    for k, v in (("comments", {}), ("messages", {}), ("daily", {}), ("reply_rot", 0), ("errors", {}), ("summary", {})):
        d.setdefault(k, v)
    return d


def prune(state, now):
    keep_c, keep_m, keep_d = now - timedelta(days=14), now - timedelta(days=3), (now - timedelta(days=14)).astimezone(KST).date().isoformat()
    state["comments"] = {k: v for k, v in state["comments"].items() if ts(v["at"]) >= keep_c}
    state["messages"] = {k: v for k, v in state["messages"].items() if ts(v["at"]) >= keep_m}
    state["daily"] = {k: v for k, v in state["daily"].items() if k >= keep_d}


def save_state(state, path=None):
    p = path or STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def today_kst(now):
    return now.astimezone(KST).date().isoformat()


def daily_left(state, now):
    return max(0, DAILY_CAP - int(state["daily"].get(today_kst(now), 0)))


# ---------- 리포트·종목 ----------
def _yaml(p):
    import yaml  # 지연 import: 검사(test_social.py)는 PyYAML 없이 돈다
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_reports(root=ROOT, now=None):
    """공개 리포트 목록 [{slug, ticker, title, date}] (초안·미래 날짜·_파일 제외), 최신순."""
    today = (now or now_utc()).astimezone(KST).date()
    out = []
    for p in sorted((root / "content" / "reports").glob("*.md")):
        if p.name.startswith("_"):
            continue
        parts = re.split(r"^---\s*$", p.read_text(encoding="utf-8"), maxsplit=2, flags=re.M)
        if len(parts) < 3:
            continue
        import yaml
        fm = yaml.safe_load(parts[1]) or {}
        d = fm.get("date")
        if isinstance(d, str):  # '2026-10-15' 처럼 따옴표로 쓴 날짜
            try:
                d = datetime.strptime(d.strip()[:10], "%Y-%m-%d").date()
            except ValueError:
                d = None
        d = d if hasattr(d, "year") else None
        d = d.date() if isinstance(d, datetime) else d
        if fm.get("draft") or not d or d > today:
            continue
        out.append({"slug": p.stem, "ticker": str(fm.get("ticker") or ""), "title": str(fm.get("title") or ""), "date": d.isoformat()})
    out.sort(key=lambda r: (r["date"], r["slug"]), reverse=True)
    return out


def latest_by_ticker(reports):
    out = {}
    for r in reports:  # 최신순이라 처음 본 것이 최신
        out.setdefault(r["ticker"], r)
    return out


def build_index(tickers, reports):
    """찾기 표 [(종류, 정규화한 이름, 티커)]. 공개 리포트가 있는 종목만."""
    have = set(latest_by_ticker(reports))
    idx = []
    for tk, info in (tickers or {}).items():
        tk = str(tk)
        if tk not in have:
            continue
        info = info or {}
        codes = {tk.upper(), tk.split(".")[0].upper()}
        for c in codes:
            if re.fullmatch(r"[A-Z0-9]{1,6}", c):
                idx.append(("code", c, tk))
        for n in [info.get("name"), info.get("name_en")] + list(info.get("aliases") or []):
            n = re.sub(r"\s+", "", str(n or "")).lower()
            if len(n) >= 2:
                idx.append(("name", n, tk))
    return idx


def find_tickers(text, idx):
    """메시지에서 종목을 찾는다. 이름·별칭은 공백 무시 부분 일치(긴 이름 우선), 티커는 영문 경계 일치
    (3자 이상은 대소문자 무시, 1~2자는 대문자 그대로 또는 $티커만)."""
    text = text or ""
    flat = re.sub(r"\s+", "", text).lower()
    found = []
    taken = []  # 이미 맞춘 이름 구간(짧은 이름이 긴 이름 안에서 또 맞지 않게)
    for kind, n, tk in sorted(idx, key=lambda x: -len(x[1])):
        if kind == "name":
            i = flat.find(n)
            while i != -1 and any(a <= i < b for a, b in taken):
                i = flat.find(n, i + 1)
            if i == -1:
                continue
            if re.fullmatch(r"[a-z0-9.\- ]+", n):  # 영문 이름은 단어 경계로 다시 확인
                if not re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", flat):
                    continue
            taken.append((i, i + len(n)))
            pos = i
        else:
            pat = r"(?<![A-Za-z0-9])\$?" + re.escape(n) + r"(?![A-Za-z0-9])"
            ms = [m for m in re.finditer(pat, text, re.I) if len(n) > 2 or m.group(0).startswith("$") or m.group(0) == n]
            if not ms:
                continue
            m = ms[0]
            pos = 10000 + m.start()
        if tk not in [t for _, t in found]:
            found.append((pos, tk))
    return [tk for _, tk in sorted(found)]


# ---------- 문구 ----------
def link(slug, content, url=None):
    utm = f"utm_source=ig&utm_medium=dm&utm_campaign={slug}&utm_content={content}"
    base = url or (f"{SITE}/r/{slug}/" if slug else f"{SITE}/search/")
    base = re.sub(r"[?&]utm_[^&]*", "", base)
    return base + ("&" if "?" in base else "?") + utm


def problems(text):
    """면책 줄을 뺀 본문의 금지어."""
    body = text.replace(DISCLAIMER, "")
    return [w for w in BANNED if w.lower() in body.lower()]


def _short(t, n):
    t = re.sub(r"\s*\|\s*주가 내러티브와 패턴 투자전략\s*$", "", t or "")  # 사이트 제목 꼬리는 뺀다
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _clean_title(t, fallback=""):
    return fallback if problems(t) else t


def single_text(title, url, parts_line=True):
    title = _short(title, 60)
    lines = [f"{GREETING} 요청하신 무료 리포트예요 👇"] + ([title] if title else []) + [url]
    lines += ([PARTS_LINE] if parts_line else []) + [TELEGRAM_LINE, DISCLAIMER]
    return "\n".join(lines)


def list_text(items, ask_name):
    """items [(제목, 링크)]. 바이트 한도를 넘으면 제목을 줄이고, 그래도 넘으면 항목을 줄인다."""
    head = f"{GREETING} " + ("최근 무료 리포트예요 👇" if ask_name else "요청하신 무료 리포트예요 👇")
    for n_items in range(len(items), 0, -1):
        for tl in (40, 28, 18, 0):
            body = []
            for t, u in items[:n_items]:
                body += ([_short(t, tl)] if tl and t else []) + [u]
            lines = [head, ""] + body + [""] + ([ASK_NAME] if ask_name else []) + [TELEGRAM_LINE, DISCLAIMER]
            text = "\n".join(lines)
            if len(text.encode()) <= BYTE_LIMIT:
                return text
    return text


def text_ok(text, chars=None):
    return not problems(text) and len(text.encode()) <= BYTE_LIMIT and (chars is None or len(text) <= chars)


def compose_for_tickers(tks, latest, recent, tickers, content):
    """찾은 종목(없으면 최근 3개)으로 보낼 문구와 보낸 slug 목록."""
    name = lambda tk: str(((tickers or {}).get(tk) or {}).get("name") or tk)  # noqa: E731
    if len(tks) == 1:
        r = latest[tks[0]]
        return single_text(_clean_title(r["title"], name(tks[0])), link(r["slug"], content)), [r["slug"]]
    if tks:
        rs = [latest[t] for t in tks[:3]]
        items = [(_clean_title(r["title"], name(r["ticker"])), link(r["slug"], content)) for r in rs]
        return list_text(items, ask_name=False), [r["slug"] for r in rs]
    rs = recent[:3]
    items = [(_clean_title(r["title"], name(r["ticker"])), link(r["slug"], content)) for r in rs]
    return list_text(items, ask_name=True), [r["slug"] for r in rs]


# ---------- 1) 댓글 키워드 → DM ----------
def keyword_hit(text, keywords=None):
    flat = re.sub(r"\s+", "", text or "").lower()
    return any(k.lower() in flat for k in (keywords or KEYWORDS))


def ig_posts(posted_dir, now, reports_by_slug):
    """게시 기록에서 최근 인스타 게시물 [{media, slug, url, title, keywords}]."""
    out = []
    for p in sorted(Path(posted_dir).glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        mid = ((d.get("results") or {}).get("instagram") or {}).get("id")
        when = d.get("posted_at") or d.get("publish_at")
        if not mid or not when or ts(when) < now - timedelta(days=POST_DAYS):
            continue
        slug = slug_of_file(p.stem)
        dm = d.get("dm") or {}
        kw = dm.get("keyword")
        kws = tuple(kw) if isinstance(kw, list) else ((kw,) if kw else None)
        rep = reports_by_slug.get(slug)
        out.append({"media": str(mid), "slug": slug if rep or dm.get("url") else "", "camp": slug, "url": dm.get("url"),
                    "title": (rep or {}).get("title", ""), "keywords": kws})
    return out


def comment_text(post):
    """명세 12-2 DM 문구. 리포트가 없으면(결산 글 등) 검색 화면으로."""
    url = link(post["camp"], "comment", post.get("url") or (None if post["slug"] else f"{SITE}/search/"))
    title = _clean_title(post.get("title") or "", "")
    if not post["slug"] and not post.get("url"):
        return single_text("김박사 월드 리포트 찾아보기", url, parts_line=False)
    return single_text(title, url, parts_line=bool(title))


def plan_comments(posts, comments, state, now, me, sent_users=None):
    """me: 우리 계정 id·username 집합. comments {media: [{id, text, user, name, ts, parent?}]} → 할 일 [{action, comment, post, user}].
    action: dm(보냄) / reply_only(같은 사용자 24시간 안, 공개 답글만) / expired(7일 지남, 기록만)."""
    sent_users = set(sent_users or ())
    recent_ids = {cid for cid, v in state["comments"].items() if v.get("result") == "sent" and ts(v["at"]) >= now - timedelta(hours=24)}
    all_c = [c for cs in comments.values() for c in cs]
    sent_users |= {c["user"] for c in all_c if c["id"] in recent_ids and c.get("user")}
    plan, n_dm = [], 0
    by_media = {p["media"]: p for p in posts}
    items = sorted(((by_media[m], c) for m, cs in comments.items() if m in by_media for c in cs), key=lambda x: x[1]["ts"])
    seen = set()
    for post, c in items:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        if c["id"] in state["comments"] or c.get("parent") or ({c.get("user"), c.get("name")} & set(me or ())):
            continue
        if not keyword_hit(c.get("text"), post.get("keywords")):
            continue
        if ts(c["ts"]) < now - timedelta(days=COMMENT_DAYS):
            plan.append({"action": "expired", "comment": c["id"], "post": post, "user": c.get("user")})
            continue
        if c.get("user") and c["user"] in sent_users:
            plan.append({"action": "reply_only", "comment": c["id"], "post": post, "user": c.get("user")})
            continue
        if n_dm >= PER_RUN_COMMENT:
            break
        plan.append({"action": "dm", "comment": c["id"], "post": post, "user": c.get("user")})
        sent_users.add(c.get("user"))
        n_dm += 1
    return plan


def fetch_comments(posts, now):
    out = {}
    for p in posts:
        f = lambda path, q: ig("GET", path, q)  # noqa: E731
        cs = []
        for c in pages(f, (f"{p['media']}/comments", {"fields": "id,text,username,timestamp,from{id,username}", "limit": 50}), limit=6):
            u = (c.get("from") or {}).get("id") or c.get("username") or ""
            name = c.get("username") or (c.get("from") or {}).get("username") or ""
            cs.append({"id": c["id"], "text": c.get("text", ""), "user": str(u), "name": name, "ts": c["timestamp"]})
        out[p["media"]] = cs
    return out


# ---------- 2) DM 자동 답장 ----------
def is_mine(m, me_ids):
    f = m.get("from") or {}
    return str(f.get("id") or "") in me_ids or (f.get("username") or "") in me_ids


def plan_conversation(msgs, me_ids, state, now, idx, latest, recent, tickers):
    """한 대화의 메시지 [{id, created_time, from{id,username}, message}] → None 또는
    {send: 문구|None, to: 상대 id, mids: [처리한 메시지 ID], result: 코드, slugs}."""
    msgs = sorted(msgs, key=lambda m: m.get("created_time", ""))
    last_mine = max((i for i, m in enumerate(msgs) if is_mine(m, me_ids)), default=-1)
    window = now - timedelta(hours=DM_WINDOW_H)
    pending = [m for m in msgs[last_mine + 1:] if not is_mine(m, me_ids) and ts(m["created_time"]) >= window and h(m["id"]) not in state["messages"]]
    if not pending:
        return None
    mids = [m["id"] for m in pending]
    to = str((pending[-1].get("from") or {}).get("id") or "")
    mine24 = [m for m in msgs if is_mine(m, me_ids) and ts(m["created_time"]) >= window]
    auto24 = [m for m in mine24 if DISCLAIMER in (m.get("message") or "")]
    sent_slugs = {s for m in mine24 for s in re.findall(r"drkimworld\.com/r/([a-z0-9-]+)/", m.get("message") or "")}
    text = " ".join((m.get("message") or "") for m in pending).strip()
    base = {"send": None, "to": to, "mids": mids, "slugs": []}
    if not text:
        return {**base, "result": "skip:no_text"}
    if len(auto24) >= CONV_CAP_24H:
        return {**base, "result": "skip:conv_cap"}
    tks = [t for t in find_tickers(text, idx) if latest[t]["slug"] not in sent_slugs]
    if not tks:
        if find_tickers(text, idx):
            return {**base, "result": "skip:already_sent"}
        if mine24:  # 이미 이야기 중인 대화(감사 인사 등)에는 최근 목록을 또 보내지 않는다
            return {**base, "result": "skip:no_match_in_talk"}
    msg, slugs = compose_for_tickers(tks, latest, recent, tickers, "reply")
    if not text_ok(msg):
        return {**base, "result": "skip:text_check"}
    return {**base, "send": msg, "slugs": slugs, "result": "sent:" + (",".join(slugs) if tks else "recent")}


def fetch_conversations(now):
    """24시간 안에 바뀐 대화의 최근 메시지들. 메시지 상세가 비어 있으면 하나씩 묻는다(최근 20개까지)."""
    window = now - timedelta(hours=DM_WINDOW_H)
    f = lambda path, q: ig("GET", path, q)  # noqa: E731
    out = []
    for c in pages(f, ("me/conversations", {"platform": "instagram", "fields": "id,updated_time", "limit": 25}), limit=4):
        if c.get("updated_time") and ts(c["updated_time"]) < window:
            continue
        r = ig("GET", c["id"], {"fields": "messages.limit(20){id,created_time,from,message}"})
        msgs = (r.get("messages") or {}).get("data", [])
        full = []
        for m in msgs:
            if "from" not in m or "created_time" not in m:
                try:
                    m = ig("GET", m["id"], {"fields": "id,created_time,from,message"})
                except RuntimeError:
                    continue
            full.append(m)
        out.append(full)
    return out


# ---------- 실행 ----------
class Runner:
    def __init__(self, state, now, dry):
        self.state, self.now, self.dry = state, now, dry
        self.streak, self.stopped = 0, False
        self.count = {"comment_dm": 0, "public_reply": 0, "same_user": 0, "dm_reply": 0, "skipped": 0, "failed": 0}
        self.run_errors = {}

    def can_send(self):
        return not self.stopped and daily_left(self.state, self.now) > 0

    def fail(self, e):
        code = err_code(e)
        self.run_errors[code] = self.run_errors.get(code, 0) + 1
        self.state["errors"][code] = self.state["errors"].get(code, 0) + 1
        self.count["failed"] += 1
        self.streak += 1
        if self.streak >= MAX_ERR_STREAK:
            self.stopped = True
            print("::warning::인스타 DM 보내기 오류가 연속으로 나 이번 실행을 멈춤(코드는 social/dm/sent.json summary)")
        return "err:" + code

    def sent(self):
        self.streak = 0
        d = today_kst(self.now)
        self.state["daily"][d] = int(self.state["daily"].get(d, 0)) + 1

    def public_reply(self, cid):
        text = PUBLIC_REPLIES[self.state["reply_rot"] % len(PUBLIC_REPLIES)]
        if self.dry:
            print(f"  [dry] 댓글 {cid} 공개 답글: {text}")
            return "dry"
        try:
            ig("POST", f"{cid}/replies", {"message": text})
            self.state["reply_rot"] += 1
            self.count["public_reply"] += 1
            return "ok"
        except RuntimeError as e:
            return "err:" + err_code(e)

    def comments(self, posts, comments, me):
        for a in plan_comments(posts, comments, self.state, self.now, me):
            cid, post = a["comment"], a["post"]
            rec = {"media": post["media"], "at": iso(self.now)}
            if a["action"] == "expired":
                rec["result"] = "expired"
            elif a["action"] == "reply_only":
                rec["result"] = "same_user"
                rec["reply"] = self.public_reply(cid)
                self.count["same_user"] += 1
            else:
                if not self.can_send():
                    break
                text = comment_text(post)
                if not text_ok(text, COMMENT_DM_CHARS):
                    rec["result"] = "skip:text_check"
                elif self.dry:
                    print(f"  [dry] 댓글 {cid}(게시물 {post['media']}) → DM:\n" + "\n".join("      " + l for l in text.split("\n")))
                    rec["result"] = "dry"
                    rec["reply"] = self.public_reply(cid)
                else:
                    try:
                        ig("POST", "me/messages", {"recipient": json.dumps({"comment_id": cid}), "message": json.dumps({"text": text}, ensure_ascii=False)})
                        self.sent()
                        self.count["comment_dm"] += 1
                        rec["result"] = "sent"
                        rec["reply"] = self.public_reply(cid)
                    except RuntimeError as e:
                        rec["result"] = self.fail(e)
            if not self.dry:
                self.state["comments"][cid] = rec

    def dms(self, convs, me_ids, idx, latest, recent, tickers):
        for n, msgs in enumerate(convs, 1):
            p = plan_conversation(msgs, me_ids, self.state, self.now, idx, latest, recent, tickers)
            if not p:
                continue
            result = p["result"]
            if p["send"]:
                if not self.can_send():
                    break
                if not p["to"]:
                    result = "skip:no_recipient"
                elif self.dry:
                    print(f"  [dry] 대화 #{n} → DM ({result}):\n" + "\n".join("      " + l for l in p["send"].split("\n")))
                else:
                    try:
                        ig("POST", "me/messages", {"recipient": json.dumps({"id": p["to"]}), "message": json.dumps({"text": p["send"]}, ensure_ascii=False)})
                        self.sent()
                        self.count["dm_reply"] += 1
                    except RuntimeError as e:
                        result = self.fail(e)
            else:
                self.count["skipped"] += 1
                if self.dry:
                    print(f"  [dry] 대화 #{n}: 보내지 않음 ({result})")
            if not self.dry:
                for mid in p["mids"]:
                    self.state["messages"][h(mid)] = {"at": iso(self.now), "result": result}

    def summary(self, extra):
        s = {"run_at": iso(self.now), **self.count, "errors": self.run_errors, "stopped": self.stopped,
             "today": int(self.state["daily"].get(today_kst(self.now), 0)), "daily_cap": DAILY_CAP, **extra}
        return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="보내지 않고 출력만(기록도 바꾸지 않음)")
    ap.add_argument("--only", choices=["comments", "dms"])
    a = ap.parse_args(argv)
    if not os.environ.get("IG_ACCESS_TOKEN"):
        print("::notice::IG_ACCESS_TOKEN 없음 — 인스타 DM 건너뜀")
        return 0
    now = now_utc()
    state = load_state()
    prune(state, now)
    tickers = _yaml(ROOT / "data" / "tickers.yaml")
    reports = load_reports(ROOT, now)
    latest, by_slug = latest_by_ticker(reports), {r["slug"]: r for r in reports}
    idx = build_index(tickers, reports)
    run = Runner(state, now, a.dry)
    extra = {}
    try:
        _run(a, run, extra, idx, latest, by_slug, reports, tickers, now)
    finally:  # 중간에 멈춰도 이미 보낸 것은 반드시 기록한다(중복 발송 방지)
        s = run.summary(extra)
        print("DM_SUMMARY: " + json.dumps({**s, "dry": a.dry}, ensure_ascii=False))
        if not a.dry:
            state["summary"] = s
            save_state(state)
    return 0


def _run(a, run, extra, idx, latest, by_slug, reports, tickers, now):
    try:
        me = ig("GET", "me", {"fields": "id,user_id,username"})
    except RuntimeError as e:
        extra["me_error"] = err_code(e)
        print(f"::warning::인스타 계정 확인 실패({extra['me_error']})")
        me = None
    if me:
        me_ids = {str(me.get("id") or ""), str(me.get("user_id") or ""), me.get("username") or ""} - {""}
        if a.only != "dms":
            try:
                posts = ig_posts(sp.POSTED, now, by_slug)
                run.comments(posts, fetch_comments(posts, now), me_ids)
            except RuntimeError as e:
                extra["comments_error"] = err_code(e)
                print(f"::warning::인스타 댓글 읽기 실패({extra['comments_error']})")
        if a.only != "comments" and not run.stopped:
            try:
                run.dms(fetch_conversations(now), me_ids, idx, latest, reports, tickers)
            except RuntimeError as e:
                extra["dms_error"] = err_code(e)
                print(f"::warning::인스타 대화 읽기 실패({extra['dms_error']})")


if __name__ == "__main__":
    sys.exit(main())
