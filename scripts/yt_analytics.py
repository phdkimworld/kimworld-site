#!/usr/bin/env python3
"""유튜브 분석(YouTube Analytics API v2) 자료를 받아 JSON 하나로 만든다(운영자 지시 2026-11-21 "지금 새 키로 넘어가").

왜: 제작 세션 컨테이너의 유튜브 키는 분석 권한이 없다. 새 키(yt-analytics.readonly 포함)는 이 저장소 GitHub 비밀값
YT_CLIENT_ID·YT_CLIENT_SECRET·YT_REFRESH_TOKEN 에만 있다(운영자가 11-20 넣음). 그래서 이 저장소 워크플로
`yt-analytics.yml` 이 이 스크립트를 돌리고, 결과는 scripts/ops_publish.sh 로 비공개 저장소
phdkimworld/kimworld ops-data 브랜치 stats/yt_analytics.json 에만 올린다. 공개 저장소·공개 주석에는 숫자를 남기지 않는다
(운영자 2026-10-28 통계 비공개). 미디어 저장소 tools/yt_analytics_read.py 가 이 JSON을 읽는다.

받는 것(ids=channel==MINE):
  - totals.d28 / totals.d7: views, estimatedMinutesWatched, averageViewDuration, averageViewPercentage, subscribersGained, subscribersLost
  - videos: 영상별(dimensions=video, 최근 28일, maxResults 200, sort -views) views, estimatedMinutesWatched,
            averageViewDuration, averageViewPercentage, subscribersGained (+ 제목은 Data API로 되면)
            + 상위 200편에 없는 최근 업로드 RECENT(기본 50)편을 filters=video==ID로 더 받아 top200=false 로 붙인다
  - traffic.channel: 채널 전체 유입 경로(insightTrafficSourceType, 28일)
  - traffic.videos[영상ID]: 조회 상위 TOP_TRAFFIC 편의 유입 경로(28일)
  - daily: 일별(dimensions=day, 28일) views, subscribersGained
노출수(impressions)·노출 클릭률(CTR)은 YouTube Studio에만 있고 공개 Analytics API에는 없다(그래서 받지 않는다).
분석 자료는 2~3일 늦게 차므로 끝 날짜는 어제(UTC)로 둔다.

환경 변수: YT_CLIENT_ID·YT_CLIENT_SECRET·YT_REFRESH_TOKEN(값 출력 금지), OUT(기본 .cache/yt_analytics.json), TOP_TRAFFIC(기본 15), RECENT(기본 50).
실패하면 HTTP 코드와 짧은 오류만 ::notice 로 남긴다. 영상별 표를 못 받으면 0이 아닌 값으로 끝나 게시하지 않는다.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KEYS = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
REPORTS = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA_API = "https://www.googleapis.com/youtube/v3/videos"
TOTAL_METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
VIDEO_METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained"


def notice(title, msg):
    print(f"::notice title={title}::{str(msg).replace(chr(10), ' ')[:200]}", flush=True)


def short_err(e: urllib.error.HTTPError) -> str:
    try:
        j = json.load(e)
        er = j.get("error")
        if isinstance(er, dict):
            reason = ",".join(x.get("reason", "") for x in er.get("errors", [])) or er.get("status", "") or er.get("message", "")
        else:
            reason = str(er or "")
    except Exception:
        reason = ""
    return f"HTTP {e.code} {reason[:80]}".strip()


def token() -> str:
    for k in KEYS:
        print(f"::add-mask::{os.environ[k]}", flush=True)
    d = urllib.parse.urlencode({"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
                                "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    tok = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", d, timeout=30))["access_token"]
    print(f"::add-mask::{tok}", flush=True)
    return tok


def report(tok, start, end, metrics, **q) -> dict:
    """reports.query 한 번. 반환 {columns:[...], rows:[...]}."""
    params = {"ids": "channel==MINE", "startDate": str(start), "endDate": str(end), "metrics": metrics, **q}
    req = urllib.request.Request(REPORTS + "?" + urllib.parse.urlencode(params), headers={"Authorization": "Bearer " + tok})
    j = json.load(urllib.request.urlopen(req, timeout=60))
    return {"columns": [h["name"] for h in j.get("columnHeaders", [])], "rows": j.get("rows") or []}


def as_dicts(r: dict) -> list[dict]:
    return [dict(zip(r["columns"], row)) for row in r["rows"]]


def titles(tok, ids: list[str]) -> dict:
    out = {}
    for i in range(0, len(ids), 50):
        q = urllib.parse.urlencode({"part": "snippet", "id": ",".join(ids[i:i + 50]), "maxResults": 50})
        req = urllib.request.Request(DATA_API + "?" + q, headers={"Authorization": "Bearer " + tok})
        for it in json.load(urllib.request.urlopen(req, timeout=60)).get("items", []):
            sn = it.get("snippet", {})
            out[it["id"]] = {"title": sn.get("title", ""), "published": sn.get("publishedAt", "")}
    return out


def recent_uploads(tok, n: int) -> list[str]:
    """채널 업로드 재생목록의 최근 n편 영상 ID(Data API)."""
    def get(url, **q):
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"Authorization": "Bearer " + tok})
        return json.load(urllib.request.urlopen(req, timeout=60))
    ch = get("https://www.googleapis.com/youtube/v3/channels", part="contentDetails", mine="true")
    pl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = get("https://www.googleapis.com/youtube/v3/playlistItems", part="contentDetails", playlistId=pl, maxResults=min(n, 50))
    return [it["contentDetails"]["videoId"] for it in items.get("items", [])]


def main() -> int:
    if not all(os.environ.get(k) for k in KEYS):
        notice("YT 분석", "YT_* 비밀값 없음")
        return 1
    try:
        tok = token()
    except urllib.error.HTTPError as e:
        notice("YT 분석 토큰", short_err(e))
        return 1
    except Exception as e:  # 네트워크 등
        notice("YT 분석 토큰", type(e).__name__)
        return 1

    end = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    s28, s7 = end - dt.timedelta(days=27), end - dt.timedelta(days=6)
    top_n = int(os.environ.get("TOP_TRAFFIC") or 15)
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "range": {"d28": [str(s28), str(end)], "d7": [str(s7), str(end)]},
           "note": "impressions·CTR은 공개 Analytics API에 없음(Studio 전용)",
           "totals": {}, "videos": [], "traffic": {"channel": [], "videos": {}}, "daily": [], "errors": {}}

    def run(name, fn):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            msg = short_err(e)
        except Exception as e:
            msg = type(e).__name__
        out["errors"][name] = msg
        notice(f"YT 분석 {name}", msg)
        return None

    for key, start in (("d28", s28), ("d7", s7)):
        r = run(f"totals_{key}", lambda start=start: report(tok, start, end, TOTAL_METRICS))
        if r:
            rows = as_dicts(r)
            out["totals"][key] = rows[0] if rows else {}

    r = run("videos", lambda: report(tok, s28, end, VIDEO_METRICS, dimensions="video", maxResults=200, sort="-views"))
    if r is None:
        return 1
    vids = as_dicts(r)
    # 상위 200편은 조회순이라 조회가 적은 최근 롱폼이 빠진다 → 최근 업로드 RECENT편을 영상 ID로 따로 묻는다(top200=False 표시)
    have = {v["video"] for v in vids}
    recent = run("recent_uploads", lambda: recent_uploads(tok, int(os.environ.get("RECENT") or 50))) or []
    miss = [x for x in recent if x not in have]
    if miss:
        r2 = run("videos_recent", lambda: report(tok, s28, end, VIDEO_METRICS, dimensions="video", filters="video==" + ",".join(miss),
                                                 maxResults=200, sort="-views"))
        for v in as_dicts(r2) if r2 else []:
            v["top200"] = False
            vids.append(v)
    meta = run("titles", lambda: titles(tok, [v["video"] for v in vids])) or {}
    for v in vids:
        v.update(meta.get(v["video"], {}))
    out["videos"] = vids

    r = run("traffic_channel", lambda: report(tok, s28, end, "views,estimatedMinutesWatched",
                                              dimensions="insightTrafficSourceType", sort="-views"))
    if r:
        out["traffic"]["channel"] = as_dicts(r)
    for v in vids[:top_n]:
        vid = v["video"]
        r = run(f"traffic_{vid}", lambda vid=vid: report(tok, s28, end, "views,estimatedMinutesWatched",
                                                          dimensions="insightTrafficSourceType", filters=f"video=={vid}", sort="-views"))
        if r:
            out["traffic"]["videos"][vid] = as_dicts(r)

    r = run("daily", lambda: report(tok, s28, end, "views,subscribersGained", dimensions="day", sort="day"))
    if r:
        out["daily"] = as_dicts(r)

    path = Path(os.environ.get("OUT") or ".cache/yt_analytics.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # 공개 로그에는 개수만(숫자 값은 남기지 않는다)
    notice("YT 분석", f"영상 {len(vids)}편(최근 업로드 추가 {len(vids) - len(have)}) · 유입 경로 {len(out['traffic']['videos'])}편 · 일별 {len(out['daily'])}일 · 오류 {len(out['errors'])}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
