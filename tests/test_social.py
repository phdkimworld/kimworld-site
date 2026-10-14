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
    os.environ.update(THREADS_ACCESS_TOKEN="t", THREADS_USER_ID="9", IG_ACCESS_TOKEN="g", IG_USER_ID="7")

    check("시간대 없는 시각은 동부시간", sp.parse_time("2026-10-14T19:30").utcoffset() == timedelta(hours=-4))
    check("이모지는 바이트로 셈", sp.threads_len("👉") == 4)
    W("bad.json", {"text": "가" * 501, "publish_at": past, "channels": ["threads"]})
    check("Threads 501자는 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad.json").unlink()
    W("bad2.json", {"text": "x", "publish_at": past, "channels": ["instagram"], "media": {"type": "reels", "path": "media/a.mp4"}})
    check("static/social 밖 미디어는 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad2.json").unlink()
    W("bad3.json", {"text": "x", "publish_at": past, "channels": ["facebook"]})
    check("모르는 채널은 검사 실패", sp.main(["--check"]) == 1)
    (sp.QUEUE / "bad3.json").unlink()

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
                 "channel_text": {"instagram": "인스타 캡션"},
                 "replies": [{"text": "댓글", "link_attachment": "https://drkimworld.com/r/x/"}]})
    W("b.json", {"text": "내일", "publish_at": future, "channels": ["threads"]})
    W("c.json", {"text": "글만", "publish_at": past, "channels": ["threads", "instagram"]})
    check("두 채널 게시 성공", sp.main([]) == 0)
    posted = json.loads((sp.POSTED / "a.json").read_text())
    check("Threads 본문 → 댓글 순서", len(posted["results"]["threads"]["ids"]) == 2)
    ig = [l for l in log if l[0] == sp.IG_API and l[2] == "7/media"]
    check("릴스 컨테이너: REELS·공개 주소·인스타 전용 캡션",
          ig and ig[0][3]["media_type"] == "REELS" and ig[0][3]["video_url"] == "https://drkimworld.com/static/social/a.mp4"
          and ig[0][3]["caption"] == "인스타 캡션" and ig[0][3]["cover_url"].endswith("a.jpg"))
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
print(f"\n모두 통과 ({ok})")
