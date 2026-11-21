"""건강몰 유입·클릭 인사이트(김박사 몰은 scripts/mall_stats.py·mall_ev 가 맡는다. 2026-11-20 운영자 "몰 페이지 트래픽좀 다각화해서 체계적으로 잘 추적해서 저장해놓고 인사이트로 활용해").

입력: analytics.json 의 hmall 칸(워커 mallStats·hm_* 표: totals·prev·channels·sources·landings·campaigns·clicks·pages, 7일).
출력: digest 에 넣을 줄 목록. LLM 없이 규칙으로만 — 숫자는 저장된 합계에서만 나온다.
규칙(판정 기준을 바꾸면 여기와 AGENTS.md '몰 유입 추적'을 같이 고친다):
- 다각화: 한 채널이 세션의 70% 이상이면 '쏠림', 목표 채널(검색·유튜브·SNS·메신저·내부) 중 세션 0인 채널은 '빈 채널'
- 전환: 채널·랜딩별 쿠팡 클릭률 = 쿠팡 클릭 / 세션. 세션 10 이상만 비교
- 막힌 페이지: 페이지뷰 20 이상인데 쿠팡 클릭 0
- 할 일: 빈 채널·쏠림·막힌 페이지에서 한 줄씩(최대 3)
"""
from __future__ import annotations

NAMES = {"mall": "김박사 몰", "health": "건강몰"}
CH_KO = {"search": "검색", "ai": "AI", "youtube": "유튜브", "social": "SNS", "messenger": "메신저", "community": "커뮤니티",
         "referral": "다른 사이트", "email": "메일", "direct": "직접", "internal": "김박사 월드 내부"}
TARGET = ("search", "youtube", "social", "messenger", "internal")
TODO = {
    "search": "검색 0 → 서치 콘솔·서치어드바이저 등록 확인, 가이드 제목에 검색어(\"○○ 고르는 법\") 점검",
    "youtube": "유튜브 0 → 고정댓글 첫 세 줄에 몰 주소(utm_source=youtube&utm_medium=pinned)",
    "social": "SNS 0 → Threads 끝 댓글·인스타 프로필에 몰 주소(utm_source=threads|instagram)",
    "messenger": "메신저 0 → 텔레그램 새 리포트 🛒 줄 utm_source=telegram 확인",
    "internal": "내부 0 → 본 사이트 하단 메뉴·리포트 끝에서 몰로 가는 링크(utm_source=site) 확인",
}


def _rate(c, s):
    return f"{100 * c / s:.0f}%" if s else "-"


def lines(m: dict | None) -> list[str]:
    if not m:
        return ["- 건강몰 유입 기록 없음(워커 mallStats 응답 없음)"]
    out: list[str] = []
    prev = {x["site"]: x for x in m.get("prev") or []}
    todo: list[str] = []
    for t in m.get("totals") or []:
        site, sess, clicks = t["site"], t.get("sess") or 0, t.get("clicks") or 0
        p = prev.get(site) or {}
        chg = f" (전주 {p.get('sess') or 0})" if p else ""
        out.append(f"- {NAMES.get(site, site)}: 세션 {sess}{chg} · 참여 {_rate(t.get('engaged') or 0, sess)} · 2페이지+ {_rate(t.get('deep') or 0, sess)} · 쿠팡 클릭 {clicks}(세션당 {_rate(clicks, sess)})")
        chs = [x for x in m.get("channels") or [] if x["site"] == site]
        if chs:
            out.append("  - 채널: " + " · ".join(f"{CH_KO.get(x['ch'], x['ch'])} {x['sess']}({_rate(x.get('clicks') or 0, x['sess'])} 클릭)" for x in chs[:6]))
            top = max(chs, key=lambda x: x["sess"])
            if sess >= 10 and top["sess"] / sess >= 0.7:
                out.append(f"  - 쏠림: 세션의 {100 * top['sess'] / sess:.0f}%가 {CH_KO.get(top['ch'], top['ch'])}")
                todo.append(f"{NAMES.get(site, site)} {CH_KO.get(top['ch'], top['ch'])} 쏠림 → 다른 채널 하나에 이번 주 링크 2곳 추가")
            have = {x["ch"] for x in chs if x["sess"]}
            empty = [c for c in TARGET if c not in have]
            if empty:
                out.append("  - 빈 채널: " + " · ".join(CH_KO[c] for c in empty))
                todo += [f"{NAMES.get(site, site)} {TODO[c]}" for c in empty[:1]]
            good = [x for x in chs if x["sess"] >= 10]
            if len(good) >= 2:
                best = max(good, key=lambda x: (x.get("clicks") or 0) / x["sess"])
                out.append(f"  - 클릭률 1위 채널: {CH_KO.get(best['ch'], best['ch'])} {_rate(best.get('clicks') or 0, best['sess'])}")
        lps = [x for x in m.get("landings") or [] if x["site"] == site][:3]
        if lps:
            out.append("  - 랜딩 상위: " + " · ".join(f"{x['lp']} {x['sess']}({_rate(x.get('clicks') or 0, x['sess'])})" for x in lps))
        camps = [x for x in m.get("campaigns") or [] if x["site"] == site][:3]
        if camps:
            out.append("  - 캠페인: " + " · ".join(f"{x['src']}/{x['camp']} {x['sess']}" for x in camps))
        blocks = [x for x in m.get("clicks") or [] if x["site"] == site and x["kind"] == "coupang"][:4]
        if blocks:
            out.append("  - 클릭 많은 자리: " + " · ".join(f"{x['sub']} {x['n']}" for x in blocks))
        stuck = [x for x in m.get("pages") or [] if x["site"] == site and (x.get("pv") or 0) >= 20 and not x.get("coupang")][:3]
        if stuck:
            out.append("  - 클릭 없는 페이지(PV 20+): " + " · ".join(f"{x['path']} {x['pv']}" for x in stuck))
            todo.append(f"{NAMES.get(site, site)} {stuck[0]['path']}: 상품 줄을 본문 위쪽으로 올리거나 진열 교체")
    if not out:
        return ["- 건강몰 방문 기록 아직 없음(2026-11-20 추적 시작)"]
    if todo:
        out.append("- 이번 주 할 일: " + " / ".join(todo[:3]))
    return out
