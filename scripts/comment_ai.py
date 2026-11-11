#!/usr/bin/env python3
"""댓글 질문·의견에 저가 모델로 답글(운영자 지시 2026-11-11). .github/workflows/comment-ai.yml 에서 매시 15분 실행.

대상: 유튜브·Threads·페이스북의 시청자 첫 댓글(top) 가운데 질문·의견.
하지 않는 것(지금처럼 세션·인스타팀 몫): 대댓글, 종목 요청, AI 여부 질문, 홍보·스팸, 숫자 투표, 감사·이모지(hourly.py 틀 답글),
인스타그램 댓글 전부, 리포트를 찾지 못한 댓글.
흐름: 리포트 본문을 근거로 넣어 답을 만든다 → 규칙 검사(150자·금지어·숫자가 리포트에 실제로 있는지·기준 날짜·링크)
→ 통과한 것만 게시, 아니면 '세션 몫(left)'으로 장부에 남긴다.
장부 social/llm/comments/state.json: 미디어 tools/hourly.py 가 읽어 posted 는 건너뛰고, left 는 세션에 넘기고,
아직 시도 전인 질문·의견은 잠깐(2시간) 기다린다. 키가 없거나(no_key) 크레딧이 없으면(no_credit) 아무것도 하지 않는다.

사용: python3 scripts/comment_ai.py [--dry] [--max N]
  --dry : 답을 만들고 검사만 한다(게시·장부 없음). LLM_MOCK_RESPONSE 와 함께 쓰면 네트워크 없이 흐름만 본다.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402

ROOT = llm.ROOT
REPORTS = ROOT / "content" / "reports"
STATE = ROOT / "social" / "llm" / "comments" / "state.json"
DONE = ROOT / "social" / "replies" / "done"
YT_DAY_LIMIT = 40          # 유튜브 하루(ET) 한도: hourly.py·세션과 함께 쓴다
AI_CEILING = 32            # 오늘 답글이 이만큼 차면 AI는 멈춘다(종목 요청·대댓글 몫 8개를 세션에 남김)
MAX_PER_RUN = 15
MAX_CHARS = 150
HOLD_HOURS = 2             # hourly.py 가 시도 전 질문을 기다려 주는 시간(장부에 함께 적어 둠)

# ---------- 분류(미디어 tools/hourly.py 와 같은 정규식) ----------
THX_RE = re.compile(r"감사|고맙|잘\s*봤|잘\s*보고|잘\s*들었|응원|수고|좋은\s*(영상|정보|분석|내용|자료)|유익|최고|구독\s*(했|하고|누르)|화이팅|파이팅|좋아요")
ASK_RE = re.compile(r"\?|？|해\s*주|다뤄|부탁|요청|왜|어떻|언제|얼마|어디|무엇|뭐|궁금|알려|분석\s*좀|어때|일까|인가요|나요|까요|ㅠ|ㅜ|근데|하지만|그런데|반대|틀렸|아닌")
AI_RE = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|에이아이|GPT|자동\s*답글|봇(이|인가|이세요|이냐|같)|로봇|기계", re.I)
SPAM_RE = re.compile(r"https?://|t\.me/|텔레그램|카톡|카카오톡|오픈채팅|오픈톡|리딩|유료방|매매방|수익\s*(률)?\s*\d+\s*%|수익\s*보장|문의|추천방|무료\s*종목", re.I)
HANGUL = re.compile(r"[가-힣A-Za-z0-9]")


def prefilter(text):
    """모델에 보내기 전에 거른다. None 이면 모델 대상, 아니면 넘기는 이유."""
    t = (text or "").strip()
    if AI_RE.search(t):
        return "AI여부"
    if SPAM_RE.search(t):
        return "홍보의심"
    if re.fullmatch(r"[\d\s,번.과와및\-]+", t) and re.search(r"\d", t):
        return "투표"
    if len(HANGUL.findall(t)) <= 2:
        return "의미없음"
    if THX_RE.search(t) and not ASK_RE.search(t) and len(t) <= 80:
        return "감사"
    return None


# ---------- 답글 규칙 검사(comments.md 3장, SKILL 0.2) ----------
BANNED = [
    (r"매수\s*(하세요|하시|추천|타이밍|기회|해도|각|하면|권)|매도\s*(하세요|하시|추천|타이밍|해도|각|하면|권)|사세요|파세요|사셔도|파셔도|담으세요|줍줍|물타기|손절|익절|팔아야", "매수·매도 권유"),
    (r"목표\s*(가|주가)", "목표가"),
    (r"수익\s*(을|이)?\s*(보장|약속|드리|확실|낼|날\s*거)|확실한\s*수익|원금|손실\s*보전|무조건|급등\s*확정", "수익 약속"),
    (r"베팅|배팅|올인|몰빵|도박|대박|떡상|떡락|존버", "베팅 표현"),
    (r"보유\s*(하고|중|하신|했|해|종목)|들고\s*있|제\s*계좌|저도\s*(샀|사|가지|들)", "보유 여부"),
    (r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|에이아이|GPT|챗봇|(?<!로)봇(?!물)|자동\s*답글|언어\s*모델", "AI 언급"),
    (r"회원\s*가입|가입\s*(하|해)", "회원 가입"),
    (r"사기", "'사기' 단정"),
    (r"빚|대출\s*받아|신용\s*(거래|매수)", "빚"),
    (r"지금\s*당장|서두르|놓치면|마지막\s*기회|지금\s*사야", "긴급성"),
    (r"→|->|=>", "화살표 나열"),
]
URL_RE = re.compile(r"https?://\S+")
NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|퍼센트|달러|배|억|만|원|주|센트|년|월|일|분기|번|거래일|부)?")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def norm_num(s):
    return s.replace(",", "")


def check_reply(text, report_body, slug):
    """문제 목록(빈 목록이면 통과). text 는 링크를 붙이기 전 본문."""
    errs = []
    t = (text or "").strip()
    if not t:
        return ["빈 답글"]
    body = URL_RE.sub("", t).strip()
    if len(body) > MAX_CHARS:
        errs.append(f"{len(body)}자 > {MAX_CHARS}")
    for pat, why in BANNED:
        if re.search(pat, body, re.I):
            errs.append(f"금지: {why}")
    if body.count("·") >= 2:
        errs.append("가운뎃점 나열")
    if EMOJI_RE.search(body) or "#" in body or "**" in body:
        errs.append("이모지·해시태그·마크다운")
    for u in URL_RE.findall(t):
        if not re.fullmatch(rf"https://drkimworld\.com/r/{re.escape(slug)}/", u.rstrip(".,)")):
            errs.append("허용하지 않은 링크")
    if not re.search(r"\d{1,2}월\s*\d{1,2}일", body):
        errs.append("기준 날짜 없음")
    rep = norm_num(report_body)
    rep_dates = set(re.findall(r"(\d{1,2})월\s*(\d{1,2})일", report_body))
    rep_dates |= {(str(int(m)), str(int(d))) for m, d in re.findall(r"\d{4}-(\d{2})-(\d{2})", report_body)}
    for m, d in re.findall(r"(\d{1,2})월\s*(\d{1,2})일", body):
        if (str(int(m)), str(int(d))) not in rep_dates:
            errs.append(f"리포트에 없는 날짜 {m}월 {d}일")
    body_wo_dates = re.sub(r"\d{1,2}월\s*\d{1,2}일|\d{4}년", " ", body)
    for num, unit in NUM_RE.findall(body_wo_dates):
        n = norm_num(num)
        if unit == "부" and n in {"1", "2", "3", "4", "5", "6"}:
            continue
        if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d]|\.\d)", rep):
            errs.append(f"리포트에 없는 숫자 {num}{unit}")
    return errs


# ---------- 리포트 ----------
def front(path):
    s = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n?(.*)", s, re.S)
    if not m:
        return None
    meta = {}
    for k in ("ticker", "title", "date", "data_as_of", "youtube_id", "draft"):
        mm = re.search(rf"^{k}:\s*(.+?)\s*$", m.group(1), re.M)
        meta[k] = mm.group(1).strip().strip('"\'') if mm else ""
    meta.update(slug=path.stem, body=m.group(2), full=s)
    return meta


def load_reports():
    out = []
    for p in sorted(REPORTS.glob("*.md")):
        if p.name.startswith("_"):
            continue
        r = front(p)
        if r and r["draft"].lower() != "true":
            out.append(r)
    return out


def latest_of(reports, ticker):
    c = [r for r in reports if r["ticker"].upper() == ticker.upper()]
    return max(c, key=lambda r: (r["date"], r["slug"])) if c else None


def report_for_video(reports, video_id, title):
    for r in reports:
        if video_id and r["youtube_id"] == video_id:
            return latest_of(reports, r["ticker"])
    tickers = {r["ticker"].upper() for r in reports if r["ticker"]}
    for m in re.findall(r"#([A-Za-z]{1,6})\b|\(([A-Z]{1,6})\)|\b([A-Z]{2,6})\b", title or ""):
        t = next(x for x in m if x).upper()
        if t in tickers:
            return latest_of(reports, t)
    return None


def report_for_slug(reports, slug):
    for r in reports:
        if r["slug"] == slug:
            return latest_of(reports, r["ticker"]) or r
    return None


# ---------- 모델 ----------
SYSTEM = """당신은 미국 주식 리포트 채널 '김박사 월드'의 댓글 담당자입니다. 시청자 댓글 하나에 짧은 답글을 씁니다.
근거는 함께 주는 리포트 본문뿐입니다. 리포트에 없는 숫자·날짜·사실은 쓰지 않습니다.

