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
    print("health ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
