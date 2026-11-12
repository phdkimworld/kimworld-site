"""SNS 예약 게시 스크립트 검사 (네트워크 없이)."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import social_publish as sp

ok = 0
def check(name, cond):
    global ok
    if not cond:
        print("FAIL", name); sys.exit(1)
    ok += 1; print("  ok ", name)

with tempfile.TemporaryDirectory() as d:
    d = Path(d); sp.ROOT = d; sp.QUEUE = d / "social/queue"; sp.POSTED = d / "social/posted"
    sp.QUEUE.mkdir(parents=True); (d / "static/social").mkdir(parents=True)
    (d / "static/social/a.mp4").write_bytes(b"x"); (d / "static/social/a.jpg").write_bytes(b"x")
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    W = lambda n, o: (sp.QUEUE / n).write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")
    sp.time.sleep = lambda s: None
    os.environ.update(THREADS_ACCESS_TOKEN="t", THREADS_USER_ID="9", IG_ACCESS_TOKEN="g", IG_USER_ID="7", FB_PAGE_ID="55", FB_PAGE_TOKEN="f")
    sp.FB_LIVE = d / "social/FACEBOOK_LIVE"

    check("시간대 없는 시각은 동부시간", sp.parse_time("2026-10-14T19:30").utcoffset() == timedelta(hours=-4))
    check("이모지는 바이트로 셈", sp.threads_len("👉") == 4)
    W("bad.json", {"text": "가" * 501, "publish_at": past, "channels": ["threads"]})
    check("Threads 501자는 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad.json").unlink()
    W("bad2.json", {"text": "x", "publish_at": past, "channels": ["instagram"], "media": {"type": "reels", "path": "media/a.mp4"}})
    check("static/social 밖 미디어는 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad2.json").unlink()
    W("bad3.json", {"text": "x", "publish_at": past, "channels": ["twitter"]})
    check("모르는 채널은 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad3.json").unlink()
    W("bad4.json", {"text": "x", "publish_at": past, "channels": ["threads"], "poll": ["하나"]})
    check("투표 보기 1개는 검사 실패", sp.main(["--check"]) == 1)
    W("bad4.json", {"text": "x", "publish_at": past, "channels": ["threads"], "poll": ["가" * 9, "나"]})
    check("투표 보기 25바이트 초과(한글 9자)는 검사 실패", sp.main(["--check"]) == 1)
    W("bad4.json", {"text": "x", "publish_at": past, "channels": ["threads"], "poll": ["가", "나"], "link_attachment": "https://drkimworld.com/"})
    check("투표와 링크 카드 함께 쓰면 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad4.json").unlink()

    log = []
    def fake(api, method, path, params, token):
        log.append((api, method, path, {k: v for k, v in params.items() if k != "access_token"}))
        if path == "me": return {"id": "9"} if api == sp.TH_API else {"user_id": "7", "username": "x"}
        if method == "GET" and "status_code" in params.get("fields", ""): return {"status_code": "FINISHED"}
        if method == "GET": return {"permalink": "https://p/" + path}
        return {"id": str(100 + len(log))}
    sp.call = fake; sp.url_ready = lambda u: True
    W("a.json", {"text": "본문", "publish_at": past, "channels": ["threads", "instagram"],
                 "media": {"type": "reels", "path": "static/social/a.mp4", "cover": "static/social/a.jpg"},
                 "channel_text": {"instagram": "인스타 캡션"}, "poll": ["오른다", "내린다", "그대로"],
                 "replies": [{"text": "댓글", "link_attachment": "https://drkimworld.com/r/x/"}]})
    W("b.json", {"text": "내일", "publish_at": future, "channels": ["threads"]})
    W("c.json", {"text": "글만", "publish_at": past, "channels": ["threads", "instagram"]})
    check("두 채널 게시 성공", sp.main([]) == 0)
    posted = json.loads((sp.POSTED / "a.json").read_text())
    check("Threads 본문 → 댓글 순서", len(posted["results"]["threads"]["ids"]) == 2)
    th = [l for l in log if l[0] == sp.TH_API and l[2] == "9/threads"]
    check("투표는 Threads 본문에만 poll_attachment 로",
          json.loads(th[0][3].get("poll_attachment", "{}")) == {"option_a": "오른다", "option_b": "내린다", "option_c": "그대로"}
          and "poll_attachment" not in th[1][3])
    ig = [l for l in log if l[0] == sp.IG_API and l[2] == "7/media"]
    check("릴스 컨테이너: REELS·공개 주소·인스타 전용 캡션 + 투표 보기 글",
          ig and ig[0][3]["media_type"] == "REELS" and ig[0][3]["video_url"] == "https://drkimworld.com/static/social/a.mp4"
          and ig[0][3]["caption"].startswith("인스타 캡션\n\n여러분의 생각은?") and ig[0][3]["caption"].endswith("③ 그대로") and ig[0][3]["cover_url"].endswith("a.jpg"))
    check("media_publish 호출", any(l[2] == "7/media_publish" for l in log))
    check("미디어 없는 글은 인스타 건너뜀", json.loads((sp.POSTED / "c.json").read_text())["results"]["instagram"]["skipped"])
    check("미래 글은 대기열에 남음", (sp.QUEUE / "b.json").exists())

    sp.url_ready = lambda u: False
    W("d.json", {"text": "대기", "publish_at": past, "channels": ["instagram"], "media": {"type": "image", "path": "static/social/a.jpg"}})
    check("배포 전이면 실패 없이 다음으로 미룸", sp.main([]) == 0 and (sp.QUEUE / "d.json").exists())
    old = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    W("d.json", {"text": "대기", "publish_at": old, "channels": ["instagram"], "media": {"type": "image", "path": "static/social/a.jpg"}})
    check("6시간 넘게 주소가 안 열리면 실패", sp.main([]) == 1)
    (sp.QUEUE / "d.json").unlink()

    sp.url_ready = lambda u: True; calls = {"n": 0}
    def flaky(api, method, path, params, token):
        if api == sp.IG_API and path == "7/media":
            calls["n"] += 1
            if calls["n"] == 1: raise RuntimeError("HTTP 500")
        return fake(api, method, path, params, token)
    sp.call = flaky; log.clear()
    W("e.json", {"text": "부분 실패", "publish_at": past, "channels": ["threads", "instagram"], "media": {"type": "image", "path": "static/social/a.jpg"}})
    first = sp.main([])
    saved = json.loads((sp.QUEUE / "e.json").read_text())
    check("인스타 실패 시 Threads 결과 저장, 종료 코드 1", first == 1 and saved["results"]["threads"]["done"])
    log.clear()
    check("다시 돌면 인스타만 게시", sp.main([]) == 0 and not any(l[0] == sp.TH_API and l[2].endswith("/threads") for l in log))

    # ---------- Facebook ----------
    fblog = []
    def fbfake(method, path, params, token, base=sp.FB_API, headers=None, body=None):
        fblog.append((method, path, dict(params), base, dict(headers or {}), body))
        if method == "GET": return {"permalink_url": "https://fb/" + path}
        if params.get("upload_phase") == "start": return {"video_id": "777"}
        if base == sp.FB_RUPLOAD: return {"success": True}
        if path.endswith("/comments"): return {"id": "c1"}
        return {"id": "55_" + str(len(fblog))}
    sp.fb_call = fbfake; sp.call = fake; sp.url_ready = lambda u: True
    sp.FB_LIVE.write_text("ok")
    W("f.json", {"text": "페북 본문", "publish_at": past, "channels": ["threads", "facebook"], "poll": ["가", "나"],
                 "replies": [{"text": "리포트 https://drkimworld.com/r/x/?utm_source=threads&utm_medium=social"}]})
    check("페이스북 글 게시 성공", sp.main([]) == 0)
    feed = [l for l in fblog if l[1] == "55/feed"]
    com = [l for l in fblog if l[1].endswith("/comments")]
    check("페이스북: 본문은 feed(투표 보기 글 안 붙임), 링크는 첫 댓글(utm_source=facebook)",
          feed and feed[0][2]["message"] == "페북 본문" and com and "utm_source=facebook" in com[0][2]["message"])
    check("페이스북 결과 저장", json.loads((sp.POSTED / "f.json").read_text())["results"]["facebook"]["permalink"])
    fblog.clear()
    W("g.json", {"text": "x", "publish_at": past, "channels": ["facebook"], "channel_text": {"instagram": "릴스 캡션"},
                 "media": {"type": "reels", "path": "static/social/a.mp4"}})
    check("페이스북 릴스 게시 성공", sp.main([]) == 0)
    ph = [l[2].get("upload_phase") for l in fblog if l[1] == "55/video_reels" and l[0] == "POST"]
    up = [l for l in fblog if l[3] == sp.FB_RUPLOAD]
    fin = [l for l in fblog if l[2].get("upload_phase") == "finish"]
    check("릴스 3단계(start→파일 직접 업로드→finish), 인스타 캡션(사이트 주소 403 회피)",
          ph == ["start", "finish"] and up and up[0][5] == b"x" and up[0][4]["file_size"] == "1" and up[0][4]["offset"] == "0"
          and "file_url" not in up[0][4] and fin[0][2]["description"] == "릴스 캡션")
    check("replies 없는 릴스는 첫 댓글 없음", not [l for l in fblog if l[1].endswith("/comments")])
    # 11-02: 같은 캡션 첫 줄의 릴스가 이미 있으면 다시 올리지 않는다(SNDK·EU 중복 게시)
    fblog.clear()
    def fbdup(method, path, params, token, base=sp.FB_API, headers=None, body=None):
        fblog.append((method, path, dict(params), base, dict(headers or {}), body))
        if method == "GET" and path.endswith("/video_reels"): return {"data": [{"id": "888", "description": "릴스 캡션"}]}
        if method == "GET": return {"permalink_url": "https://fb/" + path}
        return {"id": "x"}
    sp.fb_call = fbdup
    W("h.json", {"text": "x", "publish_at": past, "channels": ["facebook"], "channel_text": {"instagram": "릴스 캡션"},
                 "media": {"type": "reels", "path": "static/social/a.mp4"}})
    sp.main([])
    hr = json.loads((sp.POSTED / "h.json").read_text())["results"]["facebook"]
    check("이미 올라간 같은 릴스는 다시 올리지 않음(중복 방지)", hr.get("post_id") == "888" and not [l for l in fblog if l[2].get("upload_phase")])
    sp.fb_call = fbfake
    fblog.clear()
    W("g2.json", {"text": "x", "publish_at": past, "channels": ["facebook"], "media": {"type": "reels", "path": "static/social/a.mp4"},
                  "replies": [{"text": "리포트 https://drkimworld.com/r/x/?utm_source=facebook&utm_content=reels_comment"}]})
    check("페이스북 릴스 replies[0] → 첫 댓글", sp.main([]) == 0
          and [l for l in fblog if l[1] == "777/comments" and "reels_comment" in l[2]["message"]])
    fblog.clear()
    def fbnocomment(method, path, params, token, base=sp.FB_API, headers=None, body=None):
        if path.endswith("/comments"): raise RuntimeError("HTTP 400")
        return fbfake(method, path, params, token, base, headers, body)
    sp.fb_call = fbnocomment
    W("g3.json", {"text": "x", "publish_at": past, "channels": ["facebook"], "media": {"type": "reels", "path": "static/social/a.mp4"},
                  "replies": [{"text": "리포트"}]})
    check("릴스 첫 댓글 실패는 게시를 막지 않고 기록만", sp.main([]) == 0
          and json.loads((sp.POSTED / "g3.json").read_text())["results"]["facebook"].get("comment_error"))
    sp.fb_call = fbfake; fblog.clear()
    W("p.json", {"text": "사진 글", "publish_at": past, "channels": ["facebook"], "media": {"type": "image", "path": "static/social/a.jpg"}})
    check("페이스북 사진 게시 성공", sp.main([]) == 0)
    pho = [l for l in fblog if l[1] == "55/photos"]
    check("사진도 파일을 직접 올림(multipart source)", pho and b'name="source"' in pho[0][5] and b'name="message"' in pho[0][5]
          and "multipart/form-data" in pho[0][4]["Content-Type"])
    sp.FB_LIVE.unlink(); fblog.clear()
    for q in sp.POSTED.glob("*.json"): q.unlink()
    W("h1.json", {"text": "첫 글", "publish_at": past, "channels": ["facebook"]})
    W("h2.json", {"text": "둘째 글", "publish_at": past, "channels": ["facebook"]})
    check("공개 확인 전(FACEBOOK_LIVE 없음)에는 한 건만 게시", sp.main([]) == 0 and len([l for l in fblog if l[1] == "55/feed"]) == 1
          and json.loads((sp.QUEUE / "h2.json").read_text())["results"]["facebook"]["waiting"].startswith("공개 확인"))
    (sp.QUEUE / "h2.json").unlink()

import io, urllib.error
attempts = {"n": 0}
def boom(code):
    def f(req, timeout=0):
        attempts["n"] += 1
        raise urllib.error.HTTPError("u", 400, "x", {}, io.BytesIO(json.dumps({"error": {"code": code, "message": "m"}}).encode()))
    return f
import importlib; spf = importlib.reload(sp); spf.time.sleep = lambda s: None
spf.urllib.request.urlopen = boom(190)
try:
    spf.fb_call("POST", "1/feed", {}, "tok"); r = False
except spf.FbFatal:
    r = True
check("페이스북 190 오류는 재시도 없이 실패", r and attempts["n"] == 1)
attempts["n"] = 0; spf.urllib.request.urlopen = boom(4)
try:
    spf.fb_call("POST", "1/feed", {}, "tok")
except spf.FbFatal:
    pass
except RuntimeError:
    pass
check("속도 제한(4)은 최대 3회 재시도", attempts["n"] == 4)
seen = []
def flaky(req, timeout=0):
    seen.append(req.full_url)
    if len(seen) == 1:
        raise urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(json.dumps({"error": {"code": 2, "message": "m"}}).encode()))
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return R(b'{"ok": true}')
spf.urllib.request.urlopen = flaky
check("GET 재시도도 같은 주소로(오류 본문이 요청을 덮지 않음)", spf.fb_call("GET", "1/comments", {"a": "b"}, "tok") == {"ok": True} and seen[0] == seen[1] and seen[1].endswith("?a=b"))
pp = {"text": "본문 질문?", "poll": ["오른다", "내린다", "그대로"], "channel_text": {"instagram": "캡션"}, "media": {"type": "reels", "path": "x"}}
check("인스타 캡션 끝에만 투표 보기를 글로 붙이고 페이스북은 안 붙임", "①" not in sp.fb_text(pp) and sp.ig_caption(pp).endswith("① 오른다\n② 내린다\n③ 그대로"))
check("투표가 없으면 본문 그대로", sp.fb_text({"text": "a"}) == "a")
check("이미 보기를 써 둔 본문에는 다시 붙이지 않음", sp.with_poll_text("x\n① 오른다", pp) == "x\n① 오른다")
wf = (Path(__file__).resolve().parent.parent / ".github/workflows/social.yml").read_text(encoding="utf-8")
step = wf[wf.index("Commit results"):]
check("기록 커밋: rebase 전에 git 이름·메일을 저장소 설정으로 둠(중복 게시 방지)",
      step.find("git config user.name") != -1 and step.find("git config user.name") < step.find("pull -q --rebase"))
KST = sp.KST
n0 = datetime(2026, 10, 20, 20, 10, tzinfo=KST)
check("다음 칸: KST 20:10 → 21:10", sp.next_slot(n0).strftime("%H:%M") == "21:10")
check("3시간 안에 잡힌 글이 있으면 그다음 칸", sp.next_slot(n0, [datetime(2026, 10, 20, 21, 0, tzinfo=KST)]).strftime("%d %H:%M") == "21 07:40")
check("밤 23시 뒤에는 다음 날 아침 칸", sp.next_slot(datetime(2026, 10, 20, 23, 30, tzinfo=KST)).strftime("%d %H:%M") == "21 07:40")

# ---------- 인스타 DM 자동 응답(scripts/ig_dm.py, 네트워크 없이 모의 응답) ----------
import ig_dm as dm
from datetime import date as _date
DN = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
DT = lambda hrs: (DN - timedelta(hours=hrs)).isoformat().replace("+00:00", "Z")
TICK = {"IONQ": {"name": "아이온큐", "name_en": "IonQ", "aliases": ["IonQ"]},
        "QBTS": {"name": "디웨이브 퀀텀", "name_en": "D-Wave Quantum Inc.", "aliases": ["디웨이브", "D-Wave"]},
        "ON": {"name": "온 세미컨덕터", "aliases": []}, "NVDA": {"name": "엔비디아", "aliases": ["NVIDIA"]}}
REPS = [{"slug": "ionq-2026-11", "ticker": "IONQ", "title": "아이온큐, 실적 다음 날 +23.4% | 주가 내러티브와 패턴 투자전략", "date": "2026-11-10"},
        {"slug": "qbts-2026-10", "ticker": "QBTS", "title": "디웨이브 지금 매수하세요", "date": "2026-10-15"},
        {"slug": "ionq-2026-10", "ticker": "IONQ", "title": "아이온큐 지난 리포트", "date": "2026-10-01"},
        {"slug": "on-2026-09", "ticker": "ON", "title": "온 세미", "date": "2026-09-01"}]
LATEST = dm.latest_by_ticker(REPS)
IDX = dm.build_index(TICK, REPS)
check("DM 종목 찾기: 한글 이름", dm.find_tickers("아이온큐 리포트 보내 주세요", IDX) == ["IONQ"])
check("DM 종목 찾기: 별칭·공백 무시", dm.find_tickers("디 웨이브 궁금해요", IDX) == ["QBTS"])
check("DM 종목 찾기: 티커(조사 붙어도)", dm.find_tickers("ionq랑 QBTS", IDX) == ["IONQ", "QBTS"])
check("DM 종목 찾기: 짧은 티커는 대문자·$만", dm.find_tickers("on 리포트", IDX) == [] and dm.find_tickers("$on", IDX) == ["ON"] and dm.find_tickers("ON 리포트", IDX) == ["ON"])
check("DM 종목 찾기: 공개 리포트 없는 종목은 뺌", dm.find_tickers("엔비디아", IDX) == [])
check("DM 종목 찾기: 최신 리포트", LATEST["IONQ"]["slug"] == "ionq-2026-11")
u = dm.link("ionq-2026-11", "reply")
check("DM 링크 utm(명세 12-2)", u == "https://drkimworld.com/r/ionq-2026-11/?utm_source=ig&utm_medium=dm&utm_campaign=ionq-2026-11&utm_content=reply")
check("dm.url 덮어쓰기에도 utm", dm.link("x", "comment", "https://drkimworld.com/glossary/dilution/?utm_source=a") == "https://drkimworld.com/glossary/dilution/?utm_source=ig&utm_medium=dm&utm_campaign=x&utm_content=comment")
t1, s1 = dm.compose_for_tickers(["IONQ"], LATEST, REPS, TICK, "reply")
check("한 종목 답장: 제목(꼬리 뺌)·링크·면책 끝줄", "주가 내러티브와 패턴" not in t1 and "ionq-2026-11" in t1 and t1.endswith(dm.DISCLAIMER) and s1 == ["ionq-2026-11"])
t2, _ = dm.compose_for_tickers(["QBTS"], LATEST, REPS, TICK, "reply")
check("금지어 든 제목은 종목 이름으로 바꿈", "매수하" not in t2 and "디웨이브 퀀텀" in t2 and dm.text_ok(t2))
t3, s3 = dm.compose_for_tickers([], LATEST, REPS, TICK, "reply")
check("못 찾으면 최근 3개 + 종목 이름 안내, 장부 말 없음", len(s3) == 3 and dm.ASK_NAME in t3 and "장부" not in t3 and "요청 목록" not in t3)
check("문구 검사: 금지어 없음·1000바이트 이하", all(dm.text_ok(t) for t in (t1, t3)) and dm.problems("목표가 50달러, AI가 골랐어요, 회원 가입 후, 보유 중이세요?, 베팅") != [])
check("고정 문구에는 금지어 없음(면책 줄 제외)", not dm.problems("\n".join([dm.GREETING, dm.PARTS_LINE, dm.TELEGRAM_LINE, dm.ASK_NAME] + list(dm.PUBLIC_REPLIES))) and not dm.problems(dm.DISCLAIMER))
long = [("가" * 80, dm.link(f"slug-{i}-" + "x" * 30, "reply")) for i in range(3)]
check("긴 목록도 1000바이트 안으로 줄임", len(dm.list_text(long, True).encode()) <= dm.BYTE_LIMIT)
post = {"media": "M1", "slug": "ionq-2026-11", "camp": "ionq-2026-11", "url": None, "title": REPS[0]["title"], "keywords": None}
ct = dm.comment_text(post)
check("댓글 DM 문구: 400자 이내·명세 문구", len(ct) <= dm.COMMENT_DM_CHARS and ct.startswith("안녕하세요, 김박사 월드입니다. 요청하신 무료 리포트예요") and "utm_content=comment" in ct and dm.text_ok(ct, 400))
check("결산 글(리포트 없음)은 검색 화면으로", "/search/?utm_source=ig" in dm.comment_text({**post, "slug": "", "camp": "mood-20261108", "title": ""}))
check("키워드: 공백 지우고 리포트·링크·보내·dm", dm.keyword_hit("리 포 트 부탁") and dm.keyword_hit("DM 주세요") and dm.keyword_hit("보내주세요") and not dm.keyword_hit("좋은 글이네요"))
check("게시물별 키워드", dm.keyword_hit("자료 주세요", ("자료",)) and not dm.keyword_hit("리포트", ("자료",)))
st = dm.load_state(Path("/nonexistent/x.json"))
C2 = lambda i, u, hrs, text="리포트 주세요": {"id": i, "text": text, "user": u, "name": "n" + u, "ts": DT(hrs)}
cm = {"M1": [C2("c1", "u1", 2), C2("c2", "u2", 3, "멋져요"), C2("c3", "me1", 1), C2("c4", "u3", 24 * 8), C2("c5", "u1", 1), C2("c6", "u4", 5)]}
st["comments"]["c6"] = {"media": "M1", "at": DT(4), "result": "err:10/2534022"}
pl = {a["comment"]: a["action"] for a in dm.plan_comments([post], cm, st, DN, {"me1", "drkimworld"})}
check("댓글 계획: 키워드만·우리 댓글 뺌·7일 지남 기록·같은 사용자 공개 답글만·실패는 재시도 안 함",
      pl == {"c1": "dm", "c4": "expired", "c5": "reply_only"})
st["comments"]["c1"] = {"media": "M1", "at": DT(1), "result": "sent"}
pl = {a["comment"]: a["action"] for a in dm.plan_comments([post], cm, st, DN, {"me1"})}
check("이미 보낸 댓글 건너뜀, 24시간 안 보낸 사용자는 공개 답글만", "c1" not in pl and pl.get("c5") == "reply_only")
many = {"M1": [C2(f"k{i}", f"user{i}", 1 + i / 100) for i in range(40)]}
check("실행당 30통 상한", sum(1 for a in dm.plan_comments([post], many, dm.load_state(Path("/x")), DN, set()) if a["action"] == "dm") == dm.PER_RUN_COMMENT)
ME = {"111", "drkimworld"}
M = lambda i, mine, hrs, text: {"id": i, "created_time": DT(hrs), "from": {"id": "111" if mine else "999", "username": "drkimworld" if mine else "x"}, "message": text}
pc = lambda msgs, s=None: dm.plan_conversation(msgs, ME, s or dm.load_state(Path("/x")), DN, IDX, LATEST, REPS, TICK)
p = pc([M("m1", False, 2, "아이온큐 리포트 있나요?")])
check("DM 답장: 종목 찾으면 최신 리포트", p["send"] and "ionq-2026-11" in p["send"] and p["to"] == "999" and p["result"] == "sent:ionq-2026-11")
p = pc([M("m1", False, 2, "안녕하세요")])
check("DM 답장: 못 찾으면 최근 3개", p["send"] and p["result"] == "sent:recent" and dm.ASK_NAME in p["send"])
check("DM 답장: 24시간 지난 메시지는 답하지 않음", pc([M("m1", False, 25, "아이온큐")]) is None)
check("DM 답장: 우리가 이미 답했으면 없음", pc([M("m1", False, 3, "아이온큐"), M("m2", True, 2, "답")]) is None)
s_ = dm.load_state(Path("/x")); s_["messages"][dm.h("m1")] = {"at": DT(1), "result": "sent:recent"}
check("DM 답장: 기록된 메시지 ID(해시)는 다시 보내지 않음", pc([M("m1", False, 2, "아이온큐")], s_) is None)
auto = M("a1", True, 3, "https://drkimworld.com/r/ionq-2026-11/?x\n" + dm.DISCLAIMER)
p = pc([M("m0", False, 4, "아이온큐"), auto, M("m2", False, 1, "감사합니다")])
check("DM 답장: 이야기 중 감사 인사엔 최근 목록 다시 안 보냄", p["send"] is None and p["result"] == "skip:no_match_in_talk")
p = pc([M("m0", False, 4, "아이온큐"), auto, M("m2", False, 1, "아이온큐 또")])
check("DM 답장: 24시간 안 이미 보낸 리포트는 다시 안 보냄", p["send"] is None and p["result"] == "skip:already_sent")
p = pc([M("m0", False, 4, "아이온큐"), auto, M("m2", False, 1, "디웨이브도요")])
check("DM 답장: 새 종목이면 그 리포트", p["send"] and "qbts-2026-10" in p["send"])
caps = [x for i in range(3) for x in (M(f"q{i}", False, 10 - i, "?"), {**auto, "id": f"a{i}", "created_time": DT(9.5 - i)})]
check("DM 답장: 대화당 24시간 3통 상한", pc(caps + [M("z", False, 1, "디웨이브")])["result"] == "skip:conv_cap")
check("DM 답장: 글 없는 메시지(사진 등)는 건너뜀", pc([M("m1", False, 1, "")])["result"] == "skip:no_text")
# 실행(모의 API): 하루 상한·오류 3연속 중단·기록에 사용자 정보 없음
calls = []
def fake_ig(method, path, params):
    calls.append((method, path, params))
    if method == "POST" and path == "me/messages":
        raise RuntimeError('HTTP 400: {"error":{"message":"x","code":10,"error_subcode":2534022}}')
    return {"id": "r"}
dm.ig = fake_ig
st = dm.load_state(Path("/x")); run = dm.Runner(st, DN, dry=False)
run.comments([post], many, set())
check("오류 3번 연속이면 그 실행 멈춤, 실패 코드 기록", run.stopped and sum(1 for c in calls if c[1] == "me/messages") == 3
      and sorted(v["result"] for v in st["comments"].values()) == ["err:10/2534022"] * 3 and st["errors"] == {"10/2534022": 3})
check("실패하면 공개 답글 안 담", not any(c[1].endswith("/replies") for c in calls))
calls.clear(); dm.ig = lambda m, p_, q: calls.append((m, p_, q)) or {"id": "ok"}
st = dm.load_state(Path("/x")); st["daily"][dm.today_kst(DN)] = dm.DAILY_CAP - 2
run = dm.Runner(st, DN, dry=False); run.comments([post], many, set())
sent = [c for c in calls if c[1] == "me/messages"]
check("하루 상한(100통)에서 멈춤", len(sent) == 2 and st["daily"][dm.today_kst(DN)] == dm.DAILY_CAP)
check("Private Reply 요청 형식(recipient.comment_id) + 공개 답글 순환",
      list(json.loads(sent[0][2]["recipient"])) == ["comment_id"] and json.loads(sent[0][2]["message"])["text"] == ct and [c[2]["message"] for c in calls if c[1].endswith("/replies")] == list(dm.PUBLIC_REPLIES[:2]))
calls.clear(); st = dm.load_state(Path("/x")); run = dm.Runner(st, DN, dry=False)
run.dms([[M("mid-raw-1", False, 2, "아이온큐 보내 주세요")]], ME, IDX, LATEST, REPS, TICK)
with tempfile.TemporaryDirectory() as d:
    dm.save_state(st, Path(d) / "s.json"); saved = (Path(d) / "s.json").read_text(encoding="utf-8")
check("DM 답장 요청 형식(recipient.id) + 기록에 사용자 ID·메시지 원문·원래 ID 없음",
      json.loads(calls[0][2]["recipient"]) == {"id": "999"} and "999" not in saved and "아이온큐" not in saved and "mid-raw-1" not in saved and dm.h("mid-raw-1") in saved)
calls.clear(); st = dm.load_state(Path("/x")); run = dm.Runner(st, DN, dry=True)
run.dms([[M("m1", False, 2, "아이온큐")]], ME, IDX, LATEST, REPS, TICK); run.comments([post], cm, set())
check("dry 모드: 보내지 않고 기록도 안 바꿈", not calls and not st["messages"] and not st["comments"])
st = dm.load_state(Path("/x")); st["comments"] = {"old": {"at": DT(24 * 20)}, "new": {"at": DT(1)}}; st["messages"] = {"o": {"at": DT(24 * 4)}}
dm.prune(st, DN)
check("오래된 기록 정리", list(st["comments"]) == ["new"] and not st["messages"])
check("오류 코드 요약", dm.err_code(RuntimeError('HTTP 403: {"error":{"code":200,"message":"perm"}}')) == "200" and dm.err_code(RuntimeError("연결 실패: x")) == "x")
print(f"\n모두 통과 ({ok})")