먼저 댓글 종류(category)를 고릅니다.
- question: 리포트 종목에 대한 질문
- opinion: 리포트 종목에 대한 의견·반론·감상
- request: 다른 종목을 다뤄 달라는 요청, 또는 이 종목의 새 분석·업데이트 요청
- vote: 투표 번호·보기만 남긴 댓글
- ai_question: 사람인지, 자동인지, 기계가 쓰는지 묻는 댓글
- spam: 홍보·외부 링크·연락처·리딩방
- thanks: 감사·인사뿐
- other: 위에 없거나 리포트로 답할 수 없는 것(지금 주가·내일 전망·매매 판단 요청 포함)
question·opinion 일 때만 reply 를 쓰고, 나머지는 reply 를 빈 글자로 둡니다.

답글 규칙
- 존댓말 1~3문장, 링크를 빼고 150자 이내. 링크는 쓰지 않습니다(시스템이 붙입니다).
- 리포트에서 확인한 숫자는 하나 또는 둘만, 반드시 기준 날짜('11월 10일 기준'처럼 리포트에 있는 날짜)와 함께 씁니다.
- 숫자에는 무엇과 비교한 값인지를 같은 문장에 붙입니다(예: '9월 말 장부 7.13달러보다 약 23% 높은 값').
- 용어를 쓰면 한 구절로 풉니다. 화살표, 가운뎃점(·) 나열, 이모지, 해시태그, 마크다운을 쓰지 않습니다.
- 답이 있는 자리를 '리포트 N부 <표 이름>'처럼 알려 줍니다(리포트에 있는 부·표 이름만).
- 마지막은 한 단어로 답할 수 있는 짧은 질문 하나로 끝낼 수 있습니다.
- 금지: 매수·매도 권유, 목표가, 수익 약속, 긴급성, 베팅 표현(올인·몰빵 등), 보유 여부 언급, 자동 답글·기계·인공지능 언급,
  회원 가입 안내, '사기' 단정, 빚·대출로 투자하라는 말, 다른 시청자 비난, 정기 업데이트·개인 연락 약속, 지금 가격·미래 주가 예측.
