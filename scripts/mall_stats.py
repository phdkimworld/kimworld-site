#!/usr/bin/env python3
"""김박사 몰 추적 기록을 쌓고 요약한다(2026-11-20 운영자 "몰 페이지 트래픽 다각화해서 체계적으로 추적해서 저장해놓고 인사이트로 활용해").

모으는 것(워커 D1 mall_ev, 하루 합계·사람 정보 없음 — worker/migrations/0032_mall_ev.sql):
  land  사이트 입구 drkimworld.com/mall/ 도착(src = utm_source, sl = utm_content 또는 utm_campaign: 어느 영상·글에서)
  view  몰 화면 보기(src = 입구가 넘긴 채널 > utm_source > 리퍼러 묶음 > direct, pg = home·deals·c-<카테고리>·search·cats·about)
  click 쿠팡으로 나가는 링크 누름(sl = 누른 칸: hero·entry·deals·rank·row-<카테고리>·grid·search)
쿠팡 쪽 실제 클릭·수수료는 하위 ID mall…(비공개 coupang.json by_sub)로 따로 본다 — 몰 click 과 쿠팡 클릭의 차이가 '누르고 쿠팡에서 안 열린' 몫이다.

사용: python3 scripts/mall_stats.py <an.json> <coupang.json|-> <history.json(있으면 이어 씀)> <summary.md 출력>
 - history.json: {"days": {"YYYY-MM-DD": [행…]}, "coupang": {"YYYY-MM-DD": {"range": [...], "subs": {...}}}}. 날마다 그날 값을 새 값으로 바꿔 쓴다(하루 동안 계속 쌓이므로).
 - 이 파일들은 비공개 저장소(ops-data stats/mall/)에만 올린다. 수수료가 들어 있다.
"""
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8")) if p and p != "-" and Path(p).exists() else {}
    except Exception:
        return {}


def merge(hist: dict, rows: list, cp: dict, today: str) -> dict:
    days = hist.setdefault("days", {})
    by = defaultdict(list)
    for r in rows or []:
        if isinstance(r, dict) and r.get("day") and r.get("k") in ("land", "view", "click"):
            by[r["day"]].append({k: r.get(k) for k in ("k", "src", "pg", "sl", "n", "u")})
    for d, rs in by.items():
        days[d] = sorted(rs, key=lambda x: (x["k"], x["src"], x["pg"], x["sl"]))
    subs = {k: v for k, v in (cp.get("by_sub") or {}).items() if str(k).startswith("mall")}
    if cp:
        hist.setdefault("coupang", {})[today] = {"range": cp.get("range"), "subs": subs}
    hist["updated"] = today
    return hist


def window(hist: dict, end: dt.date, n: int) -> list:
    out = []
    for d, rs in (hist.get("days") or {}).items():
        try:
            dd = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if end - dt.timedelta(days=n - 1) <= dd <= end:
            out += rs
    return out


def agg(rows: list, key, k: str, f: str = "n") -> dict:
    o = defaultdict(int)
    for r in rows:
        if r["k"] == k:
            o[key(r)] += int(r.get(f) or 0)
    return dict(o)


