"""운영 통계 요약(지난 7일 vs 그 전 7일)을 주석(annotation)으로 출력한다. analytics-report.yml 에서 실행.

입력: .cache/an.json (api.drkimworld.com/v1/admin/analytics?days=7 응답)
출력: `::notice title=AN i/n::<JSON>` 주석. 매일 도는 클로드 예약 작업이 읽고 개선점을 찾는다.

저장소가 공개라 Actions 주석도 공개된다. 그래서 집계 숫자만 내보낸다:
사용자 닉네임·상위 사용자·검색어 원문·검색 실패어 원문은 넣지 않는다(검색 실패는 개수만).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".cache" / "an.json"


def pct(a, b):
    return round((a - b) / b * 100, 1) if b else None


def rate(a, b, k=100, nd=1):
    return round(a / b * k, nd) if b else None


def is_name_like(q: str) -> bool:
    """종목 티커·회사 이름처럼 생긴 검색어인지(공개 주석에 실어도 되는지)."""
    q = q.strip()
    if not q or len(q) > 20 or re.search(r"[@/:\\]|\d{4,}", q):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9.\-]{1,10}|[가-힣A-Za-z0-9 .&\-]{1,20}", q)) and len(q.split()) <= 3


def pick(d, keys):
    return {k: d.get(k) for k in keys if k in d}


def summarize(a: dict) -> dict:
    t, p = a.get("totals", {}), a.get("prev", {})
    out = {"days": a.get("days"), "since": a.get("since")}
    out["totals"] = {k: {"now": t.get(k, 0), "prev": p.get(k, 0), "chg_pct": pct(t.get(k, 0) or 0, p.get(k, 0) or 0)}
                     for k in ("pv", "uv", "sess", "multi", "newv", "signups", "secs")}
    out["totals"]["mobile_pct"] = rate(t.get("mob", 0), t.get("pv", 0))
    out["totals"]["pages_per_sess"] = rate(t.get("pv", 0), t.get("sess", 0), 1, 2)
    out["totals"]["multi_page_pct"] = rate(t.get("multi", 0), t.get("sess", 0))
    out["active"] = a.get("active")
    out["series"] = [pick(x, ("day", "pv", "uv", "sess", "secs", "signups")) for x in a.get("series", [])]
    acq = a.get("acq") or {}
    prevCh = {x.get("ch"): x.get("sess", 0) for x in acq.get("channelsPrev", [])}

    def acqrow(x):
        s = x.get("sess") or 0
        return {**pick(x, ("ch", "src", "sess", "pv")), "prevSess": x.get("prevSess", prevCh.get(x.get("ch"))),
                "pages/sess": rate(x.get("pv", 0), s, 1, 2), "secs/sess": rate(x.get("secs", 0), s, 1, 0),
                "engaged_pct": rate(x.get("engaged", 0), s), "deep_pct": rate(x.get("deep", 0), s),
                "new_pct": rate(x.get("newv", 0), s), "app_pct": rate(x.get("app", 0), s),
                "ev": {k: v for k, v in (x.get("ev") or {}).items()}}
    out["channels"] = [acqrow(x) for x in acq.get("channels", [])]
    out["sources"] = [acqrow(x) for x in acq.get("sources", [])[:20]]
    out["landings"] = [pick(x, ("path", "ch", "src", "sess", "pv", "secs", "engaged", "deep")) for x in acq.get("landings", [])[:20]]
    out["campaigns"] = [pick(x, ("src", "med", "cont", "camps", "sess", "pv", "engaged", "deep")) for x in acq.get("campaigns", [])[:20]]
    out["dow"] = acq.get("dow")

    def pagerow(x):
        pv = x.get("pv") or 0
        return {**pick(x, ("path", "t", "pv", "entries", "likes", "comments", "reposts", "app")),
                "secs/pv": rate(x.get("secs", 0), pv, 1, 0),
                "scroll_pct": rate(x.get("scroll", 0), x.get("scroll_n", 0), 1, 0)}
    out["pages"] = [pagerow(x) for x in a.get("pages", [])[:30]]
    out["reports"] = [pagerow(x) for x in a.get("reports", [])[:40]]
    out["types"] = [{**pick(x, ("t", "pv")), "secs/pv": rate(x.get("secs", 0), x.get("pv", 0), 1, 0)} for x in a.get("types", [])]
    out["hours"] = a.get("hours")
    out["events"] = {k: {"now": v, "prev": (a.get("eventsPrev") or {}).get(k, 0)} for k, v in sorted((a.get("events") or {}).items(), key=lambda kv: -kv[1])}
    out["ads"] = [{**pick(x, ("slot", "imps", "clicks")), "ctr_pct": rate(x.get("clicks", 0), x.get("imps", 0), 100, 2)} for x in a.get("ads", [])]
    out["community"] = a.get("community")
    out["actions"] = a.get("actions")
    out["app"] = a.get("app")
    out["topics"] = [pick(x, ("kind", "key", "n")) for x in a.get("topics", [])]
    out["topicNew"] = a.get("topicNew")
    s = a.get("sentiment") or {}
    out["sentiment"] = {**pick(s, ("votes", "voters", "tickers", "repeat", "prevVotes", "prevVoters")),
                        "top": [pick(x, ("ticker", "bull", "bear")) for x in s.get("top", [])[:10]]}
    # 리포트 구간별 도달·체류(0022): 전체 곡선(첫 구간 대비 도달 %, 도달한 사람의 평균 초)과 페이지뷰 상위 리포트 8개의 같은 곡선
    SEC = ["top", "ans", "can", "news", "term", "p1", "p2", "p3", "p4", "p5", "p6", "src", "more", "comm"]

    def curve(rows):
        m = {x.get("sec"): x for x in rows}
        base = (m.get("top") or {}).get("reach") or 0
        return {"n": base, **{c: [rate(m[c].get("reach", 0), base, 100, 0), rate(m[c].get("secs", 0), m[c].get("reach", 0), 1, 0)]
                             for c in SEC if c in m}} if base else None
    sec = a.get("sections") or {}
    out["sections"] = {"all": curve(sec.get("all") or [])}
    byp = {}
    for x in sec.get("byPath") or []:
        byp.setdefault(x.get("path"), []).append(x)
    top = [x.get("path") for x in a.get("reports", []) if x.get("path") in byp][:8]
    out["sections"]["reports"] = {p: curve(byp[p]) for p in top}
    out["updReq"] = a.get("updReq")  # 리포트 업데이트 요청(최근 30일, 종목별 합계)
    out["bots"] = a.get("bots")
    out["os"] = {}
    for x in a.get("tech", []):
        out["os"][x.get("os")] = out["os"].get(x.get("os"), 0) + (x.get("pv") or 0)
    out["cohorts"] = [pick(x, ("day", "n", "d1", "d7")) for x in a.get("cohorts", [])[-14:]]
    misses = a.get("misses") or []
    out["search_miss"] = {"distinct": len(misses), "total": sum(x.get("n", 0) for x in misses)}
    # 결과 없던 검색어 = 2순위 종목 요청(운영자 지시 2026-10-26 "결과 없던 검색어도 세컨티어 요청종목으로 간주").
    # 주석은 공개되므로 종목·회사 이름처럼 생긴 짧은 검색어만 싣는다(이메일·전화번호·긴 문장 등 개인정보가 될 수 있는 것은 뺀다)
    out["search_miss_top"] = [{"q": x.get("q"), "n": x.get("n", 0)} for x in misses if is_name_like(x.get("q") or "")][:20]
    out["searches_total"] = sum(x.get("n", 0) for x in a.get("searches", []))
    return out


def main() -> None:
    try:
        a = json.loads(SRC.read_text(encoding="utf-8"))
    except Exception as e:  # 응답이 JSON 이 아니면(권한 오류 등) 원인만 알린다
        print(f"::error title=AN::analytics 응답을 읽지 못함 ({type(e).__name__})")
        raise SystemExit(1)
    if a.get("error"):
        print(f"::error title=AN::analytics 오류 {a.get('error')}")
        raise SystemExit(1)
    out = summarize(a)
    for k, v in out.items():
        while isinstance(v, list) and len(v) > 3 and len(json.dumps({k: v}, ensure_ascii=False)) > 3200:
            v = v[: max(3, len(v) * 3 // 4)]
        out[k] = v
    # 섹션 단위로 3300자 안쪽(주석 한 개는 4096자에서 잘리고, 한 단계에 10개까지만 보인다) 덩어리로 나눈다(주석 하나의 길이 제한)
    chunks, cur = [], {}
    for k, v in out.items():
        cur[k] = v
        if len(json.dumps(cur, ensure_ascii=False)) > 3300 and len(cur) > 1:
            del cur[k]
            chunks.append(cur)
            cur = {k: v}
    if cur:
        chunks.append(cur)
    for i, ch in enumerate(chunks[:9]):
        msg = json.dumps(ch, ensure_ascii=False, separators=(",", ":")).replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::notice title=AN {i + 1}/{len(chunks)}::{msg}")


if __name__ == "__main__":
    main()