- 반론에는 리포트 사실로 담담하게 답하고, 리포트 범위 밖이면 '리포트 범위 밖이라 단정하기 어렵습니다'라고 씁니다.
- 매번 같은 틀로 시작하지 않습니다. '흥미롭게도', '결론적으로', '~라는 점입니다' 같은 상투어를 쓰지 않습니다."""

SCHEMA = {"type": "object", "properties": {
    "category": {"type": "string", "enum": ["question", "opinion", "request", "vote", "ai_question", "spam", "thanks", "other"]},
    "reply": {"type": "string"}}, "required": ["category", "reply"], "additionalProperties": False}


def generate(rep, comment, where):
    blocks = [
        {"type": "text", "text": f"리포트 slug: {rep['slug']}\n기준일(data_as_of): {rep['data_as_of']}\n\n{rep['full']}",
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"댓글이 달린 곳: {where}\n댓글 작성자: {comment['author']}\n댓글: {comment['text']}"},
    ]
    return llm.ask("comments", SYSTEM, "", tier="cheap", max_tokens=1500, effort="low", schema=SCHEMA, user_blocks=blocks)


# ---------- 장부 ----------
def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": {}}


def save_state(st):
    cut = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    st["items"] = {k: v for k, v in st.get("items", {}).items() if v.get("at", "") >= cut}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def handle(item, rep, st, key, dry, results):
    """한 댓글: 생성 → 검사 → (통과) 답글 본문 / (아님) left. 돌려주는 값: 게시할 본문 또는 None."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    r = generate(rep, item, item["where"])
    if r["status"] in llm.SKIP_STATUSES:
        results["skip"] = r["status"]
        return None
    if r["status"] != "ok":
        st["items"][key] = {"status": "left", "reason": f"모델 {r['status']}", "at": now}
        return None
    cat, text = r["json"].get("category"), (r["json"].get("reply") or "").strip()
    if cat not in ("question", "opinion"):
        st["items"][key] = {"status": "left", "reason": f"분류 {cat}", "at": now}
        return None
    if item["platform"] == "facebook" and item.get("author") and not text.startswith(item["author"]):
        text = f"{item['author']}님, {text}"
    errs = check_reply(text, rep["full"], rep["slug"])
    if errs:
        st["items"][key] = {"status": "left", "reason": "검사 " + "; ".join(errs)[:200], "at": now, "draft": text[:300]}
        print(f"  넘김 {key}: {'; '.join(errs)[:120]}")
        return None
    return text + f"\nhttps://drkimworld.com/r/{rep['slug']}/"


