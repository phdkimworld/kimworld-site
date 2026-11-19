#!/usr/bin/env python3
"""예측 성적표 데이터(운영자 지시 2026-11-18 "해줘" — 사이트 누적 성적표 페이지 /scorecard/).

미디어 저장소 예측 장부(review/predictions/ledger.jsonl, tools/pred_ledger.py가 판정)를 읽어 data/scorecard.json 을 쓴다.
- **판정이 끝난 예측만** 싣는다(대기·사람 판정 필요·판정 불가는 숫자 개수만). 앞날 예측 문장은 페이지에 나오지 않는다.
- 적중(콜)·브라이어·구간 보정 계산은 pred_ledger.py stats()/table()과 같게(오답노트 리포트 숫자와 맞도록).
사용: python3 scripts/scorecard.py <ledger.jsonl 경로 또는 https 주소> [출력=data/scorecard.json]
deploy.yml이 매 빌드 전에 공개 미디어 저장소의 장부로 다시 만든다(실패하면 저장소에 있는 파일 그대로).
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DONE_NOT = ("대기", "사람 판정 필요", "판정 불가")


def read(src: str) -> list[dict]:
    if src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=30) as r:
            txt = r.read().decode("utf-8")
    else:
        txt = Path(src).read_text(encoding="utf-8")
    return [json.loads(x) for x in txt.splitlines() if x.strip()]


def clean(text: str) -> str:
    """'시나리오 1 · 이름 | - 지켜볼 대응 기준: …' → '이름 | 조건' (대응 기준 꼬리는 뺀다)."""
    t = re.sub(r"\s*\|\s*-?\s*지켜볼 대응 기준:.*$", "", text or "")
    t = re.sub(r"^시나리오\s*\d+\s*·\s*", "", t)
    t = re.sub(r"^\d+\s*·\s*", "", t)
    return re.sub(r"\s+", " ", t).strip()[:120]


def build(rows: list[dict]) -> dict:
    done = [r for r in rows if r.get("outcome") is not None and r.get("status") not in DONE_NOT]
    sc = [r for r in done if r["kind"] == "scenario" and r.get("prob") is not None]
    calls = [r for r in sc if r["status"] in ("적중", "빗나감")]
    hit = sum(r["status"] == "적중" for r in calls)
    brier = round(sum((r["prob"] / 100 - r["outcome"]) ** 2 for r in sc) / len(sc), 3) if sc else None
    buckets = []
    for lo in range(0, 100, 20):
        b = [r for r in sc if lo <= r["prob"] < lo + 20 or (lo == 80 and r["prob"] == 100)]
        if b:
            buckets.append({"lo": lo, "hi": lo + 20, "said": round(sum(r["prob"] for r in b) / len(b)),
                            "actual": round(sum(r["outcome"] for r in b) / len(b) * 100), "hit": sum(r["outcome"] for r in b), "n": len(b)})
    cnt = {}
    for r in rows:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    items = []
    for r in sorted(sorted(done, key=lambda x: -(x.get("prob") or 0)), key=lambda x: (x.get("judged") or "", x.get("slug") or ""), reverse=True):  # 최근 판정 먼저, 같은 리포트 안에서는 가능성 높은 갈래 먼저
        # judged = 결과가 정해진 날(판정일 전에 일찍 갈린 갈래도 있음), judge_date = 리포트에 적은 판정 기한
        items.append({"ticker": r["ticker"], "slug": r.get("slug"), "as_of": r.get("as_of"), "judged": r.get("judged"), "judge_date": r.get("judge_date"),
                      "kind": r["kind"], "text": clean(r.get("text", "")), "prob": r.get("prob"), "outcome": r["outcome"], "status": r["status"]})
    return {"as_of": dt.date.today().isoformat(), "total": len(rows), "judged": len(done),
            "waiting": sum(cnt.get(k, 0) for k in DONE_NOT), "scenarios": len(sc), "calls": {"hit": hit, "n": len(calls)},
            "brier": brier, "buckets": buckets, "rows": items}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "scorecard.json"
    try:
        d = build(read(sys.argv[1]))
    except Exception as e:  # 장부를 못 읽어도 빌드는 저장소의 파일로 계속
        print(f"::warning title=성적표::장부를 읽지 못함({type(e).__name__}) — 저장소의 {out.name} 그대로")
        return 0
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"성적표: 예측 {d['total']} · 판정 끝 {d['judged']} · 콜 {d['calls']['hit']}/{d['calls']['n']} · 브라이어 {d['brier']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
