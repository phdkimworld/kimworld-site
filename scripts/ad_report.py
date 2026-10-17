"""쿠팡 검색어별 성과표(지난 30일)를 주석(annotation)으로 출력한다. ad-report.yml 에서 실행.

입력: .cache/ad_stats_kw.json(Cloudflare 노출·클릭), .cache/coupang_auto.json(검색어·테마), .cache/coupang_reports.json(주문·수수료)
출력: 검색어마다 한 줄 JSON {theme, keyword, sub, imps, clicks, ctr, orders, commission, score}
score = (클릭 + 주문×10) / 노출 × 1000  — 노출 300 미만은 판단 보류(null)
"""
import json
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


if __name__ == "__main__":
    main()