def run(dry=False, max_n=MAX_PER_RUN):
    st = load_state()
    st.setdefault("items", {})
    prev_status = st.get("status")
    reports = load_reports()
    results = {"posted": 0, "left": 0, "skip": ""}
    todo = []   # (key, item, report)

    # 유튜브
    yt_tok, yt_used = None, 0
    try:
        import yt_comments as yt
        if yt.available():
            yt_tok = yt.token()
            d = yt.list_open(yt_tok, 7)
            yt_used = d.get("my_replies_today_et", 0)
            for o in d.get("open", []):
                if o.get("kind") != "top" or prefilter(o.get("text")):
                    continue
                key = f"youtube:{o['threadId']}"
                if key in st["items"]:
                    continue
                rep = report_for_video(reports, o.get("videoId"), o.get("videoTitle"))
                if not rep:
                    continue
                todo.append((key, {"platform": "youtube", "to": o["threadId"], "author": o.get("author") or "", "text": o.get("text") or "",
                                   "where": f"유튜브 영상 '{o.get('videoTitle', '')}'"}, rep))
        else:
            print("유튜브 인증값 없음 — 유튜브는 건너뜀(YT_CLIENT_ID·YT_CLIENT_SECRET·YT_REFRESH_TOKEN)")
    except Exception as e:  # 유튜브가 실패해도 SNS 는 계속
        print(f"::warning::유튜브 목록 실패 {type(e).__name__}: {str(e)[:150]}")
        yt_tok = None

    # Threads·페이스북(인스타그램은 인스타팀 몫이라 보지 않는다)
    sns_used = {}
    try:
        import social_comments as sc
        lst = sc.list_all(7)
        for pl, v in lst["platforms"].items():
            if pl == "instagram" or not v.get("ok"):
                continue
            sns_used[pl] = v.get("my_replies_24h", 0)
            for o in v.get("open", []):
                if o.get("kind") != "top" or prefilter(o.get("text")) or not o.get("slug"):
                    continue
                key = f"{pl}:{o['replyTo']}"
                if key in st["items"]:
                    continue
                rep = report_for_slug(reports, o["slug"])
                if not rep:
                    continue
                todo.append((key, {"platform": pl, "to": o["replyTo"], "author": o.get("author") or "", "text": o.get("text") or "",
                                   "where": f"{pl} 게시물 '{(o.get('postText') or '')[:80]}'"}, rep))
    except Exception as e:
        print(f"::warning::SNS 목록 실패 {type(e).__name__}: {str(e)[:150]}")

    print(f"모델 대상 {len(todo)}건 · 유튜브 오늘 답글 {yt_used}/{YT_DAY_LIMIT}")
    sns_out = []
    for key, it, rep in todo[:max_n]:
        if it["platform"] == "youtube" and (yt_tok is None or yt_used >= AI_CEILING):
            continue
        if it["platform"] != "youtube" and sns_used.get(it["platform"], 0) >= AI_CEILING:
            continue
        text = handle(it, rep, st, key, dry, results)
        if results["skip"]:
            break
        if text is None:
            results["left"] += 1
            continue
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if dry:
            print(f"  [dry] {key}: {text[:80]}")
            results["posted"] += 1
            continue
        if it["platform"] == "youtube":
            try:
                rid = yt.reply(yt_tok, it["to"], text, "top")
                st["items"][key] = {"status": "posted", "id": rid, "at": now, "slug": rep["slug"]}
                yt_used += 1
                results["posted"] += 1
                time.sleep(25)
            except RuntimeError as e:
                st["items"][key] = {"status": "left", "reason": str(e)[:150], "at": now}
                results["left"] += 1
                if "403" in str(e):
                    yt_tok = None   # 권한·쿼터 문제면 유튜브는 이번 실행에서 멈춤
        else:
            r = {"platform": it["platform"], "to": it["to"], "text": sc.tag_links(text, it["platform"], "top"), "kind": "top", "by": "ai"}
            errs = sc.check_reply(r)
            res = None
            if not errs:
                try:
                    res = {"id": sc.post_one(it["platform"], it["to"], r["text"]), "at": now}
                except (RuntimeError, KeyError) as e:
                    errs = [str(e)[:150]]
            if errs:
                res = {"error": "; ".join(errs)}
                st["items"][key] = {"status": "left", "reason": res["error"][:150], "at": now}
                results["left"] += 1
            else:
                st["items"][key] = {"status": "posted", "id": res["id"], "at": now, "slug": rep["slug"]}
                sns_used[it["platform"]] = sns_used.get(it["platform"], 0) + 1
                results["posted"] += 1
            sns_out.append((r, res))

    changed = []
    if not dry:
        st["status"] = results["skip"] or "ok"
        st["hold_hours"] = HOLD_HOURS
        last = st.get("last_run", "")
        stale = not last or last < (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        if results["posted"] or results["left"] or stale or st["status"] != prev_status:
            st["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_state(st)
            changed.append(str(STATE.relative_to(ROOT)))
        if sns_out:   # hourly.py 가 social/replies/done 의 "to" 로 중복을 거르므로 같은 형식으로 남긴다
            DONE.mkdir(parents=True, exist_ok=True)
            fn = DONE / f"{datetime.now(timezone.utc):%Y%m%d-%H%M}-ai.json"
            fn.write_text(json.dumps({"replies": [r for r, _ in sns_out], "results": [x for _, x in sns_out]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            changed.append(str(fn.relative_to(ROOT)))
    print(f"결과: 게시 {results['posted']} · 세션 몫 {results['left']}" + (f" · 건너뜀 {results['skip']}" if results["skip"] else ""))
    return results, changed


def main(argv):
    dry = "--dry" in argv
    max_n = int(argv[argv.index("--max") + 1]) if "--max" in argv else MAX_PER_RUN
    if not llm.has_key() and "LLM_MOCK_RESPONSE" not in os.environ:
        print("::notice::STATUS=no_key — 댓글 AI 답글을 건너뜀(지금처럼 hourly.py·세션이 처리)")
        return 0
    results, changed = run(dry, max_n)
    if results["skip"]:
        print(f"::notice::STATUS={results['skip']} — 모델을 부르지 않고 건너뜀(실패 아님)")
    out = os.environ.get("CHANGED_FILE")
    if out:
        Path(out).write_text("\n".join(changed), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
