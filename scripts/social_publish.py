"""SNS 예약 게시 (Threads + Instagram + Facebook 페이지).

social/queue/*.json 의 게시물 가운데 publish_at 이 지난 것을 채널별로 게시하고, 모든 채널이 끝나면
social/posted/ 로 옮긴다(커밋은 워크플로가 한다).

게시물 파일 형식:
  {
    "text": "공통 본문",
    "publish_at": "2026-10-14T19:30:00-04:00",        # 시간대가 없으면 America/New_York
    "channels": ["threads", "instagram", "facebook"],
    "media": {"type": "reels", "path": "static/social/lhx/LHX_shorts.mp4"},   # 선택
    "channel_text": {"instagram": "인스타 전용 캡션"},  # 선택: 채널별 본문
    "replies": [{"text": "...", "link_attachment": "https://..."}],  # 선택: Threads 이어지는 댓글
    "link_attachment": "https://...",                   # 선택: Threads 링크 카드
    "poll": ["보기 1", "보기 2", "보기 3"]               # 선택: Threads 본문 투표(보기 2~4개, 각 25바이트 이하 = 한글 약 8자, 24시간)
  }
  poll 은 Threads 본문에 투표로 붙고 link_attachment 와 함께 쓸 수 없다. 링크는 replies 에 둔다.
  인스타·페이스북은 API로 투표를 넣을 수 없어 본문 끝에 '① 보기 …'로 글로 붙인다(릴스 파일에도 poll 을 넣으면 같다).
  media.type: image | carousel | reels
    image  → "path": 이미지 1장 (JPEG 권장)
    carousel → "paths": [이미지 2~10장]
    reels  → "path": MP4(세로 9:16, 3~90초 권장), 선택 "cover": 표지 이미지 경로
  path 는 저장소 기준 경로이며 static/social/ 아래에 둔다 → https://drkimworld.com/static/social/... 로 공개된다
  (사이트 배포가 끝나 주소가 200을 돌려줄 때까지 인스타 게시는 다음 실행으로 미룬다).
  Threads 는 TEXT 게시만 한다(미디어는 쓰지 않음). 미디어가 없는 글은 인스타를 건너뛴다.
  Facebook 페이지(운영자 지시 2026-10-15, Graph API v26.0):
    미디어 없음 → /{page}/feed 에 본문(text 또는 channel_text.facebook), replies[0] 은 첫 댓글로 단다
                  (링크의 utm_source=threads 는 facebook 으로 바꾼다). poll 은 본문 끝에 글로 붙인다
    reels      → /{page}/video_reels 3단계(start → rupload 파일 직접 업로드(없으면 file_url) → finish), 캡션은 channel_text.facebook 또는 인스타 캡션
    image      → /{page}/photos (url, message),  carousel → photos(published=false) 뒤 feed(attached_media)
    190(토큰)·200(권한) 오류는 재시도하지 않는다. 일시 오류(5xx·속도 제한)는 간격을 두고 최대 3회 재시도한다.
    앱이 개발 모드라 공개 노출을 사람이 확인해야 한다: social/FACEBOOK_LIVE 파일이 없으면 페이스북 게시는
    한 건(첫 확인용)만 하고 나머지는 '공개 확인 대기'로 미룬다. 로그아웃 상태에서 보이는 것을 확인한 뒤 파일을 만든다.

사용:
  python scripts/social_publish.py              # 검사 + 시간이 된 글 게시
  python scripts/social_publish.py --check      # 검사만
  python scripts/social_publish.py --ping       # 두 채널 토큰 확인
  python scripts/social_publish.py --delete threads <글 ID>   # Threads 글 삭제(threads_delete 권한 필요)

비밀값(환경변수): THREADS_ACCESS_TOKEN, THREADS_USER_ID, IG_ACCESS_TOKEN, IG_USER_ID, FB_PAGE_ID, FB_PAGE_TOKEN.
값은 출력하지 않는다. 페이지 토큰은 시스템 사용자(kimworld-bot) 토큰이라 만료가 없다.
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
FB_API = "https://graph.facebook.com/v26.0"
FB_RUPLOAD = "https://rupload.facebook.com/video-upload/v26.0"
FB_LIVE = ROOT / "social" / "FACEBOOK_LIVE"
TH_LIMIT = 500
POLL_OPTION_LIMIT = 25  # Threads 는 UTF-8 바이트로 센다(한글 약 8자). 2026-10-15 실제 게시에서 확인
POLL_KEYS = ("option_a", "option_b", "option_c", "option_d")
IG_LIMIT = 2200
CHANNELS = ("threads", "instagram", "facebook")
MEDIA_EXT = {"image": (".jpg", ".jpeg", ".png"), "reels": (".mp4", ".mov")}
STALE_HOURS = 6  # 미디어 주소가 이 시간 넘게 열리지 않으면 실패로 표시
TH_TOPIC_DEFAULT = "미국주식"  # Threads 주제 태그 기본값(글마다 "topic_tag"로 바꾼다, 코인 글은 "코인")
# 한국 시청자가 많이 보는 시각(KST). 새 글은 바로 올리지 않고 다음 칸에 넣는다(운영자 지시 2026-10-20)
KST = ZoneInfo("Asia/Seoul")
SLOTS_KST = ((7, 40), (12, 10), (18, 40), (21, 10))
SLOT_GAP_HOURS = 3  # 같은 칸에 두 글이 겹치지 않게, 대기열·최근 게시 글과 이 시간 이상 띄운다


def next_slot(now=None, taken=()):
    """지금 이후 가장 가까운 KST 황금 시간 칸(이미 잡힌 시각과 SLOT_GAP_HOURS 안이면 다음 칸)."""
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    taken = [t.astimezone(KST) for t in taken]
    day = now.date()
    for d in range(0, 8):
        for h, m in SLOTS_KST:
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=KST) + timedelta(days=d)
            if t <= now + timedelta(minutes=5):
                continue
            if all(abs((t - x).total_seconds()) >= SLOT_GAP_HOURS * 3600 for x in taken):
                return t
    return now + timedelta(hours=1)


def taken_times():
    out = []
    for q in list(QUEUE.glob("*.json")) + list(POSTED.glob("*.json")):
        try:
            d = json.loads(q.read_text(encoding="utf-8"))
            t = parse_time(d.get("posted_at") or d.get("publish_at") or "")
        except Exception:
            continue
        if t:
            out.append(t)
    return out


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


NUMS = "①②③④"


def with_poll_text(text, post):
    """투표를 API로 넣을 수 없는 인스타는 poll 보기를 본문 끝에 글로 붙인다(운영자 지시 2026-10-15).
    페이스북은 붙이지 않는다(운영자 지시 2026-10-16: 참여 유도 글 노출 감소 위험)."""
    poll = post.get("poll")
    if not isinstance(poll, list) or not 2 <= len(poll) <= 4 or "①" in text:
        return text
    lines = "\n".join(f"{NUMS[i]} {o}" for i, o in enumerate(poll))
    return f"{text.rstrip()}\n\n여러분의 생각은? 댓글에 번호로 남겨 주세요.\n{lines}"


def ig_caption(post):
    return with_poll_text(text_for(post, "instagram"), post)


def fb_text(post):
    """페이스북 본문. 릴스·사진 글은 인스타 캡션을 함께 쓴다. poll 보기는 붙이지 않는다(참여 유도 감점 회피, 2026-10-16)."""
    ct = post.get("channel_text") or {}
    if ct.get("facebook"):
        t = ct["facebook"]
    elif post.get("media") and ct.get("instagram"):
        t = ct["instagram"]
    else:
        t = post.get("text", "")
    return t


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
        poll = post.get("poll")
        if poll is not None:
            if not isinstance(poll, list) or not 2 <= len(poll) <= 4:
                errs.append("poll 은 보기 2~4개의 목록이어야 함")
            else:
                for i, o in enumerate(poll, 1):
                    if not isinstance(o, str) or not o.strip():
                        errs.append(f"poll[{i}] 보기가 비어 있음")
                    elif len(o.encode("utf-8")) > POLL_OPTION_LIMIT:
                        errs.append(f"poll[{i}] {len(o.encode('utf-8'))}바이트 > {POLL_OPTION_LIMIT}바이트 제한(한글 1자 = 3바이트)")
            if post.get("link_attachment"):
                errs.append("poll 과 link_attachment 는 함께 쓸 수 없음(링크는 replies 에)")
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
    if "facebook" in chans and not fb_text(post).strip():
        errs.append("페이스북 본문이 비어 있음")
    if "instagram" in chans and m is not None and len(ig_caption(post)) > IG_LIMIT:
        errs.append(f"인스타 캡션 {len(ig_caption(post))}자 > {IG_LIMIT}자 제한")
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
    if part.get("poll"):
        params["poll_attachment"] = json.dumps(dict(zip(POLL_KEYS, part["poll"])), ensure_ascii=False)
    if part.get("topic_tag"):
        params["topic_tag"] = part["topic_tag"]
    if reply_to:
        params["reply_to_id"] = reply_to
    try:
        creation = call(TH_API, "POST", f"{uid}/threads", params, token)["id"]
    except RuntimeError as e:  # 주제 태그를 받지 않는 경우에도 글은 올린다
        if "topic_tag" not in params:
            raise
        print(f"::warning::Threads 주제 태그 없이 다시 시도: {str(e)[:120]}")
        params.pop("topic_tag")
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
    # 주제 태그(운영자 지시 2026-10-20 'SNS 알고리즘 선택'): 팔로워가 거의 없는 계정은 주제 피드가 첫 노출 통로다
    tag = post.get("topic_tag", TH_TOPIC_DEFAULT)
    parts = [{"text": text_for(post, "threads"), "link_attachment": post.get("link_attachment"), "poll": post.get("poll"), "topic_tag": tag}] + list(post.get("replies", []) or [])
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
    cap = ig_caption(post)
    typ = m["type"]
    if not res.get("container"):
        if typ == "image":
            cid = call(IG_API, "POST", f"{uid}/media", {"image_url": public_url(m["path"]), "caption": cap}, token)["id"]
        elif typ == "reels":
            prm = {"media_type": "REELS", "video_url": public_url(m["path"]), "caption": cap, "share_to_feed": "true"}
            if m.get("cover"):
                prm["cover_url"] = public_url(m["cover"])
            # 체험 릴스(운영자 지시 2026-10-20): 팔로워 3명 계정이라 팔로워 아닌 사람에게 먼저 보이고, 반응이 좋으면 자동으로 일반 릴스가 된다
            if m.get("trial", True):
                prm["trial_params"] = json.dumps({"graduation_strategy": "SS_PERFORMANCE"})
            try:
                cid = call(IG_API, "POST", f"{uid}/media", prm, token)["id"]
            except RuntimeError as e:
                if "trial_params" not in prm:
                    raise
                print(f"::warning::인스타 체험 릴스 없이 다시 시도: {str(e)[:120]}")
                prm.pop("trial_params")
                res["trial"] = "unsupported"
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


# ---------- Facebook 페이지 ----------
class FbFatal(RuntimeError):
    """재시도하면 안 되는 오류(190 토큰, 200 권한)."""


def fb_call(method, path, params, token, base=FB_API, headers=None, body=None):
    """Graph API 호출(body를 주면 그 바이트를 그대로 보낸다). 190·200은 바로 실패, 일시 오류는 20·60·120초 간격으로 최대 3회 재시도."""
    last = None
    for wait in (0, 20, 60, 120):
        if wait:
            time.sleep(wait)
        q = {**params}
        data = body if body is not None else urllib.parse.urlencode(q).encode()
        url = f"{base}/{path}"
        if method == "GET":
            url, data = f"{url}?{data.decode()}", None
        req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"OAuth {token}", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            ebody = e.read().decode(errors="replace").replace(token, "***")  # body(보낼 바이트)를 덮지 않는다
            try:
                err = json.loads(ebody).get("error", {})
            except ValueError:
                err = {}
            code = err.get("code")
            msg = f"HTTP {e.code} code={code}: {err.get('message', ebody)[:240]}"
            if code in (190, 200) or (isinstance(code, int) and 200 <= code < 300) or e.code in (400, 401, 403) and code not in (1, 2, 4, 17, 32, 341, 613):
                raise FbFatal(msg) from None
            last = RuntimeError(msg)
        except urllib.error.URLError as e:
            last = RuntimeError(f"연결 실패: {e.reason}")
    raise last


def local_file(rel):
    """저장소 안의 미디어 파일(있으면 Path). 페이스북은 사이트 주소를 못 가져오는 경우가 있어(403) 파일을 직접 올린다."""
    f = ROOT / rel.lstrip("/")
    return f if f.is_file() else None


def fb_photo(page, rel, params, token):
    f = local_file(rel)
    if not f:
        return fb_call("POST", f"{page}/photos", {"url": public_url(rel), **params}, token)
    b = "----kimworld" + os.urandom(8).hex()
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in params.items()]
    ctype = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="source"; filename="{f.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
                 + f.read_bytes() + f"\r\n--{b}--\r\n".encode())
    return fb_call("POST", f"{page}/photos", params, token, headers={"Content-Type": f"multipart/form-data; boundary={b}"},
                   body=b"".join(parts))


def fb_comment_text(text):
    return text.replace("utm_source=threads", "utm_source=facebook")


def do_facebook(post, res, save, now, live_used):
    token = os.environ.get("FB_PAGE_TOKEN", "")
    page = os.environ.get("FB_PAGE_ID", "")
    if not token or not page:
        raise RuntimeError("FB_PAGE_TOKEN·FB_PAGE_ID 비밀값이 없음")
    if not FB_LIVE.exists() and not res.get("post_id") and live_used[0] >= 1:
        res["waiting"] = "공개 확인 대기(social/FACEBOOK_LIVE 없음)"
        return
    m = post.get("media")
    msg = fb_text(post)
    if not res.get("post_id"):
        if m:
            urls = [public_url(p) for p in media_paths(m) if not local_file(p)]
            if not all(url_ready(u) for u in urls):
                if now - post["_at"] > timedelta(hours=STALE_HOURS):
                    raise RuntimeError(f"미디어 주소가 {STALE_HOURS}시간 넘게 열리지 않음: {urls}")
                res["waiting"] = "미디어 주소 배포 대기"
                return
        res.pop("waiting", None)
        live_used[0] += 1
        if not m:
            r = fb_call("POST", f"{page}/feed", {"message": msg}, token)
            res["post_id"] = r["id"]
        elif m["type"] == "reels":
            if not res.get("video_id"):
                st = fb_call("POST", f"{page}/video_reels", {"upload_phase": "start"}, token)
                res["video_id"] = st["video_id"]
                save()
            f = local_file(m["path"])
            try:
                if f:
                    data = f.read_bytes()
                    fb_call("POST", res["video_id"], {}, token, base=FB_RUPLOAD,
                            headers={"offset": "0", "file_size": str(len(data)), "Content-Type": "application/octet-stream"}, body=data)
                else:
                    fb_call("POST", res["video_id"], {}, token, base=FB_RUPLOAD, headers={"file_url": public_url(m["path"])})
            except FbFatal:
                res.pop("video_id", None)  # 실패한 업로드 세션은 버리고 다음 실행에서 새로 시작
                save()
                raise
            fb_call("POST", f"{page}/video_reels", {"upload_phase": "finish", "video_id": res["video_id"],
                                                    "video_state": "PUBLISHED", "description": msg}, token)
            res["post_id"] = res["video_id"]
        elif m["type"] == "image":
            r = fb_photo(page, m["path"], {"message": msg}, token)
            res["post_id"] = r.get("post_id") or r["id"]
        else:
            ids = []
            for p in m["paths"]:
                ids.append(fb_photo(page, p, {"published": "false"}, token)["id"])
            r = fb_call("POST", f"{page}/feed", {"message": msg,
                        "attached_media": json.dumps([{"media_fbid": i} for i in ids])}, token)
            res["post_id"] = r["id"]
        save()
    reps = post.get("replies") or []
    if reps and not res.get("comment_id") and (not m or m["type"] == "reels"):
        try:
            res["comment_id"] = fb_call("POST", f"{res['post_id']}/comments", {"message": fb_comment_text(reps[0]["text"])}, token)["id"]
            res.pop("comment_error", None)
        except RuntimeError as e:
            if not m:
                raise
            res["comment_error"] = str(e)[:200]  # 릴스 첫 댓글 실패는 게시를 막지 않는다
        save()
    try:
        field = "permalink_url"
        res["permalink"] = fb_call("GET", res["post_id"], {"fields": field}, token).get(field, "")
    except RuntimeError:
        pass
    res["done"] = True
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
    fb_tok, fb_page = os.environ.get("FB_PAGE_TOKEN", ""), os.environ.get("FB_PAGE_ID", "")
    if not fb_tok or not fb_page:
        print("::error::Facebook 페이지 비밀값(FB_PAGE_ID, FB_PAGE_TOKEN)이 없음")
        bad += 1
    else:
        try:
            me = fb_call("GET", fb_page, {"fields": "name"}, fb_tok)
            print(f"Facebook 페이지 토큰 정상: {me.get('name')}")
        except RuntimeError as e:
            print(f"::error::Facebook 페이지 토큰 확인 실패: {e}")
            bad += 1
    return 1 if bad else 0


def main(argv):
    if "--ping" in argv:
        return ping()
    if "--next-slot" in argv:  # 새 SNS 글의 publish_at 으로 쓸 다음 황금 시간 칸(미국 동부시간 ISO)
        print(next_slot(taken=taken_times()).astimezone(NY).isoformat(timespec="minutes"))
        return 0
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
    live_used = [0]  # FACEBOOK_LIVE 가 없을 때 이번 실행에서 새로 올린 페이스북 글 수
    if not FB_LIVE.exists():
        live_used[0] = sum(1 for q in POSTED.glob("*.json") if (json.loads(q.read_text(encoding="utf-8")).get("results", {}).get("facebook", {}).get("post_id")))
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
                elif ch == "facebook":
                    do_facebook(post, res, save, now, live_used)
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
            print(f"{p.name}: " + ", ".join(f"{c} {r['waiting']}" for c, r in results.items() if r.get("waiting")) + " — 다음 실행에서 이어서 게시")
    return 1 if (bad or failed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
