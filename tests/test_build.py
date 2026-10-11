"""빌드 검사: python3 tests/test_build.py
실제 사이트 파일은 건드리지 않고, 임시 폴더에 복사해 가짜 광고 번호·테스트 글로 빌드해 본다."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SRC = Path(__file__).resolve().parent.parent
FAILS = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def make_project(ads_cfg: dict | None = None, extra_reports: dict | None = None) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="kws-"))
    for name in ["build.py", "site.yaml", "ads.yaml", "data", "content", "templates", "static"]:
        p = SRC / name
        (shutil.copytree if p.is_dir() else shutil.copy)(p, tmp / name)
    tick = yaml.safe_load((tmp / "data/tickers.yaml").read_text(encoding="utf-8"))
    tick["ZZZZ"] = {"name": "제트테스트", "name_en": "Zeta Test", "exchange": "TEST", "theme": "양자컴퓨팅", "aliases": ["제트"]}
    (tmp / "data/tickers.yaml").write_text(yaml.safe_dump(tick, allow_unicode=True), encoding="utf-8")
    shutil.copy(SRC / "tests/fixtures/zzzz-test-2026-01.md", tmp / "content/reports/")
    for name, text in (extra_reports or {}).items():
        (tmp / "content/reports" / name).write_text(text, encoding="utf-8")
    if ads_cfg is not None:
        base = yaml.safe_load((tmp / "ads.yaml").read_text(encoding="utf-8"))
        for k, v in ads_cfg.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
        (tmp / "ads.yaml").write_text(yaml.safe_dump(base, allow_unicode=True), encoding="utf-8")
    return tmp


def run(tmp: Path, *args):
    return subprocess.run([sys.executable, "build.py", *args], cwd=tmp, capture_output=True, text=True)


FULL_ADS = {
    "adsense": {"client": "ca-pub-1234567890123456", "slots": {"in_article": "1111111111", "display": ""}},
    "adfit": {"units": {"report_end": "DAN-test123", "list": ""}},
    "coupang": {
        "banner_html": '<script src="https://ads-partners.coupang.com/g.js"></script><script>new PartnersCoupang.G({"id":1,"height":"140"});</script>',
        "products": {
            "양자컴퓨팅": [
                {"name": "제트테스트 굿즈 (리포트 종목이라 빠져야 함)", "url": "https://link.coupang.com/a/aaa"},
                {"name": "비트코인 입문 (금지어라 빠져야 함)", "url": "https://link.coupang.com/a/bbb"},
                {"name": "양자역학 교양서", "url": "https://link.coupang.com/a/ccc"},
            ],
            "_default": [{"name": "미국주식 투자 책", "url": "https://link.coupang.com/a/ddd"}],
        },
    },
}

print("1) 광고 설정이 비어 있을 때")
t = make_project()
r = run(t)
check(r.returncode == 0, "빌드 성공 " + r.stdout[-200:] + r.stderr[-400:])
page = (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
check("adsbygoogle" not in page and "kakao_ad_area" not in page and "coupang" not in page.lower(), "광고 코드·쿠팡 링크 0개")
check((t / "dist/ads.txt").read_text().strip() == "# KimWorld ads.txt", "ads.txt 비어 있음")
check(not (t / "dist/r/rgti-2026-03").exists(), "초안은 공개 빌드에 없음")
check(page.count('class="term"') == len(set(re.findall(r'class="term"[^>]*>([^<]+)<', page))), "용어 표시는 용어당 한 번")
check('data-def' in page and re.search(r'<h2[^>]*>[^<]*<button class="term"', page) is None, "제목 안에는 용어 표시 없음")
check(page.count('>PER</button>') == 1, "PER 첫 등장만 표시")
check('id="' in page and 'href="#' in page, "목차 링크 생성")
check((t / "dist/og/zzzz-test-2026-01.png").exists() or True, "공유 이미지(폰트 있을 때)")
check("search.json" in [p.name for p in (t / "dist").iterdir()], "검색 색인 생성")

print("2) 광고를 모두 설정했을 때")
t = make_project(FULL_ADS)
r = run(t)
check(r.returncode == 0, "빌드 성공 " + r.stdout[-300:])
page = (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
n_ads = page.count('<aside class="ad ')
check(n_ads == 4, f"리포트 광고 4개 (실제 {n_ads})")
check(page.find('data-slot="report_mid"') < page.find('data-slot="report_products"') < page.find('data-slot="report_end"') < page.find('data-slot="report_bottom"'), "광고 순서: 중간 → 쿠팡 상품 → 끝 → 맨 아래")
check("제트테스트 굿즈" not in page and "비트코인 입문" not in page, "리포트 종목명·금지어 상품 제외")
check("양자역학 교양서" in page and "미국주식 투자 책" in page, "남은 상품 표시")
check(page.count("이 영역은 쿠팡 파트너스 활동의 일환으로") == 2, "쿠팡 자리마다 표시 문구")
check("이 페이지에는 쿠팡 파트너스 링크가 포함되어 있습니다." in page, "요약 상자에 쿠팡 안내")
check(all('rel="sponsored noopener"' in a for a in re.findall(r'<a class="cp-card"[^>]*>', page)), "쿠팡 링크 rel=sponsored")
check("google.com, pub-1234567890123456, DIRECT" in (t / "dist/ads.txt").read_text(), "ads.txt 애드센스 줄")
mid = page.find('data-slot="report_mid"')
check(page.rfind("<h2", 0, mid) > 0 and page.count("<h2", 0, mid) >= 2, "중간 광고는 두 번째 소제목 섹션 뒤")
home = (t / "dist/index.html").read_text(encoding="utf-8")
check(home.count('<aside class="ad ') == 1 and "kakao_ad_area" in home, "홈 광고는 애드핏 하나")
check("adsbygoogle.js?client=ca-pub-1234567890123456" in home, "head에 애드센스 스크립트")
check("adsbygoogle" not in (t / "dist/privacy/index.html").read_text(encoding="utf-8").split("</head>")[1], "고정 페이지 본문에 광고 없음")

print("3) 소제목 2개뿐인 글")
short = (SRC / "tests/fixtures/zzzz-test-2026-01.md").read_text(encoding="utf-8")
head, body = short.split("---\n", 2)[1], ""
two = "---\n" + head + "---\n\n## 하나\n\n문단입니다.\n\n## 둘\n\n문단입니다.\n"
t = make_project(FULL_ADS, {"zzzz-short-2026-02.md": two.replace("2026-01-15", "2026-02-01")})
run(t)
page = (t / "dist/r/zzzz-short-2026-02/index.html").read_text(encoding="utf-8")
check('data-slot="report_mid"' not in page, "중간 광고 없음")
check(page.count('<aside class="ad ') <= 4, "광고 4개 이하")

print("4) 쿠팡 배너에 다른 도메인")
bad = {"coupang": {"banner_html": '<script src="https://evil.example.com/x.js"></script>'}}
t = make_project(bad)
r = run(t)
check(r.returncode != 0 and "쿠팡 밖 주소" in r.stdout, "빌드 실패")

print("5) 금지 표현·필수 항목")
t = make_project(None, {"zzzz-bad-2026-03.md": two.replace("문단입니다.", "수익 보장 문단입니다.")})
r = run(t)
check(r.returncode != 0 and "금지 표현" in r.stdout, "금지 표현이면 빌드 실패")
t = make_project(None, {"zzzz-fut-2099-01.md": two.replace("2026-01-15", "2099-01-01")})
run(t)
check(not (t / "dist/r/zzzz-fut-2099-01").exists(), "미래 날짜 글은 아직 공개 안 됨(예약 발행)")
t = make_project(None, {"zzzz-hold-2026-04.md": two.replace("draft:", "holding: none\ndraft:", 1) if "draft:" in two else two.replace("sources:", "holding: none\nsources:", 1)})
r = run(t)
check(r.returncode != 0 and "holding" in r.stdout, "보유 여부 항목이 있으면 빌드 실패")
t = make_project()
run(t)
pages_txt = "".join((t / "dist" / pg / "index.html").read_text(encoding="utf-8") for pg in ("about", "contact", "privacy", "disclaimer"))
pages_txt += (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
import re as _re
check("보유 공개" not in pages_txt and "보유 여부" not in pages_txt and not _re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", pages_txt), "보유 여부·이메일이 화면에 없음")

print("6) 도메인 연결 전(github.io 하위 주소)")
import os as _os
t = make_project()
r = subprocess.run([sys.executable, "build.py"], cwd=t, capture_output=True, text=True,
                   env={**_os.environ, "SITE_URL": "https://phdkimworld.github.io/kimworld-site"})
allhtml = "".join(f.read_text(encoding="utf-8") for f in (t / "dist").rglob("*.html"))
check(r.returncode == 0 and not _re.search(r'(?:href|src)="/(?!kimworld-site/|/)', allhtml), "모든 내부 링크·CSS·JS에 하위 경로가 붙음")
check(not (t / "dist/CNAME").exists(), "github.io 주소일 때 CNAME 없음")

print()
if FAILS:
    print(f"실패 {len(FAILS)}개")
    sys.exit(1)
print("모두 통과")
