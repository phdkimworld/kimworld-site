#!/usr/bin/env python3
"""쿠팡 파트너스 API 보고서(클릭·주문·수수료)를 날짜별로 받는다(coupang-stats.yml에서 매일).

공개 저장소에는 숫자를 남기지 않는다(2026-10-28 운영자 요청): 날짜별 행은 ROWS_OUT 파일 → 워크플로가 워커 비공개 D1(/v1/admin/revenue-import)로 보내고,
요약은 SEAL_OUT 파일 → 비공개 저장소 stats/coupang.json(scripts/ops_publish.sh). 상품명 등 주문 상세는 어디에도 남기지 않는다.

쿠팡이 센 숫자라 사이트에서 못 세는 다이내믹 배너(iframe) 클릭까지 들어 있다. 하위 ID로 자리를 나눈다:
  banner = 페이지 맨 아래 다이내믹 배너(2026-10-28부터 subId), deal = 리포트 끝 '오늘의 특가'(골드박스, 2026-10-30), 테마별 상품 상자 = data/coupang.yaml 검색어 하위 ID, 그 밖 = 하위 ID 없음·사이트 밖 링크
환경변수: COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY, ROWS_OUT, SEAL_OUT. PROBE=1이면 응답 필드 이름을 봉인 요약에 넣는다(주석에는 안 씀).
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coupang_sync as cs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1/reports/"
COLS = ["day", "clicks", "clicks_banner", "clicks_boxes", "clicks_deal", "clicks_other", "orders", "gmv", "commission", "commission_banner", "commission_boxes", "commission_deal", "commission_other", "click_addtags"]


def rows_of(js):
    d = js.get("data") if isinstance(js, dict) else None
    if isinstance(d, dict):
        d = d.get("data") or d.get("items") or d.get("content") or []
    return [x for x in (d or []) if isinstance(x, dict)]


def first(x, *names, default=0):
    for n in names:
        if x.get(n) not in (None, ""):
            return x[n]
    return default


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def day_of(x):
    d = str(first(x, "date", "orderDate", "clickDate", "statDate", default=""))
    d = d.replace("-", "")[:8]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else ""


def fetch(kind, start, end, access, secret):
    out, page = [], 0
    while page < 20:
        q = urllib.parse.urlencode({"startDate": start, "endDate": end, "page": page})
        rs = rows_of(cs.report_get(BASE + kind, q, access, secret))
        out += rs
        if len(rs) < 1000:
            break
        page += 1
    return out


def main() -> None:
    access, secret = os.environ.get("COUPANG_ACCESS_KEY", ""), os.environ.get("COUPANG_SECRET_KEY", "")
    if not access or not secret:
        print("::warning::쿠팡 API 키 없음 — 건너뜀"); return
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    start, end = (kst - dt.timedelta(days=30)).strftime("%Y%m%d"), (kst - dt.timedelta(days=1)).strftime("%Y%m%d")
    import yaml
    boxes = set()
    try:
        auto = json.loads((ROOT / ".cache" / "coupang_auto.json").read_text(encoding="utf-8"))
        boxes = {str(e.get("sub_id") or "").lower() for e in (auto.get("entries") or {}).values()}
    except Exception:
        cfg = yaml.safe_load((ROOT / "data" / "coupang.yaml").read_text(encoding="utf-8")) or {}
        themes = yaml.safe_load((ROOT / "data" / "themes.yaml").read_text(encoding="utf-8")) or []
        themes = themes.get("themes", themes) if isinstance(themes, dict) else themes
        try:
            boxes = {j["sub_id"].lower() for j in cs.plan(cfg, themes)}
        except Exception:
            boxes = set()

    def where(x):
        s = str(first(x, "subId", "subid", "sub_id", "subParam", default="")).lower()
        return "banner" if s == "banner" else "deal" if s == cs.DEAL_SUB else "boxes" if s in boxes else "other"

    data, seen_orders, tags, probe = {}, set(), {}, {}
    for kind in ("clicks", "orders", "commission"):
        try:
            rs = fetch(kind, start, end, access, secret)
        except Exception as e:
            print(f"::warning title=쿠팡 {kind}::받기 실패 {type(e).__name__}: {str(e)[:200]}")
            continue
        if os.environ.get("PROBE") == "1":
            probe[kind] = sorted({k for x in rs for k in x})
        for x in rs:
            d = day_of(x)
            if not d:
                continue
            r = data.setdefault(d, {c: 0 for c in COLS if c not in ("day", "click_addtags")})
            w = where(x)
            if kind == "clicks":
                n = int(num(first(x, "click", "clicks", "clickCount", "count")))
                r["clicks"] += n; r["clicks_" + w] += n
                t = str(first(x, "addtag", default="?")); tags.setdefault(d, {}); tags[d][t] = tags[d].get(t, 0) + n
            elif kind == "orders":
                oid = str(first(x, "orderId", default="")) or json.dumps(x, sort_keys=True)
                if oid not in seen_orders:  # 주문 하나에 상품 여러 줄 → 주문 수는 한 번
                    seen_orders.add(oid); r["orders"] += 1
                r["gmv"] += round(num(first(x, "gmv", "orderPrice", "price", "amount")))
            else:
                c = round(num(first(x, "commission", "commissionAmount", "amount")))
                r["commission"] += c; r["commission_" + w] += c
    if not data:
        print("::notice title=쿠팡 일별::받은 자료 없음"); return
    rows = []
    for d in sorted(data):
        rows.append({"day": d, **data[d], "click_addtags": ";".join(f"{k}:{v}" for k, v in sorted((tags.get(d) or {}).items()))})
    Path(os.environ.get("ROWS_OUT") or ROOT / ".cache" / "coupang_rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    tot = {k: sum(int(float(r.get(k) or 0)) for r in data.values()) for k in ("clicks", "clicks_banner", "clicks_boxes", "clicks_deal", "clicks_other", "orders", "gmv", "commission", "commission_deal", "commission_boxes")}
    allt = {}
    for t in tags.values():
        for k, v in t.items():
            allt[k] = allt.get(k, 0) + v
    summ = {**tot, "click_addtags": allt, "days": len(rows), "range": [start, end], **({"probe_fields": probe} if probe else {})}
    Path(os.environ.get("SEAL_OUT") or ROOT / ".cache" / "coupang_summary.json").write_text(json.dumps(summ, ensure_ascii=False), encoding="utf-8")
    print(f"::notice title=쿠팡 일별::{len(rows)}일치 받음(숫자는 비공개 저장)")


if __name__ == "__main__":
    main()
