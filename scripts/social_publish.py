"""SNS 예약 게시 (Threads + Instagram).

social/queue/*.json 의 게시물 가운데 publish_at 이 지난 것을 채널별로 게시하고, 모든 채널이 끝나면
social/posted/ 로 옮긴다(커밋은 워크플로가 한다).

게시물 파일 형식:
  {
    "text": "공통 본문",
    "publish_at": "2026-10-14T19:30:00-04:00",        # 시간대가 없으면 America/New_York
    "channels": ["threads", "instagram"],
    "media": {"type": "reels", "path": "static/social/lhx/LHX_shorts.mp4"},   # 선택
    "channel_text": {"instagram": "인스타 전용 캡션"},  # 선택: 채널별 본문
    "replies": [{"text": "...", "link_attachment": "https://..."}],  # 선택: Threads 이어지는 댓글
    "link_attachment": "https://..."                    # 선택: Threads 링크 카드
  }
  media.type: image | carousel | reels
    image  → "path": 이미지 1장 (JPEG 권장)
    carousel → "paths": [이미지 2~10장]
    reels  → "path": MP4(세로 9:16, 3~90초 권장), 선택 "cover": 표지 이미지 경로
  path 는 저장소 기준 경로이며 static/social/ 아래에 둔다 → https://drkimworld.com/static/social/... 로 공개된다
  (사이트 배포가 끝나 주소가 200을 돌려줄 때까지 인스타 게시는 다음 실행으로 미룬다).
  Threads 는 TEXT 게시만 한다(미디어는 쓰지 않음). 미디어가 없는 글은 인스타를 건너뛴다.

사용:
  python scripts/social_publish.py              # 검사 + 시간이 된 글 게시
  python scripts/social_publish.py --check      # 검사만
  python scripts/social_publish.py --ping       # 두 채널 토큰 확인
  python scripts/social_publish.py --delete threads <글 ID>   # Threads 글 삭제(threads_delete 권한 필요)

비밀값(환경변수): THREADS_ACCESS_TOKEN, THREADS_USER_ID, IG_ACCESS_TOKEN, IG_USER_ID. 값은 출력하지 않는다.
검사·게시 실패가 하나라도 있으면 종료 코드 1. 중간에 실패하면 이미 게시한 채널·댓글은 파일의 "results" 에
남겨 다음 실행에서 건너뛴다(중복 게시 방지).
"""
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "social" / "queue"
POSTED = ROOT / "social" / "posted"
NY = ZoneInfo("America/New_York")
SITE = "https://drkimworld.com"
TH_API = "https://graph.threads.net/v1.0"
IG_API = "https://graph.instagram.com/v23.0"
TH_LIMIT = 500
IG_LIMIT = 2200
CHANNELS = ("threads", "instagram")
MEDIA_EXT = {"image": (".jpg", ".jpeg", ".png"), "reels": (".mp4", ".mov")}
STALE_HOURS = 6  # 미디어 주소가 이 시간 넘게 열리지 않으면 실패로 표시


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


def text_for(post, ch):
    return (post.get("channel_text") or {}).get(ch) or post.get("text", "")


def media_paths(m):
    return list(m.get("paths") or ([m["path"]] if m.get("path") else [])) + ([m["cover"]] if m.get("cover") else [])


def public_url(rel):
    return f"{SITE}/{rel.lstrip('/')}"


def load(path):
    """게시물 하나를 읽고 검사한다. (글, 오류 목록)"""
    try:
        post = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, [f"JSON을 읽을 수 없음: {e}"]
    if not isinstance(post, dict):
        return None, ["JSON 최상위는 객체여야 함"]
    errs = []
    try:
        post["_at"] = parse_time(str(post.get("publish_at", "")))
    except ValueError:
        errs.append("publish_at 이 ISO 형식이 아님 (예: 2026-10-14T19:30:00-04:00)")
    chans = post.get("channels")
    if not isinstance(chans, list) or not chans or any(c not in CHANNELS for c in chans):
        errs.append(f"channels 는 {list(CHANNELS)} 가운데 하나 이상인 목록이어야 함")
        chans = []
    if "threads" in chans:
        t = text_for(post, "threads")
        if not t.strip():
            errs.append("Threads 본문이 비어 있음")
        elif threads_len(t) > TH_LIMIT:
            errs.append(f"Threads 본문 {threads_len(t)}자 > {TH_LIMIT}자 제한")
        for i, r in enumerate(post.get("replies", []) or [], 1):
            rt = r.get("text") if isinstance(r, dict) else None
            if not isinstance(rt, str) or not rt.strip():
                errs.append(f"replies[{i}] text 가 비어 있음")
            elif threads_len(rt) > TH_LIMIT:
                errs.append(f"replies[{i}] {threads_len(rt)}자 > {TH_LIMIT}자 제한")
    m = post.get("media")
    if m is not None:
        typ = m.get("type") if isinstance(m, dict) else None
        if typ not in ("image", "carousel", "reels"):
            errs.append("media.type 은 image | carousel | reels")
        else:
            paths = media_paths(m)
            if typ == "carousel" and not 2 <= len(m.get("paths") or []) <= 10:
                errs.append("carousel 은 paths 이미지 2~10장")
            if typ in ("image", "reels") and not m.get("path"):
                errs.append(f"{typ} 은 path 가 필요함")
            for p in paths:
                if not str(p).startswith("static/social/"):
                    errs.append(f"미디어는 static/social/ 아래에 둬야 공개 주소가 생김: {p}")
                elif not (ROOT / p).exists():
                    errs.append(f"미디어 파일 없음: {p}")
            kind = "reels" if typ == "reels" else "image"
            main = [m["path"]] if typ != "carousel" else (m.get("paths") or [])
            for p in main:
                if not str(p).lower().endswith(MEDIA_EXT[kind]):
                    errs.append(f"{typ} 파일 형식이 맞지 않음: {p}")
    if "instagram" in chans and m is not None and len(text_for(post, "instagram")) > IG_LIMIT:
        errs.append(f"인스타 캡션 {len(text_for(post, 'instagram'))}자 > {IG_LIMIT}자 제한")
    return post, errs


