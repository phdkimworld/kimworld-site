#!/usr/bin/env python3
"""건강월드 Threads 정해진 시각 자동 게시(운영자 2026-11-27 30일 루틴 '하루 2~3개 같은 시각' + 토큰 절약).
대기열 social/threads_health/queue.json 맨 위 글을 올리고(text 원글, reply 를 '\\n===\\n'으로 나눈 이어지는 글, 링크는 마지막 조각만),
원글에 first_comment 를 단 뒤 대기열에서 빼고 social/threads_health/posted.json 에 기록. 대기열이 비면 아무것도 안 함.
대기열 채우기는 세션(운영 저장소 tools/hw_threads_llm.py — 공용 API 초안 + 검사) 몫. 값·토큰은 출력하지 않는다.
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q = ROOT / "social/threads_health/queue.json"
P = ROOT / "social/threads_health/posted.json"
API = "https://graph.threads.net/v1.0"
TOK = os.environ.get("DRKIM_THREADS_ACCESS_TOKEN", "")
# 운영자 11-27 빌리쌤 팁 "자신만의 시그니처 장착": 모든 원글 끝에 같은 서명 한 줄(이미 있거나 500자 넘으면 생략)
SIG = "— 영양제 뒷면 읽어 주는 김박사 —"
LINK_OK = re.compile(r"https://(link\.coupang\.com/a/|health\.drkimworld\.com/)")


def call(method, path, params):
    q = urllib.parse.urlencode(dict(params, access_token=TOK))
    req = urllib.request.Request(f"{API}/{path}?{q}" if method == "GET" else f"{API}/{path}", data=None if method == "GET" else q.encode(), method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def pub(text, reply_to=None, topic=None):
    p = {"media_type": "TEXT", "text": text}
    if reply_to:
        p["reply_to_id"] = reply_to
    if topic:
        p["topic_tag"] = topic
    c = call("POST", "me/threads", p); time.sleep(5)
    return call("POST", "me/threads_publish", {"creation_id": c["id"]})["id"]


def main():
    if not TOK:
        print("::notice::토큰 없음 — 건너뜀"); return 0
    q = json.loads(Q.read_text()) if Q.exists() else []
    if not q:
        print("::notice::대기열 비어 있음"); return 0
    x = q[0]
    parts = [p.strip() for p in (x.get("reply") or "").split("\n===\n") if p.strip()]
    if re.search(r"https?://", x["text"]) or any(re.search(r"https?://", p) for p in parts[:-1]) or \
       any(not LINK_OK.match(u) for u in re.findall(r"https?://\S+", parts[-1] if parts else "")) or len(x["text"]) > 500 or any(len(p) > 500 for p in parts):
        print(f"::error::{x.get('slug')} 형식 위반 — 대기열 맨 뒤로"); q.append(q.pop(0)); Q.write_text(json.dumps(q, ensure_ascii=False, indent=1) + "\n"); return 1
    text = x["text"] if SIG in x["text"] or len(x["text"]) + len(SIG) + 2 > 500 else x["text"].rstrip() + "\n\n" + SIG
    root = pub(text, topic=re.sub(r"[^0-9A-Za-z가-힣]", "", x.get("topic", ""))[:50] or None)
    prev = root; ids = [root]
    for p in parts:
        time.sleep(4); prev = pub(p, reply_to=prev); ids.append(prev)
    fc = None
    if x.get("first_comment"):
        time.sleep(4); fc = pub(x["first_comment"], reply_to=root)
    done = json.loads(P.read_text()) if P.exists() else []
    done.append({"slug": x.get("slug"), "hook": x["text"].split("\n")[0][:60], "root": root, "parts": ids[1:], "first_comment": fc,
                 "at": datetime.now(timezone.utc).isoformat(timespec="minutes")})
    P.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n")
    Q.write_text(json.dumps(q[1:], ensure_ascii=False, indent=1) + "\n")
    Path(os.environ.get("CHANGED_FILE", "/tmp/changed.txt")).write_text(f"{Q.relative_to(ROOT)}\n{P.relative_to(ROOT)}\n")
    print(f"::notice::게시 {x.get('slug')} root={root} · 남은 대기 {len(q) - 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
