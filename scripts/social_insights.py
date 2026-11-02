#!/usr/bin/env python3
"""SNS 게시물 성과(조회·도달·저장·공유) 수집 — 인스타그램·Threads·페이스북 페이지.

운영자 지시(2026-10-16 "인스타그램 뷰가 전혀 안 나오는데 신경 좀 써줘"): 게시물마다 숫자를 모아
무엇이 안 보이는지(도달 0 = 배포 문제 / 도달은 있는데 조회 낮음 = 첫 화면 문제)를 가른다.

  python scripts/social_insights.py --log [--days 14]
    작업 로그에 "INSIGHTS_JSON:" 한 줄을 낸다(세션이 읽는다).

비밀값(환경변수): IG_ACCESS_TOKEN, THREADS_ACCESS_TOKEN, FB_PAGE_ID, FB_PAGE_TOKEN. 값은 출력하지 않는다.
권한이 없어 지표를 못 읽으면 그 오류 문구를 그대로 담는다(권한 확인용).
"""
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from social_publish import FB_API, IG_API, TH_API, call  # noqa: E402

IG_REEL = "views,reach,likes,comments,shares,saved,total_interactions,ig_reels_avg_watch_time,ig_reels_video_view_total_time"
IG_POST = "views,reach,likes,comments,shares,saved,total_interactions"
TH_POST = "views,likes,replies,reposts,quotes,shares"


def metrics(f, mid, names):
    try:
        r = f(f"{mid}/insights", {"metric": names})
    except RuntimeError as e:  # 지표 하나라도 지원하지 않으면 전체가 실패하므로 기본 지표로 한 번 더
        try:
            r = f(f"{mid}/insights", {"metric": "views,reach"})
        except RuntimeError:
            return {"error": str(e)[:200]}
    out = {}
    for m in r.get("data", []):
        v = m.get("values", [{}])
        out[m["name"]] = (m.get("total_value") or {}).get("value", v[0].get("value") if v else None)
    return out


def instagram(since):
    tok = os.environ.get("IG_ACCESS_TOKEN", "")
    if not tok:
        raise RuntimeError("IG_ACCESS_TOKEN 비밀값이 없음")
    f = lambda p, q: call(IG_API, "GET", p, q, tok)  # noqa: E731
    me = f("me", {"fields": "id,username,account_type,followers_count,follows_count,media_count"})
    acct = {}
    try:
        r = f(f"{me['id']}/insights", {"metric": "reach,views,profile_views,website_clicks,accounts_engaged",
                                      "period": "day", "metric_type": "total_value"})
        acct = {m["name"]: (m.get("total_value") or {}).get("value") for m in r.get("data", [])}
    except RuntimeError as e:
        acct = {"error": str(e)[:200]}
    items = []
    r = f("me/media", {"fields": "id,media_type,media_product_type,timestamp,permalink,caption,like_count,comments_count",
                       "limit": 50})
    for m in r.get("data", []):
        if m.get("timestamp", "") < since:
            continue
        reel = m.get("media_product_type") == "REELS"
        items.append({"id": m["id"], "type": "reel" if reel else m.get("media_type", "").lower(),
                      "time": m.get("timestamp"), "permalink": m.get("permalink"),
                      "caption": (m.get("caption") or "")[:60], "likes": m.get("like_count"),
                      "comments": m.get("comments_count"), **metrics(f, m["id"], IG_REEL if reel else IG_POST)})
    return {"ok": True, "me": me.get("username"), "account_type": me.get("account_type"),
            "followers": me.get("followers_count"), "media_count": me.get("media_count"), "account_day": acct, "items": items}


def threads(since):
    tok = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if not tok:
        raise RuntimeError("THREADS_ACCESS_TOKEN 비밀값이 없음")
    f = lambda p, q: call(TH_API, "GET", p, q, tok)  # noqa: E731
    me = f("me", {"fields": "id,username"})
    items = []
    r = f("me/threads", {"fields": "id,timestamp,permalink,text,media_type", "limit": 50})
    for m in r.get("data", []):
        if m.get("timestamp", "") < since:
            continue
        items.append({"id": m["id"], "time": m.get("timestamp"), "permalink": m.get("permalink"),
                      "text": (m.get("text") or "")[:60], **metrics(f, m["id"], TH_POST)})
    return {"ok": True, "me": me.get("username"), "items": items}


