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
    ph = [l[2].get("upload_phase") for l in fblog if l[1] == "55/video_reels"]
    up = [l for l in fblog if l[3] == sp.FB_RUPLOAD]
    fin = [l for l in fblog if l[2].get("upload_phase") == "finish"]
    check("릴스 3단계(start→파일 직접 업로드→finish), 인스타 캡션(사이트 주소 403 회피)",
          ph == ["start", "finish"] and up and up[0][5] == b"x" and up[0][4]["file_size"] == "1" and up[0][4]["offset"] == "0"
          and "file_url" not in up[0][4] and fin[0][2]["description"] == "릴스 캡션")
    check("replies 없는 릴스는 첫 댓글 없음", not [l for l in fblog if l[1].endswith("/comments")])
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
print(f"\n모두 통과 ({ok})")
