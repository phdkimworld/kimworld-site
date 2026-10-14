"""Threads 예약 게시.

threads/queue/*.json 의 글 가운데 publish_at 이 지난 것을 Threads API로 게시하고
threads/posted/ 로 옮긴다(커밋은 워크플로가 한다).

글 파일 형식:
  {"text": "본문(500자 이내)", "publish_at": "2026-10-14T19:30:00-04:00"}
  - publish_at 에 시간대가 없으면 America/New_York 으로 본다.
  - 선택: "link_attachment": "https://..." (링크 미리보기 카드. 본문에 주소가 없어도 된다)

사용:
  python scripts/threads_publish.py            # 검사 + 시간이 된 글 게시
  python scripts/threads_publish.py --check    # 검사만(게시하지 않음)
  python scripts/threads_publish.py --dry-run  # 게시할 글만 출력
  python scripts/threads_publish.py --ping     # 토큰이 살아 있는지 확인

비밀값(환경변수): THREADS_ACCESS_TOKEN, THREADS_USER_ID. 값은 어디에도 출력하지 않는다.
검사 실패나 게시 실패가 하나라도 있으면 종료 코드 1(워크플로 실패로 표시).
"""
import json
import os
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "threads" / "queue"
POSTED = ROOT / "threads" / "posted"
NY = ZoneInfo("America/New_York")
API = "https://graph.threads.net/v1.0"
LIMIT = 500


def threads_len(text):
    """Threads 글자 수. 이모지는 UTF-8 바이트 수로 세어 보수적으로 잡는다."""
    n = 0
    for ch in text:
        cp = ord(ch)
        emoji = (cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF
                 or cp in (0x200D, 0xFE0F) or unicodedata.category(ch) == "So")
        n += len(ch.encode("utf-8")) if emoji else 1
    return n


def parse_time(s):
    t = datetime.fromisoformat(s)
    return t.replace(tzinfo=NY) if t.tzinfo is None else t


def load(path):
    """글 하나를 읽고 검사한다. (글, 오류 목록)"""
    try:
        post = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # JSON 문법 오류
        return None, [f"JSON을 읽을 수 없음: {e}"]
    errs = []
    if not isinstance(post, dict):
        return None, ["JSON 최상위는 객체여야 함"]
    text = post.get("text")
    if not isinstance(text, str) or not text.strip():
        errs.append("text 가 비어 있음")
    else:
        n = threads_len(text)
        if n > LIMIT:
            errs.append(f"text {n}자 > {LIMIT}자 제한")
    try:
        post["_at"] = parse_time(str(post.get("publish_at", "")))
    except ValueError:
        errs.append("publish_at 이 ISO 형식이 아님 (예: 2026-10-14T19:30:00-04:00)")
    link = post.get("link_attachment")
    if link is not None and not (isinstance(link, str) and link.startswith("https://")):
        errs.append("link_attachment 는 https:// 주소여야 함")
    return post, errs


def call(method, path, params):
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        url, data = f"{url}?{data.decode()}", None
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        token = params.get("access_token")
        if token:
            body = body.replace(token, "***")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from None


def publish(post, uid, token):
    params = {"media_type": "TEXT", "text": post["text"], "access_token": token}
    if post.get("link_attachment"):
        params["link_attachment"] = post["link_attachment"]
    creation = call("POST", f"{uid}/threads", params)["id"]
    last = None
    for wait in (3, 10, 20, 30):  # 컨테이너 준비를 잠깐 기다렸다가 게시
        time.sleep(wait)
        try:
            media = call("POST", f"{uid}/threads_publish",
                         {"creation_id": creation, "access_token": token})["id"]
            break
        except RuntimeError as e:
            last = e
    else:
        raise last
    link = ""
    try:
        link = call("GET", media, {"fields": "permalink", "access_token": token}).get("permalink", "")
    except RuntimeError:
        pass
    return media, link


def main(argv):
    check = "--check" in argv
    dry = "--dry-run" in argv
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    uid = os.environ.get("THREADS_USER_ID", "")

    if "--ping" in argv:
        if not (token and uid):
            print("::error::THREADS_ACCESS_TOKEN / THREADS_USER_ID 비밀값이 없음")
            return 1
        try:
            me = call("GET", "me", {"fields": "id,username", "access_token": token})
        except RuntimeError as e:
            print(f"::error::Threads 토큰 확인 실패(만료됐으면 threads/README.md의 갱신 방법 참고): {e}")
            return 1
        print(f"토큰 정상: @{me.get('username')}")
        return 0

    QUEUE.mkdir(parents=True, exist_ok=True)
    POSTED.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    bad = 0
    due = []
    files = sorted(QUEUE.glob("*.json"))
    for p in files:
        post, errs = load(p)
        if errs:
            bad += 1
            for e in errs:
                print(f"::error file=threads/queue/{p.name}::{e}")
            continue
        state = "게시 대상" if post["_at"] <= now else "대기"
        print(f"{p.name}: {threads_len(post['text'])}자, {post['_at'].astimezone(NY):%Y-%m-%d %H:%M} ET, {state}")
        if post["_at"] <= now:
            due.append((p, post))
    for p in sorted(ROOT.glob("threads/*.json")):
        bad += 1
        print(f"::error file=threads/{p.name}::글은 threads/queue/ 안에 둬야 함")
    print(f"대기열 {len(files)}개, 게시 대상 {len(due)}개, 검사 실패 {bad}개")

    if check or dry or not due:
        return 1 if bad else 0
    if not (token and uid):
        print("::error::THREADS_ACCESS_TOKEN / THREADS_USER_ID 비밀값이 없어 게시하지 못함")
        return 1

    failed = 0
    for p, post in sorted(due, key=lambda x: x[1]["_at"]):
        try:
            media, link = publish(post, uid, token)
        except RuntimeError as e:
            failed += 1
            print(f"::error file=threads/queue/{p.name}::게시 실패: {e}")
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw.update(posted_at=datetime.now(NY).isoformat(timespec="seconds"), threads_id=media, permalink=link)
        dest = POSTED / p.name
        if dest.exists():
            dest = POSTED / f"{p.stem}-{media}.json"
        dest.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        p.unlink()
        print(f"::notice::게시함 {p.name} → {link or media}")
    return 1 if (bad or failed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
