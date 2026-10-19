"""매주 '개미 심리 순위' Threads 글을 social/queue/ 에 만든다(mood-post.yml 에서 실행).

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


def build(d: dict, nm: dict, today: dt.date) -> dict | None:
    bull, bear, top = d.get("bull") or [], d.get("bear") or [], d.get("top") or []
    if len(bull) + len(bear) < 3:
        return None
    lab = lambda x: f"${x['t']}" + (f" {nm[x['t']]}" if nm.get(x["t"]) else "")
    lines = [f"이번 주 개미 심리 순위 ({today.month}/{today.day}, 지난 30일 이용자 투표)", ""]
    if bull:
        lines.append("▲ 오를 것 같다 상위")
        lines += [f"{i}. {lab(x)} {x['bull']}% ({x['n']}표)" for i, x in enumerate(bull[:3], 1)]
        lines.append("")
    if bear:
        lines.append("▼ 내릴 것 같다 상위")
        lines += [f"{i}. {lab(x)} {100 - x['bull']}% ({x['n']}표)" for i, x in enumerate(bear[:3], 1)]
        lines.append("")
    if top:
        lines.append(f"가장 많이 투표한 종목: {lab(top[0])} ({top[0]['n']}표)")
    lines += ["", "여러분 생각은 어느 쪽인가요?", "※ 이용자 투표 결과이며 투자 판단의 근거가 아닙니다."]
    text = "\n".join(lines)
    if len(text) > 480:  # Threads 500자 한도(여유). 종목 3개씩이면 보통 350자 안팎
        return None
    url = f"{SITE}/search/?utm_source=threads&utm_medium=social&utm_campaign=mood#tab=mood"
    return {"text": text, "publish_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "channels": ["threads"],
            "replies": [{"text": "순위 전체 보기·직접 투표하기 👇", "link_attachment": url}]}


def main() -> None:
    try:
        d = json.loads((ROOT / ".cache" / "mood.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"::warning title=mood::순위 자료를 읽지 못함 ({type(e).__name__})"); return
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date()
    post = build(d, names(), today)
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