def summary(hist: dict, end: dt.date) -> str:
    cur, prev = window(hist, end, 7), window(hist, end - dt.timedelta(days=7), 7)
    L = [f"# 김박사 몰 추적 요약 {end} (최근 7일, 괄호는 전 7일)", ""]
    if not cur and not prev:
        L += ["- 아직 기록 없음(추적 시작 2026-11-20). 입구·몰 화면이 열리면 쌓인다.", ""]
    src = lambda r: r["src"]
    land, view, click = agg(cur, src, "land", "u"), agg(cur, src, "view", "u"), agg(cur, src, "click")
    pland, pview, pclick = agg(prev, src, "land", "u"), agg(prev, src, "view", "u"), agg(prev, src, "click")
    chans = sorted(set(land) | set(view) | set(click) | set(pland) | set(pview), key=lambda s: -(view.get(s, 0) + land.get(s, 0)))
    L.append("## 채널별 깔때기: 입구 도착(사람) → 몰 화면(사람) → 쿠팡 클릭(번) · 클릭률")
    for s in chans:
        v, c = view.get(s, 0), click.get(s, 0)
        L.append(f"- {s}: 입구 {land.get(s, 0)}({pland.get(s, 0)}) → 몰 {v}({pview.get(s, 0)}) → 클릭 {c}({pclick.get(s, 0)})" + (f" · {c / v * 100:.0f}%" if v else ""))
    tv, tc = sum(view.values()), sum(click.values())
    L.append(f"- 합계: 입구 {sum(land.values())} → 몰 {tv} → 클릭 {tc}" + (f" · {tc / tv * 100:.0f}%" if tv else ""))
    L += ["", "## 화면별 보기(사람)·클릭(번)"]
    pv, pc = agg(cur, lambda r: r["pg"], "view", "u"), agg(cur, lambda r: r["pg"], "click")
    for p in sorted(set(pv) | set(pc), key=lambda x: -pv.get(x, 0)):
        L.append(f"- {p}: 보기 {pv.get(p, 0)} · 클릭 {pc.get(p, 0)}")
    L += ["", "## 누른 칸(번)"]
    sl = agg(cur, lambda r: r["sl"], "click")
    L.append("- " + (" · ".join(f"{k} {v}" for k, v in sorted(sl.items(), key=lambda kv: -kv[1])) or "없음"))
    L += ["", "## 입구 세부(어느 영상·글에서, utm_content·campaign, 사람)"]
    ld = agg(cur, lambda r: f"{r['src']}/{r['sl']}", "land", "u")
    L.append("- " + (" · ".join(f"{k} {v}" for k, v in sorted(ld.items(), key=lambda kv: -kv[1])[:15]) or "없음"))
    cp = (hist.get("coupang") or {}).get(str(end)) or (sorted((hist.get("coupang") or {}).items())[-1][1] if hist.get("coupang") else {})
    if cp:
        subs = cp.get("subs") or {}
        L += ["", f"## 쿠팡 하위 ID mall…(쿠팡 보고 기간 {cp.get('range')})",
              "- " + (" · ".join(f"{k} {v.get('clicks', 0)}클릭/{v.get('commission', 0)}원" for k, v in subs.items()) or "클릭 0"),
              f"- 몰 화면 클릭(7일) {tc} 대 쿠팡이 센 mall… 클릭 {sum(v.get('clicks', 0) for v in subs.values())} — 기간이 달라 대략 비교"]
    # 자동 관찰(판단 재료): 숫자가 적으면 결론을 내지 않는다
    L += ["", "## 관찰"]
    obs = []
    if tv < 30:
        obs.append(f"표본 작음(몰 방문 {tv}명) — 채널·칸 비교는 30명 넘은 뒤에")
    for s in chans:
        if land.get(s, 0) >= 5 and view.get(s, 0) < land[s] * 0.5:
            obs.append(f"{s}: 입구 {land[s]}명 중 몰 도착 {view.get(s, 0)}명 — 넘겨주기에서 새는지 확인")
        if view.get(s, 0) >= 10 and not click.get(s):
            obs.append(f"{s}: 몰 {view[s]}명이 봤는데 클릭 0 — 이 채널 사람에게 맞는 첫 화면·카테고리인지")
    if tc >= 10:
        top = max(sl.items(), key=lambda kv: kv[1])
        obs.append(f"클릭이 가장 많은 칸 {top[0]}({top[1] / tc * 100:.0f}%) — 첫 화면에서 이 칸을 위로")
    zero = [p for p in pv if p.startswith("c-") and pv[p] >= 5 and not pc.get(p)]
    if zero:
        obs.append("본 사람은 있는데 클릭 0인 카테고리: " + ", ".join(zero) + " — 12-03 판정 때 바꿀 후보")
    L += [f"- {o}" for o in obs] or ["- 특이점 없음"]
    return "\n".join(L) + "\n"


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    an, cp, hp, out = load(sys.argv[1]), load(sys.argv[2]), sys.argv[3], sys.argv[4]
    today = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).date()  # 워커 날짜는 한국 기준
    hist = merge(load(hp), an.get("mall") or [], cp, str(today))
    Path(hp).parent.mkdir(parents=True, exist_ok=True)
    Path(hp).write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
    Path(out).write_text(summary(hist, today), encoding="utf-8")
    print(f"김박사 몰 기록: {len(hist.get('days') or {})}일 · 요약 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
