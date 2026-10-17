"""SNS 댓글 모니터링 (Threads + Instagram + Facebook 페이지). 운영자 지시 2026-10-15.

유튜브 댓글 자동 답글(kimworld-media tools/yt_reply.py)과 같은 요령으로, 우리 게시물에 달린 시청자 댓글과
대댓글 가운데 답할 차례인 것을 모으고, 세션이 쓴 답글을 게시한다. 토큰은 GitHub 비밀값에만 있으므로
워크플로(.github/workflows/social-comments.yml)에서 실행한다.

사용:
  python scripts/social_comments.py --list [--days 7] [--out open.json | --log]
      답할 차례인 댓글을 JSON 으로 낸다. 항목:
        kind=top      : 우리 게시물에 달린 시청자 댓글에 우리 답글이 아직 없다.
        kind=followup : 우리 답글(또는 우리가 쓴 댓글) 뒤에 시청자 대댓글이 새로 달렸다.
        replyTo       : --post 답글 파일의 "to" 에 넣을 ID
        context       : 그 댓글까지의 대화(시간순), slug: 게시 기록·본문 링크로 찾은 리포트 slug(없으면 "")
  python scripts/social_comments.py --probe
      채널마다 토큰·게시물 목록·댓글 읽기 권한을 확인한다(답글 쓰기 권한은 실제로 달아 봐야 안다).
  python scripts/social_comments.py --post
      social/replies/*.json 의 답글을 게시하고 결과를 파일의 "results" 에 적은 뒤 social/replies/done/ 으로 옮긴다.
      답글 파일 형식: {"replies": [{"platform": "threads|instagram|facebook", "to": "<replyTo>", "text": "...", "kind": "top|followup|request"}]}
      본문의 리포트 링크(drkimworld.com/r/<slug>/)에는 게시 직전에 위치별 UTM 을 붙인다(운영자 지시 2026-10-16):
      utm_source=<채널>&utm_medium=comment&utm_campaign=<slug>&utm_content=reply|followup|request
      (kind 가 top·없음이면 reply, followup 이면 대댓글 followup, request 면 종목 요청 답글 request). 이미 있는 utm 값은 덮어쓴다.
      결과가 이미 있는 항목(성공·실패 모두)은 다시 달지 않는다(중복 방지).

비밀값(환경변수): THREADS_ACCESS_TOKEN, IG_ACCESS_TOKEN, FB_PAGE_ID, FB_PAGE_TOKEN. 값은 출력하지 않는다.
필요 권한: Threads threads_read_replies·threads_manage_replies, Instagram instagram_business_manage_comments,
Facebook pages_read_engagement·pages_read_user_content·pages_manage_engagement.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from social_publish import FB_API, IG_API, TH_API, POSTED, ROOT, call, fb_call, th_publish_one  # noqa: E402

REPLIES = ROOT / "social" / "replies"
DONE = REPLIES / "done"
POST_WINDOW_DAYS = 60   # 이 기간 안에 올린 게시물의 댓글을 본다
MAX_PER_FILE = 30
LIMITS = {"threads": 500, "instagram": 2200, "facebook": 8000}
SLUG_RE = re.compile(r"drkimworld\.com/r/([a-z0-9-]+)/")
LINK_RE = re.compile(r"https?://(?:www\.)?drkimworld\.com/r/([a-z0-9-]+)/(\?[^\s]*)?")
UTM_CONTENT = {"top": "reply", "reply": "reply", "followup": "followup", "request": "request"}


def tag_links(text, source, kind):
    """답글 본문의 리포트 링크에 위치별 UTM 을 붙인다. 댓글 답글(reply)·대댓글 답글(followup)·종목 요청 답글(request)을 따로 센다."""
    content = UTM_CONTENT.get(kind or "top", "reply")

    def sub(m):
        slug, q = m.group(1), (m.group(2) or "")[1:]
        keep = [kv for kv in q.split("&") if kv and not kv.startswith("utm_")]
        utm = [f"utm_source={source}", "utm_medium=comment", f"utm_campaign={slug}", f"utm_content={content}"]
        return f"https://drkimworld.com/r/{slug}/?" + "&".join(keep + utm)
    return LINK_RE.sub(sub, text)


def ts(s):
    s = s.replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-2] + ":" + s[-2:]
    return datetime.fromisoformat(s)


def slug_of_file(name):
    m = re.match(r"^(.*?-\d{4}-\d{2})(?:-.+)?$", name)
    return m.group(1) if m else re.sub(r"-(\d+|reels)$", "", name)


def posted_map():
    """게시 기록에서 채널별 게시물 ID → 리포트 slug."""
    out = {}
    for p in POSTED.glob("*.json"):
        try:
            res = json.loads(p.read_text(encoding="utf-8")).get("results", {})
        except ValueError:
            continue
        slug = slug_of_file(p.stem)
        ids = list((res.get("threads") or {}).get("ids") or [])
        ids += [(res.get("instagram") or {}).get("id"), (res.get("facebook") or {}).get("post_id"), (res.get("facebook") or {}).get("video_id")]
        for i in ids:
            if i:
                out[str(i)] = slug
    return out


def find_slug(pid, texts, pmap):
    if pid in pmap:
        return pmap[pid]
    for t in texts:
        m = SLUG_RE.search(t or "")
        if m:
            return m.group(1)
    return ""


def msg(c):
    return {k: c[k] for k in ("author", "isMe", "text", "publishedAt")}


# ---------- 답할 차례 판정(순수 함수, tests/test_comments.py) ----------
def open_two_level(top, replies, since, now):
    """인스타·페이스북·유튜브처럼 '댓글 + 한 단계 답글' 구조. top·replies 는 {id, author, isMe, text, publishedAt}.
    돌려주는 값: None 또는 {kind, target, followups, context, mine24}."""
    conv = sorted([top] + list(replies), key=lambda c: c["publishedAt"])
    if max(ts(c["publishedAt"]) for c in conv) < since:
        return None
    mine = [c for c in conv if c["isMe"]]
    mine24 = sum(1 for c in mine if c is not top and ts(c["publishedAt"]) >= now - timedelta(hours=24))
    if not mine:
        if ts(top["publishedAt"]) < since:
            return None
        return {"kind": "top", "target": top, "followups": [], "context": [msg(top)], "mine24": 0}
    last = max(ts(c["publishedAt"]) for c in mine)
    fu = [c for c in conv if not c["isMe"] and ts(c["publishedAt"]) > last and ts(c["publishedAt"]) >= since]
    if not fu:
        return None
    return {"kind": "followup", "target": fu[-1], "followups": fu, "context": [msg(c) for c in conv][-12:], "mine24": mine24}


def open_tree(root_id, comments, since, now):
    """Threads 처럼 답글이 나무 구조인 경우. comments: {id, parent, author, isMe, text, publishedAt}.
    우리 글(본문·우리 답글)에 직접 단 시청자 댓글 가운데 우리가 아직 답하지 않은 것만 고른다(시청자끼리 대화는 뺀다)."""
    by = {c["id"]: c for c in comments}
    mine_ids = {c["id"] for c in comments if c["isMe"]} | {root_id}
    answered = {c["parent"] for c in comments if c["isMe"]}
    out = []
    for c in sorted(comments, key=lambda x: x["publishedAt"]):
        if c["isMe"] or c["parent"] not in mine_ids or c["id"] in answered or ts(c["publishedAt"]) < since:
            continue
        chain, p = [c], c["parent"]
        while p in by:
            chain.insert(0, by[p])
            p = by[p]["parent"]
        branch_mine = [x for x in chain if x["isMe"]]
        mine24 = sum(1 for x in branch_mine if ts(x["publishedAt"]) >= now - timedelta(hours=24))
        out.append({"kind": "top" if c["parent"] == root_id else "followup", "target": c, "followups": [c] if c["parent"] != root_id else [],
                    "context": [msg(x) for x in chain][-12:], "mine24": mine24})
    return out


def item(platform, post, slug, o, reply_to):
    t = o["target"]
    return {"platform": platform, "kind": o["kind"], "replyTo": reply_to, "commentId": t["id"], "postId": post["id"],
            "postPermalink": post.get("permalink", ""), "postText": (post.get("text") or "")[:200], "slug": slug,
            "author": t["author"], "text": t["text"], "publishedAt": t["publishedAt"], "likeCount": t.get("likeCount", 0),
            "followups": [msg(x) for x in o["followups"]], "context": o["context"], "my_replies_in_thread_24h": o["mine24"]}


def pages(fetch, first, limit=20):
    """Graph API 쪽 넘기기. fetch(path_or_url, params) 가 dict 를 돌려준다."""
    r, n = fetch(*first), 0
    while True:
        yield from r.get("data", [])
        nxt = (r.get("paging") or {}).get("cursors", {}).get("after") if (r.get("paging") or {}).get("next") else None
        n += 1
        if not nxt or n >= limit:
            return
        path, params = first
        r = fetch(path, {**params, "after": nxt})


# ---------- Threads ----------
def list_threads(since, now, pmap):
    tok = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if not tok:
        raise RuntimeError("THREADS_ACCESS_TOKEN 비밀값이 없음")
    f = lambda p, q: call(TH_API, "GET", p, q, tok)  # noqa: E731
    me = f("me", {"fields": "id,username"})
    oldest = int((now - timedelta(days=POST_WINDOW_DAYS)).timestamp())
    out, mine24 = [], 0
    for post in pages(f, ("me/threads", {"fields": "id,text,permalink,timestamp", "since": oldest, "limit": 50})):
        conv = list(pages(f, (f"{post['id']}/conversation", {"fields": "id,text,username,timestamp,replied_to,is_reply_owned_by_me,hide_status", "reverse": "false", "limit": 100})))
        cs = [{"id": c["id"], "parent": (c.get("replied_to") or {}).get("id", post["id"]), "author": c.get("username", ""),
               "isMe": bool(c.get("is_reply_owned_by_me")) or c.get("username") == me.get("username"), "text": c.get("text", ""),
               "publishedAt": c["timestamp"]} for c in conv if c.get("hide_status") not in ("HIDDEN", "COVERED", "BLOCKED", "RESTRICTED")]
        own = {post["id"]} | {c["id"] for c in cs if c["isMe"]}
        mine24 += sum(1 for c in cs if c["isMe"] and c["parent"] not in own and ts(c["publishedAt"]) >= now - timedelta(hours=24))  # 링크 답글 등 우리 글에 단 답글은 빼고 시청자에게 단 답글만 센다
        slug = find_slug(post["id"], [post.get("text")] + [c["text"] for c in cs if c["isMe"]], pmap)
        for o in open_tree(post["id"], cs, since, now):
            out.append(item("threads", post, slug, o, o["target"]["id"]))
    return {"ok": True, "me": me.get("username"), "my_replies_24h": mine24, "open": out}


# ---------- Instagram ----------
def list_instagram(since, now, pmap):
    tok = os.environ.get("IG_ACCESS_TOKEN", "")
    if not tok:
        raise RuntimeError("IG_ACCESS_TOKEN 비밀값이 없음")
    f = lambda p, q: call(IG_API, "GET", p, q, tok)  # noqa: E731
    me = f("me", {"fields": "user_id,username"})
    uname = me.get("username")
    oldest = now - timedelta(days=POST_WINDOW_DAYS)
    out, mine24 = [], 0
    norm = lambda c: {"id": c["id"], "author": c.get("username") or (c.get("from") or {}).get("username", ""),  # noqa: E731
                      "isMe": (c.get("username") or (c.get("from") or {}).get("username")) == uname, "text": c.get("text", ""),
                      "publishedAt": c["timestamp"], "likeCount": c.get("like_count", 0)}
    for post in pages(f, ("me/media", {"fields": "id,caption,permalink,timestamp,comments_count", "limit": 50}), limit=4):
        if ts(post["timestamp"]) < oldest:
            break
        if not post.get("comments_count"):
            continue
        post = {**post, "text": post.get("caption", "")}
        slug = find_slug(post["id"], [post["text"]], pmap)
        for c in pages(f, (f"{post['id']}/comments", {"fields": "id,text,username,timestamp,like_count,from{id,username},replies{id,text,username,timestamp,from{id,username}}", "limit": 50})):
            top, reps = norm(c), [norm(r) for r in (c.get("replies") or {}).get("data", [])]
            mine24 += sum(1 for r in reps if r["isMe"] and ts(r["publishedAt"]) >= now - timedelta(hours=24))
            o = open_two_level(top, reps, since, now)
            if o:
                out.append(item("instagram", post, slug, o, top["id"]))
    return {"ok": True, "me": uname, "my_replies_24h": mine24, "open": out}


# ---------- Facebook ----------
def list_facebook(since, now, pmap):
    tok, page = os.environ.get("FB_PAGE_TOKEN", ""), os.environ.get("FB_PAGE_ID", "")
    if not tok or not page:
        raise RuntimeError("FB_PAGE_TOKEN·FB_PAGE_ID 비밀값이 없음")
    f = lambda p, q: fb_call("GET", p, q, tok)  # noqa: E731
    oldest = int((now - timedelta(days=POST_WINDOW_DAYS)).timestamp())
    posts = list(pages(f, (f"{page}/posts", {"fields": "id,message,created_time,permalink_url", "since": oldest, "limit": 50}), limit=4))
    try:
        posts += [{**v, "message": v.get("description", "")} for v in pages(f, (f"{page}/video_reels", {"fields": "id,description,created_time,permalink_url", "since": oldest, "limit": 50}), limit=2)]
    except RuntimeError:
        pass
    norm = lambda c: {"id": c["id"], "author": (c.get("from") or {}).get("name", ""), "isMe": (c.get("from") or {}).get("id") == page,  # noqa: E731
                      "text": c.get("message", ""), "publishedAt": c["created_time"], "likeCount": c.get("like_count", 0)}
    out, mine24 = [], 0
    for p in posts:
        post = {"id": p["id"], "text": p.get("message", ""), "permalink": p.get("permalink_url", "")}
        comments = list(pages(f, (f"{p['id']}/comments", {"filter": "toplevel", "order": "chronological", "limit": 50,
                                                           "fields": "id,message,from{id,name},created_time,like_count,comments.limit(50){id,message,from{id,name},created_time}"})))
        texts = [post["text"]] + [c.get("message", "") for c in comments if (c.get("from") or {}).get("id") == page]
        slug = find_slug(p["id"], texts, pmap)
        for c in comments:
            top, reps = norm(c), [norm(r) for r in (c.get("comments") or {}).get("data", [])]
            mine24 += sum(1 for r in reps if r["isMe"] and ts(r["publishedAt"]) >= now - timedelta(hours=24))
            o = open_two_level(top, reps, since, now)
            if o:
                out.append(item("facebook", post, slug, o, top["id"]))
    return {"ok": True, "me": page, "my_replies_24h": mine24, "open": out}


LISTERS = {"threads": list_threads, "instagram": list_instagram, "facebook": list_facebook}


def list_all(days):
    now = datetime.now(timezone.utc)
    since, pmap, res = now - timedelta(days=days), posted_map(), {}
    for name, fn in LISTERS.items():
        try:
            res[name] = fn(since, now, pmap)
        except RuntimeError as e:
            res[name] = {"ok": False, "error": str(e)[:400]}
    return {"generated": now.isoformat(timespec="seconds"), "since": since.isoformat(timespec="seconds"), "platforms": res}


def probe():
    r = list_all(7)
    bad = 0
    for name, v in r["platforms"].items():
        if v["ok"]:
            print(f"{name}: 댓글 읽기 정상 (@{v['me']}) · 답할 차례 {len(v['open'])}개 · 최근 24시간 우리 답글 {v['my_replies_24h']}개")
        else:
            bad += 1
            print(f"::warning::{name}: 댓글 읽기 실패 — {v['error']}")
    return 1 if bad == len(r["platforms"]) else 0


# ---------- 답글 게시 ----------
def post_one(platform, to, text):
    if platform == "threads":
        tok = os.environ["THREADS_ACCESS_TOKEN"]
        uid = call(TH_API, "GET", "me", {"fields": "id"}, tok)["id"]
        return th_publish_one({"text": text}, uid, tok, reply_to=to)
    if platform == "instagram":
        return call(IG_API, "POST", f"{to}/replies", {"message": text}, os.environ["IG_ACCESS_TOKEN"])["id"]
    if platform == "facebook":
        return fb_call("POST", f"{to}/comments", {"message": text}, os.environ["FB_PAGE_TOKEN"])["id"]
    raise RuntimeError(f"모르는 채널: {platform}")


# 홍보·스팸 댓글 조치(운영자 지시 2026-10-17 "홍보글 다는 애들은 차단하거나 삭제하거나 권한 내에서 적절히 조치"):
# 답글 파일 항목에 "action":"hide"|"delete" 를 주면 text 없이 그 댓글을 숨기거나 지운다.
#  - Threads: 남의 답글은 지울 수 없어 숨긴다(manage_reply hide). delete 를 줘도 숨김으로 처리한다.
#  - 인스타그램: hide=true(숨김) 또는 DELETE(내 게시물의 댓글 삭제).
#  - 페이스북: is_hidden=true(숨김) 또는 DELETE.
def moderate_one(platform, to, action):
    if platform == "threads":
        call(TH_API, "POST", f"{to}/manage_reply", {"hide": "true"}, os.environ["THREADS_ACCESS_TOKEN"])
        return "hidden"
    if platform == "instagram":
        tok = os.environ["IG_ACCESS_TOKEN"]
        if action == "delete":
            call(IG_API, "DELETE", to, {}, tok); return "deleted"
        call(IG_API, "POST", to, {"hide": "true"}, tok); return "hidden"
    if platform == "facebook":
        tok = os.environ["FB_PAGE_TOKEN"]
        if action == "delete":
            fb_call("DELETE", to, {}, tok); return "deleted"
        fb_call("POST", to, {"is_hidden": "true"}, tok); return "hidden"
    raise RuntimeError(f"모르는 채널: {platform}")


def check_reply(r):
    errs = []
    if r.get("action") is not None:
        if r.get("action") not in ("hide", "delete"):
            errs.append(f"action 이 맞지 않음: {r.get('action')}")
        if r.get("platform") not in LIMITS:
            errs.append(f"platform 이 맞지 않음: {r.get('platform')}")
        if not re.fullmatch(r"[0-9_A-Za-z.-]+", str(r.get("to", ""))):
            errs.append(f"to 가 맞지 않음: {r.get('to')}")
        return errs
    if r.get("platform") not in LIMITS:
        errs.append(f"platform 이 맞지 않음: {r.get('platform')}")
    if not re.fullmatch(r"[0-9_A-Za-z.-]+", str(r.get("to", ""))):
        errs.append(f"to 가 맞지 않음: {r.get('to')}")
    t = (r.get("text") or "").strip()
    if not t:
        errs.append("text 가 비어 있음")
    elif r.get("platform") in LIMITS and len(t) > LIMITS[r["platform"]]:
        errs.append(f"{r['platform']} 글자 수 초과 {len(t)} > {LIMITS[r['platform']]}")
    return errs


def post_files():
    DONE.mkdir(parents=True, exist_ok=True)
    bad = 0
    for p in sorted(REPLIES.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        reps = d.get("replies", [])[:MAX_PER_FILE]
        res = d.setdefault("results", [None] * len(reps))
        res += [None] * (len(reps) - len(res))

        def save():
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for i, r in enumerate(reps):
            if res[i] is not None:
                continue
            r = {**r, "text": tag_links((r.get("text") or "").strip(), r.get("platform"), r.get("kind"))}
            errs = check_reply(r)   # 글자 수는 UTM 을 붙인 뒤로 센다
            if errs:
                res[i] = {"error": "; ".join(errs)}
            else:
                try:
                    if r.get("action"):
                        res[i] = {"moderated": moderate_one(r["platform"], r["to"], r["action"]),
                                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                        print(f"{p.name} #{i} {r['platform']} 댓글 {r['to']} {res[i]['moderated']}")
                        save()
                        continue
                    res[i] = {"id": post_one(r["platform"], r["to"], r["text"]),
                              "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                except (RuntimeError, KeyError) as e:
                    res[i] = {"error": str(e)[:300]}
            if "error" in res[i]:
                bad += 1
                print(f"::warning::{p.name} #{i} {r.get('platform')} 실패: {res[i]['error']}")
            else:
                print(f"{p.name} #{i} {r['platform']} 답글 {res[i]['id']}")
            save()
        p.rename(DONE / p.name)
    return 1 if bad else 0


def main(argv):
    if "--probe" in argv:
        return probe()
    if "--post" in argv:
        return post_files()
    if "--list" in argv:
        days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 7
        r = list_all(days)
        out = argv[argv.index("--out") + 1] if "--out" in argv else None
        s = json.dumps(r, ensure_ascii=False, indent=1)
        if out:
            Path(out).write_text(s, encoding="utf-8")
        elif "--log" in argv:  # 워크플로 로그로 넘길 때: 한 줄 JSON(세션이 작업 로그에서 OPEN_JSON: 줄을 읽는다)
            print("OPEN_JSON:" + json.dumps(r, ensure_ascii=False, separators=(",", ":")))
        else:
            print(s)
        for name, v in r["platforms"].items():
            print(f"{name}: " + (f"답할 차례 {len(v['open'])}개, 최근 24시간 우리 답글 {v['my_replies_24h']}개" if v["ok"] else f"실패 — {v['error']}"), file=sys.stderr)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
