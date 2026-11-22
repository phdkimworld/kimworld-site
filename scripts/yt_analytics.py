#!/usr/bin/env python3
"""유튜브 분석 숫자(구독·조회·시청 시간)를 비공개 ops-data 에 매일 쌓는다(2026-11-22: vidIQ 크레딧 소진으로 구독 1,000회당을 못 읽게 됨 →
11-20 운영자가 넣은 분석 권한 yt-analytics.readonly 로 직접 읽는다. 12-01 구독 전환 시험 판정·영상별 A/B 비교용).

출력(둘 다 비공개 저장소에만, scripts/ops_publish.sh):
  stats/youtube/analytics.json  {at, daily:[{day, views, subs_gained, subs_lost, minutes}], videos:[{id, views, subs_gained, minutes}](최근 14일 조회 상위 50)}
  stats/youtube/summary.md      최근 7일 vs 전 7일: 조회·순구독·1,000회당 구독·시청 분
공개 주석에는 성공 여부와 줄 수만 남긴다. 키 값은 출력하지 않는다.
분석 수치는 2~3일 늦게 들어오므로 '최근 7일'은 마지막으로 값이 있는 날부터 거꾸로 센다.
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yt_comments as yc  # noqa: E402

API = "https://youtubeanalytics.googleapis.com/v2/reports?"


def q(tok, **p):
    req = urllib.request.Request(API + urllib.parse.urlencode({"ids": "channel==MINE", **p}), headers={"Authorization": "Bearer " + tok})
    return json.load(urllib.request.urlopen(req, timeout=60))


def summary(daily: list) -> str:
    rows = [d for d in daily if d["views"] or d["subs_gained"]]
    if len(rows) < 14:
        return "# 유튜브 분석 요약\n\n- 값이 14일 치보다 적어 비교하지 않음\n"
    cur, prev = rows[-7:], rows[-14:-7]

    def agg(r):
        v = sum(x["views"] for x in r); net = sum(x["subs_gained"] - x["subs_lost"] for x in r)
        return v, net, sum(x["subs_gained"] for x in r), sum(x["minutes"] for x in r), (net / v * 1000 if v else 0)

    c, p = agg(cur), agg(prev)
    return (f"# 유튜브 분석 요약 ({cur[0]['day']}~{cur[-1]['day']}, 괄호는 그 전 7일)\n\n"
            f"- 조회 {c[0]:,} ({p[0]:,})\n- 순구독 {c[1]:+,} ({p[1]:+,}) · 새 구독 {c[2]:,} ({p[2]:,})\n"
            f"- 1,000회당 순구독 {c[4]:.2f} ({p[4]:.2f}) — 구독 전환 시험 기준선 1.1, 판정선 1.65\n"
            f"- 시청 {c[3]:,}분 ({p[3]:,}분)\n")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/yt")
    if not yc.available():
        print("::notice title=유튜브 분석::키 없음, 건너뜀")
        return 0
    tok = yc.token()
    end = dt.date.today()
    try:
        d = q(tok, startDate=str(end - dt.timedelta(days=40)), endDate=str(end), metrics="views,subscribersGained,subscribersLost,estimatedMinutesWatched", dimensions="day", sort="day")
        v = q(tok, startDate=str(end - dt.timedelta(days=14)), endDate=str(end), metrics="views,subscribersGained,estimatedMinutesWatched", dimensions="video", sort="-views", maxResults=50)
    except urllib.error.HTTPError as e:
        print(f"::warning title=유튜브 분석::HTTP {e.code} {yc.err(e)[:120]}")
        return 1
    daily = [{"day": r[0], "views": r[1], "subs_gained": r[2], "subs_lost": r[3], "minutes": r[4]} for r in d.get("rows") or []]
    videos = [{"id": r[0], "views": r[1], "subs_gained": r[2], "minutes": r[3]} for r in v.get("rows") or []]
    out.mkdir(parents=True, exist_ok=True)
    (out / "analytics.json").write_text(json.dumps({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "daily": daily, "videos": videos}, ensure_ascii=False), encoding="utf-8")
    (out / "summary.md").write_text(summary(daily), encoding="utf-8")
    print(f"::notice title=유튜브 분석::일별 {len(daily)}줄 · 영상 {len(videos)}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
