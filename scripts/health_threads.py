#!/usr/bin/env python3
"""김박사 건강몰 → Threads @drkimworld 하루 한 글(2026-11-25 운영자 "니가 직접 할수 있는 방식 아무거나 해").

health/health.yaml 의 성분 가이드를 날짜 순서로 돌려 가며, 가이드에 이미 있는
'고를 때 확인할 것' 한 줄 + 식약처 인정 기능성 문구(그대로) + 가이드 링크(UTM)로 글을 만든다.
쿠팡 상품 링크는 넣지 않는다(몰 가이드로만). 금지어가 들어가면 만들지 않는다.

python3 scripts/health_threads.py [--day YYYY-MM-DD]  → 본문을 표준 출력으로
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KST = dt.timezone(dt.timedelta(hours=9))
LIMIT = 500


def compose(c: dict, day: dt.date) -> str:
    guides = [g for g in c.get("guides") or [] if g.get("choose") and g.get("functions")]
    if not guides:
        raise SystemExit("가이드 없음")
    n = day.toordinal()
    g = guides[n % len(guides)]
    tip = g["choose"][(n // len(guides)) % len(g["choose"])]
    f = g["functions"][(n // len(guides)) % len(g["functions"])]
    url = (f"{c['url'].rstrip('/')}/guide/{g['slug']}/"
           f"?utm_source=threads&utm_medium=post&utm_campaign=drkim-{g['slug']}")
    parts = [
        f"{g['name']}, 사기 전에 뒷면에서 확인할 것",
        tip,
        f"식약처 인정 기능성: {f['text']}" + (f" (하루 섭취량: {f['dose']})" if f.get("dose") else ""),
        f"성분별 고르는 법·섭취 시 주의사항 → {url}",
    ]
    text = "\n\n".join(parts)
    if len(text) > LIMIT:  # 팁이 길면 팁을 줄인다(기능성 문구·링크는 그대로)
        cut = LIMIT - (len(text) - len(tip)) - 1
        parts[1] = tip[:max(cut, 0)].rstrip() + "…"
        text = "\n\n".join(parts)
    bad = [w for w in c.get("banned") or [] if w in text]
    if bad:
        raise SystemExit(f"금지어 포함: {bad}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    a = ap.parse_args()
    day = dt.date.fromisoformat(a.day) if a.day else dt.datetime.now(KST).date()
    c = yaml.safe_load((ROOT / "health" / "health.yaml").read_text(encoding="utf-8"))
    sys.stdout.write(compose(c, day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
