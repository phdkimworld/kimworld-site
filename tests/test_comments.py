"""SNS 댓글 모니터링 스크립트 검사 (네트워크 없이)."""
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import social_comments as sc

ok = 0
def check(name, cond):
    global ok
    if not cond:
        print("FAIL", name); sys.exit(1)
    ok += 1; print("  ok ", name)

now = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)
since = now - timedelta(days=7)
T = lambda h: (now - timedelta(hours=h)).isoformat().replace("+00:00", "Z")
C = lambda i, me, h, parent=None: {"id": i, "parent": parent, "author": "나" if me else f"시청자{i}", "isMe": me, "text": i, "publishedAt": T(h)}

# 두 단계 구조(인스타·페이스북)
check("답글 없는 시청자 댓글은 top", sc.open_two_level(C("a", False, 5), [], since, now)["kind"] == "top")
check("우리가 답했으면 열림 아님", sc.open_two_level(C("a", False, 5), [C("b", True, 4)], since, now) is None)
o = sc.open_two_level(C("a", False, 5), [C("b", True, 4), C("c", False, 3)], since, now)
check("우리 답글 뒤 대댓글은 followup", o and o["kind"] == "followup" and o["target"]["id"] == "c")
o = sc.open_two_level(C("p", True, 50), [C("x", False, 2)], since, now)
check("우리 고정 댓글 밑 대댓글은 followup", o and o["kind"] == "followup" and o["mine24"] == 0)
check("8일 지난 댓글은 뺌", sc.open_two_level(C("a", False, 24 * 8), [], since, now) is None)
o = sc.open_two_level(C("a", False, 30), [C("b", True, 10), C("c", False, 9), C("d", True, 8), C("e", False, 1)], since, now)
check("24시간 안 우리 답글 수를 셈", o["mine24"] == 2 and o["target"]["id"] == "e")

# 나무 구조(Threads)
root = "R"
cs = [C("L", True, 20, root), C("a", False, 10, root), C("b", False, 9, "L"), C("c", False, 8, "a"), C("d", False, 7, root), C("e", True, 6, "d")]
out = {o["target"]["id"]: o for o in sc.open_tree(root, cs, since, now)}
check("본문에 단 시청자 댓글은 top", out.get("a", {}).get("kind") == "top")
check("우리 링크 답글에 단 댓글은 followup", out.get("b", {}).get("kind") == "followup")
check("시청자끼리 대화는 뺌", "c" not in out)
check("우리가 답한 댓글은 뺌", "d" not in out)
check("대화 맥락은 위에서부터", [m["text"] for m in out["b"]["context"]] == ["L", "b"])

# slug 찾기
check("파일 이름에서 slug", sc.slug_of_file("hype-2026-10-reels") == "hype-2026-10" and sc.slug_of_file("aave-2026-10-1") == "aave-2026-10")
check("본문 링크에서 slug", sc.find_slug("x", ["리포트 https://drkimworld.com/r/stx-2026-10/?utm=1"], {}) == "stx-2026-10")

# 답글 파일 게시
with tempfile.TemporaryDirectory() as d:
    d = Path(d); sc.REPLIES = d / "replies"; sc.DONE = sc.REPLIES / "done"; sc.REPLIES.mkdir()
    sent = []
    sc.post_one = lambda p, to, t: (sent.append((p, to, t)), f"id{len(sent)}")[1]
    (sc.REPLIES / "r1.json").write_text(json.dumps({"replies": [
        {"platform": "instagram", "to": "123", "text": "감사합니다"},
        {"platform": "threads", "to": "45", "text": "가" * 501},
        {"platform": "facebook", "to": "1_2", "text": "네"},
        {"platform": "x", "to": "1", "text": "y"}]}, ensure_ascii=False), encoding="utf-8")
    rc = sc.post_files()
    r = json.loads((sc.DONE / "r1.json").read_text(encoding="utf-8"))["results"]
    check("검사 실패가 있으면 종료 코드 1", rc == 1)
    check("정상 답글 2개만 게시", len(sent) == 2 and r[0]["id"] == "id1" and r[2]["id"] == "id2")
    check("Threads 500자 초과·모르는 채널은 게시 안 함", "error" in r[1] and "error" in r[3])
    (sc.REPLIES / "r2.json").write_text(json.dumps({"replies": [{"platform": "instagram", "to": "9", "text": "a"}], "results": [{"id": "old"}]}), encoding="utf-8")
    sc.post_files()
    check("결과가 있는 답글은 다시 달지 않음", len(sent) == 2)
    (sc.REPLIES / "r3.json").write_text(json.dumps({"replies": [
        {"platform": "threads", "to": "7", "text": "리포트 → https://drkimworld.com/r/agnc-2026-10/ 어때요?", "kind": "followup"},
        {"platform": "facebook", "to": "1_3", "text": "https://drkimworld.com/r/a-1/?utm_source=threads&utm_content=x"}]}, ensure_ascii=False), encoding="utf-8")
    sc.post_files()
    check("대댓글 답글 링크는 utm_content=followup(채널·comment·slug)",
          sent[2][2] == "리포트 → https://drkimworld.com/r/agnc-2026-10/?utm_source=threads&utm_medium=comment&utm_campaign=agnc-2026-10&utm_content=followup 어때요?")
    check("kind 없으면 reply, 이미 있던 utm 은 채널 값으로 덮어씀",
          sent[3][2] == "https://drkimworld.com/r/a-1/?utm_source=facebook&utm_medium=comment&utm_campaign=a-1&utm_content=reply")

print(f"{ok}개 통과")
