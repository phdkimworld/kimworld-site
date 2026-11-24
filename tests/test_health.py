#!/usr/bin/env python3
"""김박사 건강몰 빌드 검사(쿠팡 API 없이 가짜 데이터로)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import health_build as hb  # noqa: E402


def main() -> int:
    c = hb.cfg()
    assert hb.check(c) == [], hb.check(c)
    # 금지 낱말 검사가 실제로 잡는지
    bad = json.loads(json.dumps(c))
    bad["guides"][0]["intro"] += " 이 제품은 치료 효과가 있다"
    assert any("치료" in e for e in hb.check(bad))
    # 질병·의약품 낱말이 든 상품 이름은 빠진다
    items = [{"name": "오메가3 1000 고혈압 예방", "url": "https://link.coupang.com/a/x"},
             {"name": "오메가3 180캡슐", "url": "https://link.coupang.com/a/y", "price": 19900},
             {"name": "오메가3 180캡슐", "url": "https://link.coupang.com/a/z"}]
    kept = hb.clean(items, c["drop_words"], c["guides"][0]["match"])
    assert hb.clean([{"name": "코카콜라 제로", "url": "https://link.coupang.com/a/q"}], c["drop_words"], c["guides"][0]["match"]) == []
    assert [p["url"] for p in kept] == ["https://link.coupang.com/a/y"], kept
    # 검색 순서: 한 번도 안 받은 것 → 오래된 것
    cat = {"at": {f"{g['slug']}|{k}": "2026-11-19 10:00" for g, k in hb.pairs(c)}}
    cat["at"]["lutein|루테인"] = "2026-11-01 00:00"
    del cat["at"]["coq10|코큐텐"]
    assert [(g["slug"], k) for g, k in hb.plan(c, cat)][:2] == [("coq10", "코큐텐"), ("lutein", "루테인")]
    # 한 번에 같은 성분 두 번 안 함
    cat2 = {"at": {f"{g['slug']}|{k}": "2026-11-19 10:00" for g, k in hb.pairs(c)}}
    cat2["at"]["omega3|오메가3"] = cat2["at"]["omega3|rTG 오메가3"] = "2026-11-01 00:00"
    assert [g["slug"] for g, _ in hb.plan(c, cat2)][0] == "omega3" and len({g["slug"] for g, _ in hb.plan(c, cat2)}) == len(hb.plan(c, cat2))
    # 누적: 새 것이 앞, 14일 지난 것은 빠짐, 중복 이름 하나
    old = [{"name": "A", "url": "u", "seen": "2026-11-01"}, {"name": "B", "url": "u", "seen": "2026-11-18"}]
    m = hb.merge([{"name": "C", "url": "u"}, {"name": "B", "url": "u"}], old, "2026-11-20", 24, 14)
    assert [x["name"] for x in m] == ["C", "B"] and m[1]["seen"] == "2026-11-20"
    # 빌드: 상품 링크는 sponsored, 대가성 문구, noindex는 best만, sitemap에 best 없음
    cat = {"updated": "2026-11-19 12:00", "best": [{"name": "홍삼정", "url": "https://link.coupang.com/a/b", "price": 30000}],
           "products": {"omega3": kept}, "at": {"omega3": "2026-11-19 12:00"}}
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        assert hb.build(c, cat, out) == 0
        g = (out / "guide/omega3/index.html").read_text(encoding="utf-8")
        assert 'rel="sponsored nofollow noopener"' in g and hb.DISCLOSURE in g
        assert '<link rel="canonical" href="https://health.drkimworld.com/guide/omega3/">' in g
        assert "noindex" not in g and '"@type": "Article"' in g
        assert "noindex" in (out / "best/index.html").read_text(encoding="utf-8")
        # 애드센스: 색인 페이지에만 계정 코드, noindex 페이지에는 없음, ads.txt
        assert "pagead2.googlesyndication.com" in g and "pagead2.googlesyndication.com" not in (out / "best/index.html").read_text(encoding="utf-8")
        assert (out / "ads.txt").read_text().startswith("google.com, pub-")
        # 몰 유입 추적: 모든 페이지에 건강몰 추적(site='health'), 진열 줄에 자리 이름(data-sub)
        for f in out.rglob("*.html"):
            assert "api.drkimworld.com/v1/mhit" in f.read_text(encoding="utf-8") and "SITE='health'" in f.read_text(encoding="utf-8"), f
        assert 'data-sub="g-omega3"' in g
        sm = (out / "sitemap.xml").read_text(encoding="utf-8")
        assert "/best/" not in sm and sm.count("<url>") == 3 + len(c["guides"])
        for f in out.rglob("*.html"):
            s = f.read_text(encoding="utf-8")
            assert hb.DISCLOSURE in s, f
            for w in ("완치", "특효", "효과 보장"):
                assert w not in s, (f, w)
    # 퍼널 자리: 켜면 그 가이드에 상자가 나온다
    c2 = json.loads(json.dumps(c))
    c2["funnels"] = {"guide-omega3": {"title": "t", "text": "x", "url": "https://example.com/f"}}
    with tempfile.TemporaryDirectory() as d:
        hb.build(c2, cat, Path(d))
        assert 'data-slot="guide-omega3"' in (Path(d) / "guide/omega3/index.html").read_text(encoding="utf-8")
        assert 'data-slot' not in (Path(d) / "guide/lutein/index.html").read_text(encoding="utf-8")
    # 시청자 프로필(2026-11-24): 가이드마다 기본 프로필 상자는 보이고 나머지는 숨김, 진열 정렬 버튼, 추적에 프로필 표(aud·profile_map), 쿠팡 하위 ID에 p<코드>
    with tempfile.TemporaryDirectory() as d:
        hb.build(c, cat, Path(d))
        g = (Path(d) / "guide/omega3/index.html").read_text(encoding="utf-8")
        assert '<section class="pf" data-pf="blood" data-def="1">' in g and '<section class="pf" data-pf="eye" hidden>' in g
        assert 'class="pm"' in g and "이런 조건의 제품" in g
        assert 'class="sortbar"' in g and 'data-per=' in g and 'id="cautions"' in g and 'id="fn"' in g
        assert '"dryeye-omega3":"eye"' in g and "'p'+PFX" in g and "hmEv" in g
        assert g.index('class="pf"') < g.index('id="items"'), "프로필 상자는 상품 진열보다 위(상품 옆에 질병 문장 없음)"
    bad = json.loads(json.dumps(c))
    bad["profile_map"] = {"x-long": "nope"}
    bad["profiles"][0]["steps"] = ["치료에 좋습니다"]
    errs = hb.check(bad)
    assert any("profile_map" in e for e in errs) and any("금지 낱말" in e for e in errs), errs
    print("health ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
