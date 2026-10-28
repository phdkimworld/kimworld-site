"""쿠팡 검색어별 성과표(지난 30일)를 주석(annotation)으로 출력한다. ad-report.yml 에서 실행.

입력: .cache/ad_stats_kw.json(Cloudflare 노출·클릭), .cache/coupang_auto.json(검색어·테마), .cache/coupang_reports.json(주문·수수료)
출력: 검색어마다 한 줄 JSON {theme, keyword, sub, imps, clicks, ctr, orders, commission, score}
score = (클릭 + 주문×10) / 노출 × 1000  — 노출 300 미만은 판단 보류(null)
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / ".cache"


def load(name, default):
    try:
        return json.loads((C / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> None:
    raw = load("ad_stats_kw.json", [])
    rows = raw[0].get("results", []) if isinstance(raw, list) and raw else []
    stat = {r["g"]: (int(r.get("imps") or 0), int(r.get("clicks") or 0)) for r in rows}
    rep = load("coupang_reports.json", {}).get("by_sub", {})
    out = []
    for e in (load("coupang_auto.json", {}).get("entries") or {}).values():
        sid = e.get("sub_id")
        i, c = stat.get(sid, (0, 0))
        o = int((rep.get(sid) or {}).get("orders") or 0)
        com = round(float((rep.get(sid) or {}).get("commission") or 0))
        out.append({"theme": e.get("theme"), "keyword": e.get("keyword"), "sub": sid, "imps": i, "clicks": c,
                    "ctr": round(c / i * 100, 2) if i else None, "orders": o, "commission": com,
                    "score": round((c + o * 10) / i * 1000, 1) if i >= 300 else None})
    out.sort(key=lambda x: (x["theme"] or "", -(x["score"] or -1)))
    allrep = load("coupang_reports.json", {})
    total = round(float(allrep.get("total") or 0))
    ours = {e.get("sub_id") for e in (load("coupang_auto.json", {}).get("entries") or {}).values()}
    site_com = sum(round(float(v.get("commission") or 0)) for k, v in rep.items() if k in ours)
    other = {k: v for k, v in rep.items() if k not in ours}
    summary = {"report_ts": allrep.get("ts"), "source": allrep.get("source"), "commission_30d_total": total, "commission_site_product_boxes": site_com,
               "commission_without_site_subid": total - site_com - sum(round(float(v.get("commission") or 0)) for v in other.values()),
               "other_subids": other, "site_box_clicks_counted_by_site": sum(x["clicks"] for x in out)}
    json_out = os.environ.get("JSON_OUT")
    if json_out:  # 전체(수수료 포함)는 파일로 → 워크플로가 비공개 저장소에 올린다
        Path(json_out).write_text(json.dumps({"keywords": out, "summary": summary}, ensure_ascii=False), encoding="utf-8")
    if os.environ.get("NO_ANNOTATIONS") == "1":
        print(f"::notice title=ADS PRIVATE::검색어 {len(out)}개 · 비공개 저장소 stats/ads.json")
        return
    # 공개 주석(비공개 저장소를 못 쓸 때만): 수수료·주문은 빼고 노출·클릭만
    out = [{k: v for k, v in x.items() if k not in ("orders", "commission")} for x in out]
    summary = {"site_box_clicks_counted_by_site": summary["site_box_clicks_counted_by_site"]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    chunks, cur = [], []
    for x in out:
        cur.append(x)
        if len(json.dumps(cur, ensure_ascii=False)) > 3300:  # 주석 하나는 4096자에서 잘린다
            chunks.append(cur[:-1]); cur = [x]
    if cur:
        chunks.append(cur)
    for i, ch in enumerate(chunks[:9]):
        msg = json.dumps(ch, ensure_ascii=False).replace("%", "%25").replace("\n", "%0A")
        print(f"::notice title=ADS {i + 1}/{len(chunks)}::{msg}")
    print(f"::notice title=ADS COUNT::{len(out)}")
    print("::notice title=ADS SUMMARY::" + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
