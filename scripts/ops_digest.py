#!/usr/bin/env python3
"""운영 요약 한 장(stats/digest.md, 비공개) — 매일 점검 세션이 큰 JSON을 읽지 않고 이것만 읽게(운영자 지시 2026-11-17 "주간한도 사용을 줄여").

LLM 없이 숫자만 계산한다. analytics-report.yml 이 비공개 저장소에 stats/analytics.json 을 올린 뒤 실행한다.
사용: python3 scripts/ops_digest.py <analytics.json> [coupang.json] > digest.md
담는 것: 7일 핵심(전주 대비), 채널, 랜딩 상위, 투표, 애드핏·쿠팡 7일(유튜브 카테고리·하위 ID별), 쿠팡 실험 현황,
         애드센스 재신청 기준 충족 여부(a/5), 블로거 비교 글 진행, 이상 신호(애드핏 기록 끊김 등).
수익 숫자가 들어 있으니 공개 저장소·주석에는 쓰지 않는다(비공개 ops-data 에만).
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pct(now, prev):
    return "" if not prev else f"({(now - prev) / prev * 100:+.0f}%)"


def g(d, *ks, default=0):
    for k in ks:
        d = d.get(k, {}) if isinstance(d, dict) else {}
    return d if d not in ({}, None) else default


def public_reports() -> int:
    n = 0
    for p in (ROOT / "content" / "reports").glob("*.md"):
        head = p.read_text(encoding="utf-8")[:1500]
        if not re.search(r"(?m)^draft:\s*true", head):
            n += 1
    return n


def guard_now(a: dict) -> dict:
    """리포트 평균 체류(초/PV)·스크롤 깊이(%)는 리포트 PV 가중 평균, 페이지/세션은 전체."""
    rs = [r for r in a.get("reports") or [] if r.get("secs/pv") is not None and r.get("scroll_pct") is not None]
    pv = sum(r["pv"] for r in rs)
    return {"report_pv": pv,
            "report_secs": round(sum(r["pv"] * r["secs/pv"] for r in rs) / pv, 1) if pv else None,
            "report_scroll": round(sum(r["pv"] * r["scroll_pct"] for r in rs) / pv, 1) if pv else None,
            "pages_per_sess": (a.get("totals") or {}).get("pages_per_sess")}


def guard_lines(a: dict, today) -> list:
    txt = (ROOT / "ads.yaml").read_text(encoding="utf-8")
    try:
        import yaml
        gd = (yaml.safe_load(txt) or {}).get("guard") or {}
    except ImportError:  # 실행 환경에 PyYAML이 없으면 guard 칸만 글자로 읽는다
        m = re.search(r"(?m)^guard:\n((?:  .*\n)+)", txt)
        blk = m.group(1) if m else ""
        f = lambda k: (re.search(rf"(?m)^  {k}:\s*\"?([^\"\n]*)", blk) or [None, ""])[1].strip()
        bl = dict((k, float(v)) for k, v in re.findall(r"(\w+):\s*([\d.]+)", (re.search(r"baseline:\s*\{([^}]*)\}", blk) or [None, ""])[1]))
        gd = {"baseline": bl, "judge": f("judge"), "max_drop_pct": f("max_drop_pct") or 10, "min_report_pv": f("min_report_pv") or 60, "last_change": f("last_change")} if bl else {}
    base, now = gd.get("baseline") or {}, guard_now(a)
    if not base:
        return ["기준 없음(ads.yaml guard)"]
    judge = dt.date.fromisoformat(str(gd.get("judge")))
    names = {"report_secs": "리포트 평균 체류(초)", "report_scroll": "스크롤 깊이(%)", "pages_per_sess": "페이지/세션"}
    worse, parts = [], []
    for k, n in names.items():
        b, x = base.get(k), now.get(k)
        if not b or x is None:
            continue
        ch = (x - b) / b * 100
        parts.append(f"{n} {x} (기준 {b}, {ch:+.0f}%)")
        if ch < -float(gd.get("max_drop_pct", 10)):
            worse.append(n)
    small = now["report_pv"] < int(gd.get("min_report_pv", 60))
    tail = f"마지막 추가분: {gd.get('last_change', '')}"
    if today < judge:
        head = f"관찰 중(판정 {judge})"
    elif small:
        head = f"표본 부족(리포트 PV {now['report_pv']} < {gd.get('min_report_pv', 60)}) — 판정 미룸"
    elif worse:
        head = f"되돌릴 것 — {'·'.join(worse)} 10% 넘게 나빠짐"
    else:
        head = "유지(세 지표 모두 기준 대비 -10% 이내)"
    return [head, "- " + " · ".join(parts) + f" · 리포트 PV {now['report_pv']}", "- " + tail]


def main() -> int:
    a = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    c = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) if len(sys.argv) > 2 and Path(sys.argv[2]).exists() else {}
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).date()
    t = a.get("totals", {})
    out = [f"# 운영 요약 {today} (ET) · 기간 {a.get('since')}부터 {a.get('days')}일", ""]
    s_now, s_prev = g(t, "sess", "now"), g(t, "sess", "prev")
    out.append(f"- 세션 {s_now} {pct(s_now, s_prev)} · 하루 {s_now / max(1, a.get('days', 7)):.0f} · 방문자 {g(t, 'uv', 'now')} {pct(g(t, 'uv', 'now'), g(t, 'uv', 'prev'))} · PV {g(t, 'pv', 'now')} · 신규 {g(t, 'newv', 'now')}")
    act = a.get("active", {})
    out.append(f"- 활성 DAU {act.get('dau')} · WAU {act.get('wau')} · MAU {act.get('mau')} · 빠른 이탈 {g(a, 'bots', 'quick')}/{s_now}")
    qlb = a.get("quick_land_by") or {}
    if qlb:  # 빠른 이탈 랜딩 종류:유입(검색은 엔진별, 2026-11-18부터) 상위 5
        out.append("- 빠른 이탈 랜딩: " + " · ".join(f"{k} {v}" for k, v in list(qlb.items())[:5]))
    out.append("")
    out.append("## 채널(세션, 전주)")
    for ch in a.get("channels", [])[:8]:
        out.append(f"- {ch['ch']}: {ch['sess']} (전주 {ch.get('prevSess') or 0}) · 체류 {ch.get('secs/sess', 0):.0f}초 · 참여 {ch.get('engaged_pct', 0):.0f}%")
    srch = sum(ch["sess"] for ch in a.get("channels", []) if ch["ch"] == "search")
    out.append("")
    out.append("## 랜딩 상위 5")
    for l in a.get("landings", [])[:5]:
        out.append(f"- {l['path']} · {l['src']} · {l['sess']}세션")
    se = a.get("sentiment", {})
    out += ["", f"## 투표: 참여자 {se.get('voters')} (전주 {se.get('prevVoters')}) · 투표 {se.get('votes')} (전주 {se.get('prevVotes')}) · 재참여 {se.get('repeat')} · 참여율 {(se.get('voters') or 0) / max(1, s_now) * 100:.1f}%"]
    ev = a.get("events", {})
    keys = ["yt_sub_home", "yt_sub_report", "yt_tab", "home_search", "share", "share_kakao", "install_click", "next_bar"]
    out.append("- 이벤트: " + " · ".join(f"{k} {g(ev, k, 'now')}({g(ev, k, 'prev')})" for k in keys if k in ev) or "- 이벤트 없음")

    ad = a.get("adfit", [])
    last7 = ad[:7] if ad and ad[0]["day"] >= ad[-1]["day"] else ad[-7:]
    out += ["", "## 수익(최근 7일)"]
    out.append(f"- 애드핏 {sum(x.get('earn') or 0 for x in last7)}원 · 노출 {sum(x.get('impressions') or 0 for x in last7)} · 마지막 기록 {max((x['day'] for x in ad), default='없음')}")
    cp = sorted(a.get("coupang", []), key=lambda x: x["day"])[-7:]
    if cp:
        out.append(f"- 쿠팡 클릭 {sum(x['clicks'] for x in cp)} (유튜브 {sum(x.get('clicks_youtube') or 0 for x in cp)} · 블로거 {sum(x.get('clicks_blogger') or 0 for x in cp)} · 기타 {sum(x.get('clicks_other') or 0 for x in cp)}) · 주문 {sum(x.get('orders') or 0 for x in cp)} · 수수료 {sum(x.get('commission') or 0 for x in cp)}원 · 마지막 {cp[-1]['day']}")
    if c:
        yc = c.get("yt_by_cat") or {}
        if yc:
            out.append("- 유튜브 카테고리(보고서 기간): " + " · ".join(f"{k} 클릭{v.get('clicks')}/수수료{v.get('commission')}" for k, v in yc.items()))
        bs = c.get("by_sub") or {}
        if bs:
            out.append("- 하위 ID 상위: " + " · ".join(f"{k} {v['clicks']}클릭/{v['commission']}원" for k, v in list(bs.items())[:8]))
    def mall_funnel(rows):
        """2026-11-20 추적(D1 mall_ev): 채널별 입구 도착 → 몰 화면 → 쿠팡 클릭. 자세한 것은 ops-data stats/mall/summary.md"""
        f = {}
        for r in rows:
            d = f.setdefault(r.get("src") or "?", {"land": 0, "view": 0, "click": 0})
            if r.get("k") in d:
                d[r["k"]] += int(r.get("n") if r["k"] == "click" else r.get("u") or 0)
        return " · ".join(f"{s} 입구{d['land']}→몰{d['view']}→클릭{d['click']}" for s, d in sorted(f.items(), key=lambda kv: -kv[1]["view"])[:6]) or "0(추적 2026-11-20 시작)"

    # 김박사 몰(2026-11-19, 쇼핑몰 사이트): 쿠팡 하위 ID mall…(입구 go·특가 gb·카테고리) + 사이트 /mall/ 랜딩(채널별 utm_source). 이 하위 ID는 쿠팡 칸 '기타'에도 들어 있다
    if c:
        mb = {k: v for k, v in (c.get("by_sub") or {}).items() if k.startswith("mall")}
        mc = json.loads((ROOT / "mall" / "catalog.json").read_text(encoding="utf-8")) if (ROOT / "mall" / "catalog.json").exists() else {}
        out.append("- 김박사 몰: " + (" · ".join(f"{k} {v['clicks']}클릭/{v['commission']}원" for k, v in mb.items()) or "쿠팡 클릭 0")
                   + f" (합계 {sum(v['clicks'] for v in mb.values())}클릭/{sum(v['commission'] for v in mb.values())}원)"
                   + " | 몰 추적 7일(사람): " + mall_funnel(a.get("mall") or [])
                   + f" | 진열 특가 {len(mc.get('deals') or [])} · 카테고리 {len(mc.get('cats') or {})} · 갱신 {mc.get('updated') or '없음'}")
    # 김박사 건강몰(2026-11-19, health.drkimworld.com): 쿠팡 하위 ID hm…(성분별 hm<코드> · 베스트 hmbest). 이 하위 ID도 쿠팡 칸 '기타'에 들어 있다
    if c:
        hb = {k: v for k, v in (c.get("by_sub") or {}).items() if k.startswith("hm")}
        hc = json.loads((ROOT / "health" / "catalog.json").read_text(encoding="utf-8")) if (ROOT / "health" / "catalog.json").exists() else {}
        out.append("- 김박사 건강몰: " + (" · ".join(f"{k} {v['clicks']}클릭/{v['commission']}원" for k, v in hb.items()) or "쿠팡 클릭 0")
                   + f" (합계 {sum(v['clicks'] for v in hb.values())}클릭/{sum(v['commission'] for v in hb.values())}원)"
                   + f" | 진열 성분 {len(hc.get('products') or {})} · 베스트 {len(hc.get('best') or [])} · 갱신 {hc.get('updated') or '없음'}")
    shop = ROOT / "social" / "youtube" / "shop.json"
    if shop.exists():
        log = json.loads(shop.read_text(encoding="utf-8"))
        since = (today - dt.timedelta(days=60)).isoformat()
        cnt = {}
        for e in log:
            if e.get("date", "") >= since:
                cnt[e["cat"]] = cnt.get(e["cat"], 0) + 1
        out.append("- 유튜브 쿠팡 영상 수(60일): " + " · ".join(f"{k} {v}" for k, v in sorted(cnt.items())) + f" · 최근 {log[-1]['date']} {log[-1]['cat']}({log[-1].get('why')})" if log else "")
    gs = ROOT / "social" / "blogger" / "guides" / "state.json"
    if gs.exists():
        st = json.loads(gs.read_text(encoding="utf-8"))
        out.append("- 블로거 비교 글: " + " · ".join(f"{k} {'게시' if v.get('url') else str(len(v.get('items', {}))) + '개 채움'}" for k, v in st.items()))

    # 건강몰 유입·클릭(2026-11-20): hm_* 표(본 사이트 통계·김박사 몰 mall_ev 와 분리) → 채널 다각화·전환·막힌 페이지
    import mall_insights
    out += ["", "## 건강몰 유입·클릭(7일)"] + mall_insights.lines(a.get("hmall"))
    # 애드센스 재신청 기준(예약 작업 '애드센스 재신청 준비 점검'의 기준과 같다)
    nrep = public_reports()
    crit = [
        ("공개 6주(11-22 이후)", today >= dt.date(2026, 11, 22), str(today)),
        ("공개 리포트 150+", nrep >= 150, str(nrep)),
        ("하루 세션 100+", s_now / max(1, a.get("days", 7)) >= 100, f"{s_now / max(1, a.get('days', 7)):.0f}"),
        ("검색 세션 7일 20+", srch >= 20, str(srch)),
        ("정책 페이지·noindex", all((ROOT / "content" / "pages" / f"{x}.md").exists() for x in ("editorial", "updates", "about", "privacy", "contact"))
         and "noindex" in (ROOT / "templates" / "ticker.html").read_text(encoding="utf-8"), "파일 확인"),
    ]
    ok = sum(1 for _, v, _ in crit if v)
    out += ["", f"## 애드센스 재신청: {'준비됨' if ok == 5 else '준비 중'} {ok}/5 — " + " · ".join(f"{n} {'○' if v else '×'}({x})" for n, v, x in crit)]

    # 광고 UX 가드(2026-11-22 운영자 "유저경험 해치지 않는 한도에서 광고 꽉꽉"): ads.yaml guard의 기준(변경 전 7일)과 지금 7일을 비교.
    # 판정일 뒤 리포트 평균 체류·스크롤 깊이·페이지/세션 가운데 하나라도 10% 넘게 나빠지면 '마지막 추가분 되돌리기'를 이상 신호로 올린다
    gw = guard_lines(a, today)
    out += ["", "## 광고 UX 가드: " + gw[0]] + gw[1:]

    warn = []
    if gw[0].startswith("되돌릴 것"):
        warn.append("광고 UX 가드: " + gw[0])
    if ad and (today - dt.date.fromisoformat(max(x["day"] for x in ad))).days > 2:
        warn.append("애드핏 기록이 이틀 넘게 끊김(전달 앱 확인)")
    if cp and (today - dt.date.fromisoformat(cp[-1]["day"])).days > 3:
        warn.append(f"쿠팡 클릭이 {cp[-1]['day']} 뒤로 없음(쿠팡 보고서는 클릭 있는 날만 줌 — coupang-stats 실행이 성공이면 정상)")
    if a.get("updReq"):
        warn.append(f"업데이트 요청 {len(a['updReq'])}종목")
    out += ["", "## 이상 신호: " + ("; ".join(warn) if warn else "없음")]
    print("\n".join(x for x in out if x is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