def call(api, method, path, params, token):
    params = {**params, "access_token": token}
    data = urllib.parse.urlencode(params).encode()
    url = f"{api}/{path}"
    if method in ("GET", "DELETE"):
        url, data = f"{url}?{data.decode()}", None
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(token, "***")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"연결 실패: {e.reason}") from None


def url_ready(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "kimworld-social"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


# ---------- Threads ----------
def th_publish_one(part, uid, token, reply_to=None):
    params = {"media_type": "TEXT", "text": part["text"]}
    if part.get("link_attachment"):
        params["link_attachment"] = part["link_attachment"]
    if reply_to:
        params["reply_to_id"] = reply_to
    creation = call(TH_API, "POST", f"{uid}/threads", params, token)["id"]
    last = None
    for wait in (3, 10, 20, 30):
        time.sleep(wait)
        try:
            return call(TH_API, "POST", f"{uid}/threads_publish", {"creation_id": creation}, token)["id"]
        except RuntimeError as e:
            last = e
    raise last


def do_threads(post, res, save):
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("THREADS_ACCESS_TOKEN 비밀값이 없음")
    uid = call(TH_API, "GET", "me", {"fields": "id"}, token)["id"]  # 토큰 주인 계정으로 게시
    parts = [{"text": text_for(post, "threads"), "link_attachment": post.get("link_attachment")}] + list(post.get("replies", []) or [])
    ids = res.setdefault("ids", [])
    for i in range(len(ids), len(parts)):
        ids.append(th_publish_one(parts[i], uid, token, reply_to=ids[-1] if ids else None))
        if i == 0:
            try:
                res["permalink"] = call(TH_API, "GET", ids[0], {"fields": "permalink"}, token).get("permalink", "")
            except RuntimeError:
                pass
        save()
    res["done"] = True


# ---------- Instagram ----------
def ig_wait(cid, token, limit=600):
    t0 = time.time()
    while time.time() - t0 < limit:
        st = call(IG_API, "GET", cid, {"fields": "status_code,status"}, token)
        code = st.get("status_code")
        if code in ("FINISHED", "PUBLISHED"):
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"인스타 컨테이너 {code}: {st.get('status', '')}")
        time.sleep(10)
    raise RuntimeError("인스타 컨테이너 처리 시간 초과(10분)")


