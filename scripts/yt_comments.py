#!/usr/bin/env python3
"""유튜브 댓글 읽기·답글(사이트 워크플로용). 미디어 저장소 tools/yt_reply.py 의 --list·--reply 와 같은 판정을 옮겨 왔다.

인증: 환경 변수 YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN(업로드와 같은 youtube.force-ssl 토큰).
값은 출력하지 않는다. 셋 중 하나라도 없으면 available() 이 False.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

API = "https://www.googleapis.com/youtube/v3/"
KEYS = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")


def available():
    return all(os.environ.get(k) for k in KEYS)


def token():
    d = urllib.parse.urlencode({"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
                                "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    return json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", d, timeout=30))["access_token"]


def call(tok, path, body=None, **q):
    req = urllib.request.Request(API + path + "?" + urllib.parse.urlencode(q), headers={"Authorization": "Bearer " + tok},
                                 data=json.dumps(body).encode() if body is not None else None)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    return json.load(urllib.request.urlopen(req, timeout=60))


def err(e):
    try:
        j = json.load(e)
        reason = ",".join(x.get("reason", "") for x in j["error"].get("errors", [])) or j["error"].get("message", "")
    except Exception:
        reason = ""
    return f"HTTP {e.code} {reason}".strip()


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def list_open(tok, days=7):
    """답할 차례인 스레드(kind top/followup)와 오늘(ET 0시~) 우리 채널 답글 수. tools/yt_reply.py list_open 과 같은 판정."""
    me = call(tok, "channels", part="id", mine="true")["items"][0]["id"]
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(days=days)
    q = dict(part="snippet,replies", order="time", maxResults=100, textFormat="plainText", allThreadsRelatedToChannelId=me)

    def item(c):
        sn = c["snippet"]
        return {"commentId": c["id"], "author": sn.get("authorDisplayName"), "isMe": sn.get("authorChannelId", {}).get("value") == me,
                "text": sn.get("textOriginal") or sn.get("textDisplay"), "likeCount": sn.get("likeCount", 0), "publishedAt": sn["publishedAt"]}
    et_start = datetime.datetime.now(ZoneInfo("America/New_York")).replace(hour=0, minute=0, second=0, microsecond=0)
    out, mine_today, pt, pages = [], 0, None, 0
    while True:
        r = call(tok, "commentThreads", **q, **({"pageToken": pt} if pt else {}))
        pages += 1
        fresh = False
        for t in r.get("items", []):
            topc = t["snippet"]["topLevelComment"]
            top = topc["snippet"]
            reps = t.get("replies", {}).get("comments", [])

            def all_replies(tid=t["id"]):
                got, rpt = [], None
                while True:
                    rr = call(tok, "comments", part="snippet", parentId=tid, maxResults=100, textFormat="plainText", **({"pageToken": rpt} if rpt else {}))
                    got += rr.get("items", [])
                    rpt = rr.get("nextPageToken")
                    if not rpt:
                        return got
            full = False
            if t["snippet"].get("totalReplyCount", 0) > len(reps):
                reps, full = all_replies(), True
            conv = sorted([item(topc)] + [item(c) for c in reps], key=lambda x: x["publishedAt"])
            if max(ts(c["publishedAt"]) for c in conv) < since:
                continue
            fresh = True
            mine = [c for c in conv if c["isMe"]]
            mine_today += sum(1 for c in mine if c["commentId"] != topc["id"] and ts(c["publishedAt"]) >= et_start)
            base = {"threadId": t["id"], "videoId": top.get("videoId")}
            if not mine:
                if ts(top["publishedAt"]) < since:
                    continue
                out.append({**base, "kind": "top", **{k: v for k, v in item(topc).items() if k != "isMe"}})
                continue
            last = max(ts(c["publishedAt"]) for c in mine)
            fu = [c for c in conv if not c["isMe"] and ts(c["publishedAt"]) > last and ts(c["publishedAt"]) >= since]
            if fu and reps and not full:   # commentThreads 의 답글 목록은 늦게 갱신될 때가 있어 다시 확인
                reps = all_replies()
                conv = sorted([item(topc)] + [item(c) for c in reps], key=lambda x: x["publishedAt"])
                mine = [c for c in conv if c["isMe"]]
                last = max(ts(c["publishedAt"]) for c in mine)
                fu = [c for c in conv if not c["isMe"] and ts(c["publishedAt"]) > last and ts(c["publishedAt"]) >= since]
            if not fu:
                continue
            out.append({**base, "kind": "followup", "author": fu[-1]["author"], "text": fu[-1]["text"], "publishedAt": fu[-1]["publishedAt"],
                        "commentId": fu[-1]["commentId"],
                        "context": [{k: c[k] for k in ("author", "isMe", "text", "publishedAt")} for c in conv][-12:]})
        pt = r.get("nextPageToken")
        if not pt or not fresh or pages >= 10:
            break
    ids = sorted({c["videoId"] for c in out if c.get("videoId")})
    titles = {}
    for k in range(0, len(ids), 50):
        for v in call(tok, "videos", part="snippet", id=",".join(ids[k:k + 50])).get("items", []):
            titles[v["id"]] = v["snippet"]["title"]
    for c in out:
        c["videoTitle"] = titles.get(c.get("videoId"), "")
    return {"channelId": me, "my_replies_today_et": mine_today, "open": out}


LINK_RE = re.compile(r"https?://(?:www\.)?drkimworld\.com/r/([a-z0-9-]+)/(\?[^\s]*)?")
UTM_CONTENT = {"top": "reply", "followup": "followup", "request": "request"}


def tag_links(text, kind="top"):
    content = UTM_CONTENT.get(kind, "reply")

    def sub(m):
        slug, q = m.group(1), (m.group(2) or "")[1:]
        keep = [kv for kv in q.split("&") if kv and not kv.startswith("utm_")]
        return f"https://drkimworld.com/r/{slug}/?" + "&".join(keep + ["utm_source=youtube", "utm_medium=comment", f"utm_campaign={slug}", f"utm_content={content}"])
    return LINK_RE.sub(sub, text)


def reply(tok, thread_id, text, kind="top"):
    """답글 1개. 성공하면 답글 ID, 실패하면 RuntimeError(다시 시도하지 않는다)."""
    try:
        r = call(tok, "comments", {"snippet": {"parentId": thread_id, "textOriginal": tag_links(text, kind)}}, part="snippet")
    except urllib.error.HTTPError as e:
        raise RuntimeError("답글 실패: " + err(e)) from None
    return r["id"]


def channel_videos(tok, days=7):
    """최근 days 일 업로드의 공개 통계(조회·좋아요·댓글). 주간 분석용."""
    ch = call(tok, "channels", part="contentDetails", mine="true")["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    vids, pt = [], None
    for _ in range(4):
        r = call(tok, "playlistItems", part="contentDetails", playlistId=up, maxResults=50, **({"pageToken": pt} if pt else {}))
        for it in r.get("items", []):
            at = it["contentDetails"].get("videoPublishedAt")
            if at and ts(at) >= since:
                vids.append(it["contentDetails"]["videoId"])
        pt = r.get("nextPageToken")
        if not pt:
            break
    out = []
    for k in range(0, len(vids), 50):
        for v in call(tok, "videos", part="snippet,statistics,contentDetails", id=",".join(vids[k:k + 50])).get("items", []):
            s = v.get("statistics", {})
            out.append({"id": v["id"], "title": v["snippet"]["title"], "publishedAt": v["snippet"]["publishedAt"],
                        "duration": v.get("contentDetails", {}).get("duration"), "views": int(s.get("viewCount", 0)),
                        "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0))})
    return out
