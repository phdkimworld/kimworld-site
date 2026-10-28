#!/usr/bin/env python3
"""카카오 애드핏 데일리 리포트(운영자가 채팅에 붙여 주는 글)를 data/adfit_daily.csv에 한 줄로 넣는다(같은 날이면 고친다).

사용: python3 scripts/adfit_add.py < 붙여넣은글.txt      (메모를 붙이려면 --note "토요일")
      python3 scripts/adfit_add.py --show                   (최근 기록과 주간 요약)
CSV는 운영 통계 화면(/admin/ '애드핏 실적')이 빌드 때 adfit.json으로 받아 그린다.
열: day,earn(예상 적립금 원),requests,impressions(보인 노출),rendered(렌더드 노출),clicks,ecpm(원),cum_earn(전체 예상 적립금),confirmed(확정 적립금),note
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "adfit_daily.csv"
COLS = ["day", "earn", "requests", "impressions", "rendered", "clicks", "ecpm", "cum_earn", "confirmed", "note"]


def num(pat: str, text: str):
    m = re.search(pat + r"\s*[:：]\s*([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def parse(text: str) -> dict:
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:  # 매체별 보고서: '조회일: 10월 27일 (Tue)' — 한국 날짜 기준 올해(앞으로의 달이면 작년)
        m = re.search(r"조회일\s*[:：]?\s*(\d{1,2})월\s*(\d{1,2})일", text)
        if not m:
            raise SystemExit("조회일을 찾지 못했습니다")
        import datetime as _dt
        k = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).date()
        mo, d = int(m.group(1)), int(m.group(2))
        y = k.year - 1 if mo > k.month else k.year
    row = {"day": f"{y}-{mo:02d}-{d:02d}"}
    row["cum_earn"] = num(r"전체 예상 적립금", text)
    row["confirmed"] = num(r"확정 적립금", text)
    # '예상 적립금'은 '전체 예상 적립금' 줄과 겹치므로 그 줄을 지운 뒤 찾는다
    body = re.sub(r"전체 예상 적립금[^\n]*", "", text)
    row["earn"] = num(r"예상 적립금", body)
    row["requests"] = num(r"요청수", text)
    row["rendered"] = num(r"렌더드 노출수", text)
    row["impressions"] = num(r"(?<!렌더드 )노출수", text)
    row["clicks"] = num(r"클릭수", text)
    row["ecpm"] = num(r"eCPM", text)
    miss = [k for k in ("earn", "requests", "impressions", "rendered") if row[k] is None]
    if miss:
        raise SystemExit(f"값을 찾지 못함: {', '.join(miss)}")
    return row


def load() -> list:
    if not CSV.exists():
        return []
    with CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(rows: list) -> None:
    rows.sort(key=lambda r: r["day"])
    with CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})


def show(rows: list) -> None:
    for r in rows[-10:]:
        vr = int(r["impressions"]) / int(r["rendered"]) * 100 if int(r["rendered"] or 0) else 0
        print(f"{r['day']}  적립 {r['earn']:>3}원  요청 {r['requests']:>4}  렌더 {r['rendered']:>4}  보임 {r['impressions']:>3} ({vr:.0f}%)  클릭 {r['clicks']}  eCPM {r['ecpm']}  누적 {r['cum_earn']}")
    last7 = rows[-7:]
    if last7:
        e = sum(int(r["earn"]) for r in last7)
        im = sum(int(r["impressions"]) for r in last7)
        rd = sum(int(r["rendered"]) for r in last7)
        print(f"최근 {len(last7)}일: 적립 {e}원(하루 {e / len(last7):.1f}원), 보이는 비율 {im / rd * 100 if rd else 0:.0f}%, eCPM {e / im * 1000 if im else 0:.0f}원")


def main() -> None:
    args = sys.argv[1:]
    rows = load()
    if "--show" in args:
        show(rows)
        return
    note = args[args.index("--note") + 1] if "--note" in args else ""
    row = parse(sys.stdin.read())
    old = next((r for r in rows if r["day"] == row["day"]), None)
    if old:
        row["note"] = note or old.get("note", "")
        for k in COLS:  # 매체별 보고서처럼 빠진 값은 예전 값을 지킨다
            if row.get(k) is None and old.get(k) not in (None, ""):
                row[k] = old[k]
        rows = [r for r in rows if r["day"] != row["day"]]
    else:
        row["note"] = note
    rows.append(row)
    save(rows)
    print(("고침" if old else "추가") + f": {row['day']}")
    show(load())


if __name__ == "__main__":
    main()