def do_instagram(post, res, save, now):
    m = post.get("media")
    if not m:
        res.update(done=True, skipped="미디어 없음")
        return
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("IG_ACCESS_TOKEN 비밀값이 없음")
    me = call(IG_API, "GET", "me", {"fields": "user_id,username"}, token)
    uid = str(me.get("user_id") or os.environ.get("IG_USER_ID", ""))
    if os.environ.get("IG_USER_ID") and os.environ["IG_USER_ID"] != uid:
        print("::warning::IG_USER_ID 비밀값이 토큰의 계정 ID와 다름 → 토큰 계정 ID로 게시한다")
    urls = [public_url(p) for p in media_paths(m)]
    if not all(url_ready(u) for u in urls):
        if now - post["_at"] > timedelta(hours=STALE_HOURS):
            raise RuntimeError(f"미디어 주소가 {STALE_HOURS}시간 넘게 열리지 않음(사이트 배포 확인): {urls}")
        res["waiting"] = "미디어 주소 배포 대기"
        return  # 다음 실행에서 다시 시도
    res.pop("waiting", None)
    cap = text_for(post, "instagram")
    typ = m["type"]
    if not res.get("container"):
        if typ == "image":
            cid = call(IG_API, "POST", f"{uid}/media", {"image_url": public_url(m["path"]), "caption": cap}, token)["id"]
        elif typ == "reels":
            prm = {"media_type": "REELS", "video_url": public_url(m["path"]), "caption": cap, "share_to_feed": "true"}
            if m.get("cover"):
                prm["cover_url"] = public_url(m["cover"])
            cid = call(IG_API, "POST", f"{uid}/media", prm, token)["id"]
        else:
            kids = []
            for p in m["paths"]:
                kid = call(IG_API, "POST", f"{uid}/media", {"image_url": public_url(p), "is_carousel_item": "true"}, token)["id"]
                ig_wait(kid, token)
                kids.append(kid)
            cid = call(IG_API, "POST", f"{uid}/media",
                       {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": cap}, token)["id"]
        res["container"] = cid
        save()
    ig_wait(res["container"], token)
    mid = call(IG_API, "POST", f"{uid}/media_publish", {"creation_id": res["container"]}, token)["id"]
    res.update(id=mid, done=True)
    try:
        res["permalink"] = call(IG_API, "GET", mid, {"fields": "permalink"}, token).get("permalink", "")
    except RuntimeError:
        pass
    save()


def ping():
    bad = 0
    th = os.environ.get("THREADS_ACCESS_TOKEN", "")
    ig = os.environ.get("IG_ACCESS_TOKEN", "")
    for name, api, tok, fields in (("Threads", TH_API, th, "id,username"), ("Instagram", IG_API, ig, "user_id,username")):
        if not tok:
            print(f"::error::{name} 토큰 비밀값이 없음")
            bad += 1
            continue
        try:
            me = call(api, "GET", "me", {"fields": fields}, tok)
            print(f"{name} 토큰 정상: @{me.get('username')}")
        except RuntimeError as e:
            print(f"::error::{name} 토큰 확인 실패(만료됐으면 social/README.md 의 갱신 방법 참고): {e}")
            bad += 1
    return 1 if bad else 0


def main(argv):
    if "--ping" in argv:
        return ping()
    if "--delete" in argv:
        i = argv.index("--delete")
        ch, target = (argv[i + 1:i + 3] + ["", ""])[:2]
        if ch != "threads" or not target.isdigit():
            print("::error::사용: --delete threads <숫자 글 ID> (인스타 API는 게시물 삭제를 지원하지 않음)")
            return 1
        try:
            call(TH_API, "DELETE", target, {}, os.environ.get("THREADS_ACCESS_TOKEN", ""))
        except RuntimeError as e:
            print(f"::error::삭제 실패(threads_delete 권한 확인): {e}")
            return 1
        print(f"::notice::삭제함 {target}")
        return 0

    check = "--check" in argv
    QUEUE.mkdir(parents=True, exist_ok=True)
    POSTED.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    bad, due = 0, []
    files = sorted(QUEUE.glob("*.json"))
    for p in files:
        post, errs = load(p)
        if errs:
            bad += 1
            for e in errs:
                print(f"::error file=social/queue/{p.name}::{e}")
            continue
        state = "게시 대상" if post["_at"] <= now else "대기"
        med = f", {post['media']['type']}" if post.get("media") else ""
        print(f"{p.name}: {'+'.join(post['channels'])}{med}, {post['_at'].astimezone(NY):%Y-%m-%d %H:%M} ET, {state}")
        if post["_at"] <= now:
            due.append((p, post))
    print(f"대기열 {len(files)}개, 게시 대상 {len(due)}개, 검사 실패 {bad}개")
    if check or not due:
        return 1 if bad else 0

    failed = 0
    for p, post in sorted(due, key=lambda x: x[1]["_at"]):
        raw = json.loads(p.read_text(encoding="utf-8"))
        results = raw.setdefault("results", {})

        def save():
            p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        for ch in post["channels"]:
            res = results.setdefault(ch, {})
            if res.get("done"):
                continue
            try:
                if ch == "threads":
                    do_threads(post, res, save)
                else:
                    do_instagram(post, res, save, now)
            except RuntimeError as e:
                failed += 1
                res["last_error"] = str(e)[:300]
                print(f"::error file=social/queue/{p.name}::{ch} 게시 실패: {e}")
            save()
        if all(results.get(ch, {}).get("done") for ch in post["channels"]):
            raw["posted_at"] = datetime.now(NY).isoformat(timespec="seconds")
            dest = POSTED / p.name
            if dest.exists():
                dest = POSTED / f"{p.stem}-{int(time.time())}.json"
            dest.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            p.unlink()
            links = ", ".join(f"{c}: {results[c].get('permalink') or results[c].get('skipped') or 'ok'}" for c in post["channels"])
            print(f"::notice::게시함 {p.name} → {links}")
        elif any(r.get("waiting") for r in results.values()):
            print(f"{p.name}: 미디어 배포 대기 — 다음 실행에서 이어서 게시")
    return 1 if (bad or failed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
