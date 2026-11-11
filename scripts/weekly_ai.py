#!/usr/bin/env python3
"""주간 성과 요약과 다음 회차 개선안(운영자 지시 2026-11-11). .github/workflows/weekly-ai.yml 이 매주 월요일 1회 실행.

입력(사이트 저장소·사이트 비밀값으로 닿는 것만, 미디어 저장소 통계는 쓰지 않는다):
  - 지난 7일 새 리포트 목록(content/reports 머리말), SNS 게시 기록 개수(social/posted)
  - 운영 통계 요약(.cache/an.json 이 있으면 scripts/analytics_report.summarize 의 트래픽 항목만)
  - SNS 게시물 성과(scripts/social_insights.collect, 토큰이 있을 때), 유튜브 최근 7일 영상 공개 통계(YT_* 가 있을 때)
공개 저장소에 커밋되므로 수익·광고 실적(애드핏·쿠팡·광고 노출·클릭)·검색어 원문·사용자 정보는 넣지 않는다(AGENTS.md 8장).
출력: social/llm/weekly/<YYYY-MM-DD>.md (요약 + 개선안 3~5개).
사용: python3 scripts/weekly_ai.py [--dry]   (--dry: 모델에 보낼 입력만 출력)
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402

ROOT = llm.ROOT
OUT_DIR = ROOT / "social" / "llm" / "weekly"
TRAFFIC_KEYS = ("totals", "series", "channels", "landings", "reports", "types", "sections", "sentiment", "community", "dow")
PRIVATE_RE = re.compile(r"수익|수수료|적립금|애드핏|adfit|쿠팡|coupang|광고\s*(수입|매출|클릭|노출)|eCPM|RPM|CPC|₩|\d\s*원(?![가-힣])|\$\s*\d", re.I)


def recent_reports(days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    out = []
    for p in sorted((ROOT / "content" / "reports").glob("*.md")):
        if p.name.startswith("_"):
            continue
        head = p.read_text(encoding="utf-8")[:3000]
        g = lambda k: (re.search(rf"^{k}:\s*(.+?)\s*$", head, re.M) or [None, ""])[1].strip().strip('"')  # noqa: E731
        if g("draft").lower() == "true" or g("date") < since:
            continue
        out.append({"slug": p.stem, "ticker": g("ticker"), "theme": g("theme"), "date": g("date"),
                    "title": g("title")[:90], "youtube": bool(g("youtube_id"))})
    return out


def posted_counts(days=7):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    c = {}
    for p in (ROOT / "social" / "posted").glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            at = datetime.fromisoformat(str(d.get("posted_at") or d.get("publish_at")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if at < since:
            continue
        kind = (d.get("media") or {}).get("type") or "text"
        for ch in d.get("results", {}):
            c[f"{ch}:{kind}"] = c.get(f"{ch}:{kind}", 0) + 1
    return c


def traffic():
    f = ROOT / ".cache" / "an.json"
    if not f.exists():
        return None
    try:
        import analytics_report as ar
        s = ar.summarize(json.loads(f.read_text(encoding="utf-8")))
    except Exception as e:
        return {"error": type(e).__name__}
    t = {k: s.get(k) for k in TRAFFIC_KEYS if s.get(k) is not None}
    for k in ("channels", "landings", "reports"):
        if isinstance(t.get(k), list):
            t[k] = [{kk: vv for kk, vv in x.items() if kk != "ev"} for x in t[k][:15]]
    if isinstance(t.get("sections"), dict):
        t["sections"] = {"all": t["sections"].get("all")}
    return t


def sns_insights():
    if not any(os.environ.get(k) for k in ("IG_ACCESS_TOKEN", "THREADS_ACCESS_TOKEN", "FB_PAGE_TOKEN")):
        return None
    try:
        import social_insights as si
        r = si.collect(7)
    except Exception as e:
        return {"error": type(e).__name__}
    out = {}
    for name, v in (r.get("platforms") or {}).items():
        if isinstance(v, dict) and v.get("ok"):
            out[name] = {"followers": v.get("followers"),
                         "posts": [{k: x.get(k) for k in x if k not in ("caption", "text", "permalink", "id")} for x in v.get("items", [])][:30]}
    return out


def youtube():
    try:
        import yt_comments as yt
        if not yt.available():
            return None
        return yt.channel_videos(yt.token(), 7)
    except Exception as e:
        return {"error": type(e).__name__}


SYSTEM = """당신은 미국 주식 리포트 사이트·유튜브 채널 '김박사 월드'의 주간 운영 분석가입니다.
주어진 지난 7일 자료만 보고 한국어로 짧은 주간 메모를 씁니다. 자료에 없는 숫자는 만들지 않습니다.

형식(마크다운, 전체 40줄 이내)
## 지난 7일 요약
- 4~6줄. 숫자에는 비교 기준(지난주 대비, 채널 평균 대비 등)을 같은 줄에 씁니다.
## 다음 회차 개선안
1~5번(3개 이상). 각 항목: 무엇을 바꿀지 한 문장 + 근거 숫자 한 문장 + 확인할 지표 한 문장. 작고 되돌리기 쉬운 것부터.
## 자료 한계
- 1~3줄(빠진 자료, 표본이 작은 지표).

규칙: 이 파일은 공개 저장소에 올라갑니다. 수익·광고 실적·수수료 금액은 쓰지 않습니다. 사용자 닉네임·검색어 원문을 쓰지 않습니다.
종목 매수·매도 판단은 쓰지 않습니다. 화살표·가운뎃점 나열 대신 짧은 문장으로 씁니다."""


def scrub(md):
    """비공개 숫자가 섞인 줄은 지운다."""
    keep, cut = [], 0
    for line in md.splitlines():
        if PRIVATE_RE.search(line):
            cut += 1
            continue
        keep.append(line)
    return "\n".join(keep).strip() + "\n", cut


def main(argv):
    dry = "--dry" in argv
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    data = {"period_end": today, "new_reports": recent_reports(), "sns_posts_by_channel": posted_counts(),
            "site_traffic": traffic(), "sns_insights": sns_insights(), "youtube_last7": youtube()}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if PRIVATE_RE.search(payload):   # 입력에도 비공개 항목 이름이 섞였는지(있으면 그 키를 빼고 보낸다)
        payload = PRIVATE_RE.sub("", payload)
    if dry:
        print(payload[:4000])
        return 0
    if not llm.has_key() and "LLM_MOCK_RESPONSE" not in os.environ:
        print("::notice::STATUS=no_key — 주간 분석을 건너뜀")
        return 0
    r = llm.ask("weekly", SYSTEM, f"지난 7일 자료(JSON):\n{payload}", tier="judge", max_tokens=6000, effort="medium")
    if r["status"] != "ok":
        print(f"::notice::STATUS={r['status']} — 주간 분석을 건너뜀(실패 아님) {r['error'][:120]}")
        return 0
    md, cut = scrub(r["text"])
    head = f"# 주간 성과 메모 {today}\n\n- 자동 작성(경고·제안용). 자료: 사이트 저장소 기록과 공개 통계만. 수익·광고 실적은 넣지 않음." + (f" 비공개 표현이 섞인 {cut}줄은 지움." if cut else "") + "\n\n"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{today}.md"
    out.write_text(head + md, encoding="utf-8")
    print(f"주간 메모: {out.relative_to(ROOT)}")
    cf = os.environ.get("CHANGED_FILE")
    if cf:
        Path(cf).write_text(str(out.relative_to(ROOT)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
