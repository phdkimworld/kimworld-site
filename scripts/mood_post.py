"""매주 '미국주식 투자자 투표 결산'(옛 '개미 심리 순위') Threads 글을 social/queue/ 에 만든다(mood-post.yml 에서 실행).

입력: .cache/mood.json (API /v1/sentiment/top 응답: 지난 30일 종목별 합계만, 개인정보 없음)
출력: social/queue/mood-YYYYMMDD.json (바로 게시 시각). 순위가 빈약하면(불리시·베어리시 합쳐 3개 미만) 만들지 않는다.
2026-10-19 운영자 요청(수익성 일일 점검 '투표 데이터를 콘텐츠로'): 비용 없는 트래픽 회수 경로.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://drkimworld.com"


def names() -> dict:
    try:
        d = yaml.safe_load((ROOT / "data" / "tickers.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    items = d.get("tickers", d) if isinstance(d, dict) else d
    out = {}
    if isinstance(items, dict):
        for k, v in items.items():
            out[str(k).upper()] = (v or {}).get("name", "") if isinstance(v, dict) else ""
    elif isinstance(items, list):
        for v in items:
            if isinstance(v, dict) and v.get("code"):
                out[str(v["code"]).upper()] = v.get("name", "")
    return out


def latest_reports() -> dict:
    """종목별 최신 리포트(slug, 쟁점 한 줄): 결산 글에 '왜 화제인지' 한 줄과 최다 투표 종목 리포트 링크를 붙인다(운영자 검토 11-02)."""
    out = {}
    for f in sorted((ROOT / "content" / "reports").glob("*.md")):
        txt = f.read_text(encoding="utf-8")
        if not txt.startswith("---"):
            continue
        try:
            fm = yaml.safe_load(txt.split("---", 2)[1]) or {}
        except Exception:
            continue
        t = str(fm.get("ticker") or "").upper()
        if not t or fm.get("draft"):
            continue
        d = str(fm.get("date") or "")
        title = str(fm.get("title") or "").split("|")[0]
        hook = title.split(",", 1)[1] if "," in title else title
        hook = hook.split("—")[0].strip().rstrip("?").strip()
        if len(hook) > 24:
            hook = hook[:23].rstrip() + "…"
        if t not in out or d > out[t]["date"]:
            out[t] = {"date": d, "slug": f.stem, "hook": hook}
    return out


MIN_N = 10  # 이보다 적은 표는 비율 순위로 세우지 않는다(3표 100%가 14표 종목보다 위에 오는 착시, 운영자 검토 11-02)


def build(d: dict, nm: dict, today: dt.date, reps: dict | None = None) -> dict | None:
    reps = reps or {}
    pool = {}
    for x in (d.get("top") or []) + (d.get("bull") or []) + (d.get("bear") or []):
        if x.get("t") and x["t"] not in pool:
            pool[x["t"]] = x
    items = sorted(pool.values(), key=lambda x: (-int(x.get("n", 0)), x["t"]))[:5]
    if len(items) < 3:
        return None
    lab = lambda x: f"${x['t']}" + (f" {nm[x['t']]}" if nm.get(x["t"]) else "")
    wk = (today.day - 1) // 7 + 1
    lines = [f"📊 {today.month}월 {wk}주 차 미국주식 투자자 투표 결산 ({today.month}/{today.day} 기준, 최근 30일 누적)", "", "🔥 투표가 많이 모인 순"]
    for i, x in enumerate(items, 1):
        b = int(x.get("bull", 0)); n = int(x.get("n", 0))
        side = f"상승 의견 {b}%" if b >= 50 else f"하락 의견 {100 - b}%"
        small = "" if n >= MIN_N else ", 소수 표본"
        lines.append(f"{i}. {lab(x)} ({n}표{small}) — {side}")
        hook = (reps.get(x["t"]) or {}).get("hook")
        if hook:
            lines.append(f"   ↳ {hook}")
    lines += ["", "위 종목 중 다음 주 가장 크게 움직일 것 같은 종목은? 아래 투표나 댓글로 티커를 남겨 주세요 👇",
              f"※ 이용자 투표 집계이며 투자 판단의 근거가 아닙니다. {MIN_N}표 미만은 소수 표본입니다."]
    text = "\n".join(lines)
    while len(text) > 480 and any(l.startswith("   ↳") for l in lines):  # Threads 500자 한도: 쟁점 줄을 아래부터 뺀다
        k = max(i for i, l in enumerate(lines) if l.startswith("   ↳")); del lines[k]; text = "\n".join(lines)
    if len(text) > 480:
        return None
    def opt(x):
        o = lab(x)
        return o if len(o.encode()) <= 25 else f"${x['t']}"
    poll = [opt(x) for x in items[:4]]
    url = f"{SITE}/search/?utm_source=threads&utm_medium=social&utm_campaign=mood#tab=mood"
    first = items[0]; rep = reps.get(first["t"])
    reply = "전체 종목 순위 보기·직접 투표하기 👇"
    if rep:
        reply = (f"이번 주 투표가 가장 많이 모인 {lab(first)}의 분석 리포트:\n{SITE}/r/{rep['slug']}/?utm_source=threads&utm_medium=social&utm_campaign=mood\n\n"
                 "전체 종목 순위 보기·직접 투표하기 👇")
    return {"text": text, "publish_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "channels": ["threads"],
            "poll": poll, "replies": [{"text": reply, "link_attachment": url}]}


def main() -> None:
    try:
        d = json.loads((ROOT / ".cache" / "mood.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"::warning title=mood::순위 자료를 읽지 못함 ({type(e).__name__})"); return
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date()
    post = build(d, names(), today, latest_reports())
    if not post:
        print("::notice title=mood::표가 적어 이번 주는 건너뜀"); return
    out = ROOT / "social" / "queue" / f"mood-{today:%Y%m%d}.json"
    if out.exists():
        print("::notice title=mood::이번 주 글이 이미 있음"); return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(post, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"::notice title=mood::{out.name} 생성")


if __name__ == "__main__":
    sys.exit(main())