def facebook(since):
    """운영자 지시(2026-11-02 "페이스북 페이지도 트래픽이 전혀 없는데 진단후 조치"): 페이지 팔로워·공개 여부와
    릴스·글마다 재생·도달을 모아 '도달 0(배포 문제)'과 '도달은 있는데 클릭 0(링크 문제)'을 가른다."""
    tok, page = os.environ.get("FB_PAGE_TOKEN", ""), os.environ.get("FB_PAGE_ID", "")
    if not tok or not page:
        raise RuntimeError("FB_PAGE_TOKEN·FB_PAGE_ID 비밀값이 없음")
    f = lambda p, q: call(FB_API, "GET", p, q, tok)  # noqa: E731
    info = {}
    for fields in ("name,fan_count,followers_count,is_published,link,category", "name,fan_count,link"):
        try:
            info = f(page, {"fields": fields}); break
        except RuntimeError as e:
            info = {"error": str(e)[:200]}
    day = {}
    for m in ("page_impressions_unique", "page_views_total", "page_post_engagements", "page_video_views", "page_follows"):
        try:
            r = f(f"{page}/insights", {"metric": m, "period": "day", "date_preset": "last_7d"})
            for d in r.get("data", []):
                day[d["name"]] = sum((v.get("value") or 0) for v in d.get("values", []) if isinstance(v.get("value"), (int, float)))
        except RuntimeError as e:
            day[m] = "error: " + str(e)[:120]
    items = []
    try:
        r = f(f"{page}/video_reels", {"fields": "id,created_time,permalink_url,description", "limit": 30})
        for v in r.get("data", []):
            if v.get("created_time", "") < since:
                continue
            it = {"id": v["id"], "type": "reel", "time": v.get("created_time"), "permalink": v.get("permalink_url"),
                  "caption": (v.get("description") or "")[:60]}
            try:
                q = f(f"{v['id']}/video_insights", {})
                for m in q.get("data", []):
                    val = (m.get("values") or [{}])[0].get("value")
                    if isinstance(val, (int, float)):
                        it[m["name"]] = val
            except RuntimeError as e:
                it["error"] = str(e)[:150]
            items.append(it)
    except RuntimeError as e:
        items.append({"error": "video_reels: " + str(e)[:200]})
    try:
        r = f(f"{page}/published_posts", {"fields": "id,created_time,permalink_url,message,is_published,shares", "limit": 30})
        for p_ in r.get("data", []):
            if p_.get("created_time", "") < since:
                continue
            it = {"id": p_["id"], "type": "post", "time": p_.get("created_time"), "permalink": p_.get("permalink_url"),
                  "caption": (p_.get("message") or "")[:60], "is_published": p_.get("is_published")}
            try:
                q = f(f"{p_['id']}/insights", {"metric": "post_impressions_unique,post_clicks"})
                for m in q.get("data", []):
                    it[m["name"]] = (m.get("values") or [{}])[0].get("value")
            except RuntimeError as e:
                it["error"] = str(e)[:150]
            items.append(it)
    except RuntimeError as e:
        items.append({"error": "published_posts: " + str(e)[:200]})
    return {"ok": True, "me": info.get("name"), "followers": info.get("followers_count"), "fans": info.get("fan_count"),
            "is_published": info.get("is_published"), "link": info.get("link"), "page_7d": day, "items": items,
            "info_error": info.get("error")}


def collect(days):
    now = datetime.datetime.now(datetime.timezone.utc)
    since = (now - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    res = {}
    for name, fn in (("instagram", instagram), ("threads", threads), ("facebook", facebook)):
        try:
            res[name] = fn(since)
        except RuntimeError as e:
            res[name] = {"ok": False, "error": str(e)[:400]}
    return {"generated": now.isoformat(timespec="seconds"), "days": days, "platforms": res}


def main(argv):
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 14
    r = collect(days)
    if "--log" in argv:
        print("INSIGHTS_JSON:" + json.dumps(r, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    for name, v in r["platforms"].items():
        print(f"{name}: " + (f"게시물 {len(v['items'])}개" if v["ok"] else f"실패 — {v['error']}"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
