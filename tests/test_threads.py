"""Threads 예약 게시 스크립트 검사 (네트워크 없이)."""
import json, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import threads_publish as tp

ok = 0
def check(name, cond):
    global ok
    if not cond:
        print("FAIL", name); sys.exit(1)
    ok += 1; print("  ok ", name)

with tempfile.TemporaryDirectory() as d:
    d = Path(d); tp.ROOT = d; tp.QUEUE = d / "threads/queue"; tp.POSTED = d / "threads/posted"
    tp.QUEUE.mkdir(parents=True)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    (tp.QUEUE / "a.json").write_text(json.dumps({"text": "지금 게시", "publish_at": past}), encoding="utf-8")
    (tp.QUEUE / "b.json").write_text(json.dumps({"text": "내일", "publish_at": future}), encoding="utf-8")
    check("시간대 없는 시각은 동부시간", tp.parse_time("2026-10-14T19:30").utcoffset() == timedelta(hours=-4))
    check("한글 500자 통과", tp.threads_len("가" * 500) == 500)
    check("이모지는 바이트로 셈", tp.threads_len("👉") == 4)
    (tp.QUEUE / "c.json").write_text(json.dumps({"text": "가" * 501, "publish_at": past}), encoding="utf-8")
    check("501자는 검사 실패", tp.main(["--check"]) == 1)
    (tp.QUEUE / "c.json").unlink()
    check("정상 대기열 검사 통과", tp.main(["--check"]) == 0)
    sent = []
    def fake(method, path, params):
        sent.append((method, path, {k: v for k, v in params.items() if k != "access_token"}))
        if path == "me":
            return {"id": "9"}
        return {"id": "123"} if method == "POST" else {"permalink": "https://www.threads.net/@x/post/1"}
    tp.call = fake; tp.time.sleep = lambda s: None
    import os
    os.environ["THREADS_ACCESS_TOKEN"] = "t"; os.environ["THREADS_USER_ID"] = "9"
    check("게시 성공", tp.main([]) == 0)
    check("TEXT 컨테이너 → 게시 순서", [s[1] for s in sent[1:3]] == ["9/threads", "9/threads_publish"] and sent[1][2]["media_type"] == "TEXT")
    check("게시한 글은 posted로 이동", not (tp.QUEUE / "a.json").exists() and json.loads((tp.POSTED / "a.json").read_text())["threads_id"] == "123")
    check("미래 글은 대기열에 남음", (tp.QUEUE / "b.json").exists())
    def boom(method, path, params): raise RuntimeError("HTTP 400")
    tp.call = boom
    (tp.QUEUE / "d.json").write_text(json.dumps({"text": "실패", "publish_at": past}), encoding="utf-8")
    check("게시 실패는 종료 코드 1, 대기열 유지", tp.main([]) == 1 and (tp.QUEUE / "d.json").exists())
    def wrongid(method, path, params):
        if path == "me": return {"id": "777"}
        sent.append(path); return {"id": "5"} if method == "POST" else {}
    tp.call = wrongid; sent.clear(); (tp.QUEUE / "d.json").unlink()
    (tp.QUEUE / "e.json").write_text(json.dumps({"text": "다른 ID", "publish_at": past}), encoding="utf-8")
    check("비밀값 ID가 달라도 토큰 계정 ID로 게시", tp.main([]) == 0 and sent[0] == "777/threads")
    # 댓글 쓰레드: 본문 → 댓글1(본문에) → 댓글2(댓글1에)
    log = []; n = [100]
    def chain(method, path, params):
        if path == "me": return {"id": "9"}
        if method == "GET": return {"permalink": "https://www.threads.net/@x/post/root"}
        log.append((path, params.get("reply_to_id"), params.get("link_attachment")))
        n[0] += 1; return {"id": str(n[0])}
    tp.call = chain
    (tp.QUEUE / "f.json").write_text(json.dumps({"text": "본문", "publish_at": past, "replies": [
        {"text": "댓글1", "link_attachment": "https://drkimworld.com/r/x/"}, {"text": "댓글2"}]}), encoding="utf-8")
    check("쓰레드 게시 성공", tp.main([]) == 0)
    creates = [l for l in log if l[0].endswith("/threads")]
    check("댓글은 앞 글에 이어 달림", [c[1] for c in creates] == [None, "102", "104"] and creates[1][2] == "https://drkimworld.com/r/x/")
    check("본문 주소가 기록됨", json.loads((tp.POSTED / "f.json").read_text())["permalink"].endswith("/root"))
    (tp.QUEUE / "g.json").write_text(json.dumps({"text": "가", "publish_at": past, "replies": [{"text": "가" * 501}]}), encoding="utf-8")
    check("댓글 501자는 검사 실패", tp.main(["--check"]) == 1)
    (tp.QUEUE / "g.json").unlink()
    # 댓글에서 실패하면 본문은 다시 올리지 않는다
    calls = {"k": 0}
    def flaky(method, path, params):
        if path == "me": return {"id": "9"}
        if method == "GET": return {}
        if params.get("reply_to_id") and calls["k"] == 0 and path.endswith("/threads"):
            calls["k"] = 1; raise RuntimeError("HTTP 500")
        return {"id": "500" if not params.get("reply_to_id") else "501"}
    tp.call = flaky
    (tp.QUEUE / "h.json").write_text(json.dumps({"text": "본문", "publish_at": past, "replies": [{"text": "댓글"}]}), encoding="utf-8")
    first = tp.main([])
    saved = json.loads((tp.QUEUE / "h.json").read_text())
    check("댓글 실패 시 진행 상황 저장", first == 1 and saved["published_ids"] == ["500"])
    log2 = []
    def track(method, path, params):
        if path == "me": return {"id": "9"}
        if method == "GET": return {}
        if path.endswith("/threads"): log2.append(params.get("reply_to_id"))
        return {"id": "777"}
    tp.call = track
    check("다시 돌면 댓글만 게시", tp.main([]) == 0 and log2 == ["500"])
print(f"\n모두 통과 ({ok})")
