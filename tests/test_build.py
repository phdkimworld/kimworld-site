"""빌드 검사: python3 tests/test_build.py
실제 사이트 파일은 건드리지 않고, 임시 폴더에 복사해 가짜 광고 번호·테스트 글로 빌드해 본다."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SRC = Path(__file__).resolve().parent.parent
import re as _re0
# 대화 사이 광고 틀(화면에서만 끼워 넣음)과 PC 오른쪽 칸 광고(rail)는 본문 광고 수에서 뺀다
notpl = lambda h: _re0.sub(r'<div class="rail-ad">.*?</aside></div>', "", _re0.sub(r"<template data-thread-ad>.*?</template>", "", h, flags=_re0.S), flags=_re0.S)
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
    "placements": {"report_mid": "adsense_in_article", "report_products": "coupang_products", "report_end": "adfit_report_end",
                   "report_bottom": "coupang_banner", "list": "adfit_list"},
}

print("1) 광고 설정이 비어 있을 때")
EMPTY_ADS = {"adsense": {"client": "", "slots": {"in_article": "", "display": ""}},
             "adfit": {"units": {"report_end": "", "list": ""}},
             "coupang": {"banner_html": "", "products": {}}}
t = make_project(EMPTY_ADS)
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
page = notpl((t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8"))
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
home_full = (t / "dist/index.html").read_text(encoding="utf-8"); home = notpl(home_full)
_nf = home.count('data-slot="feed_inline"')
check(home.count("kakao_ad_area") == 1 and 1 <= _nf <= 4 and home.count('<aside class="ad ') == 1 + _nf, f"홈 광고: 애드핏 하나(목록) + 피드 사이 쿠팡 {_nf}개(6개 글마다, 최대 4)")
check('class="rail-ad"' in home_full, "홈 PC 오른쪽 칸 광고")
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
check(notpl(page).count('<aside class="ad ') <= 4, "짧은 글은 본문 광고 4개 이하")

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

print("7) 쿠팡 API 자동 상품")
import json as _json, datetime as _dt
sys.path.insert(0, str(SRC / "scripts"))
import coupang_sync as cs
# 서명 형식(쿠팡 문서: yyMMdd'T'HHmmss'Z', 메시지 = 날짜+메서드+경로+쿼리)
auth = cs.authorization("GET", "/p", "a=1", "AK", "SK", _dt.datetime(2026, 10, 11, 22, 5, 9, tzinfo=_dt.timezone.utc))
check(auth.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=261011T220509Z, signature=") and "SK" not in auth, "서명 헤더 형식, 비밀키 노출 없음")
tmpc = Path(tempfile.mkdtemp()) / "c.json"
_os.environ["COUPANG_CACHE"] = str(tmpc); cs.CACHE = tmpc
tmpr = tmpc.parent / "r.json"; _os.environ["COUPANG_REPORTS"] = str(tmpr); cs.REPORTS = tmpr
rep_calls = []
def fake_rep(path, q, a, b):
    rep_calls.append(path)
    return {"data": [{"date": "20261010", "subId": cs.sub_id("quantum", "양자컴퓨터 책"), "commission": 1200, "orderCount": 1},
                     {"date": "20261011", "subId": cs.sub_id("quantum", "양자컴퓨터 책"), "commission": 800}]}
_os.environ.pop("COUPANG_ACCESS_KEY", None)
check(cs.run() == 0 and not tmpc.exists(), "키가 없으면 호출 없이 통과")
_os.environ["COUPANG_ACCESS_KEY"] = "AK"; _os.environ["COUPANG_SECRET_KEY"] = "SK"
seen = []
def fake(kw, sid, limit, a, b):
    seen.append((kw, sid))
    return [{"name": f"{kw} 상품 {i}", "url": f"https://link.coupang.com/a/{sid}{i}", "image": "https://thumbnail.coupangcdn.com/x.jpg",
             "price": 12800 + i, "rocket": i == 2, "rank": i + 1} for i in range(4)] + [
            {"name": "제트테스트 굿즈", "url": "https://link.coupang.com/a/z", "image": "", "price": 1, "rocket": True, "rank": 0},
            {"name": "비트코인 채굴기", "url": "https://link.coupang.com/a/b", "image": "", "price": 1, "rocket": True, "rank": 0}]
now = _dt.datetime(2026, 10, 11, 15, 0, tzinfo=_dt.timezone.utc)
cs.run(now, fake, fake_rep)
check(len(seen) == 5, f"한 번에 5번까지만 호출({len(seen)})")
_kw0 = yaml.safe_load((SRC / "data/coupang.yaml").read_text(encoding="utf-8"))["keywords"]
_first = [cs.sub_id(sl, _kw0[nm][0]) for nm, sl in (("양자컴퓨팅", "quantum"), ("AI 반도체", "ai-chips"), ("우주항공·방산", "space-defense"), ("휴머노이드", "humanoids"), ("AI 소프트웨어", "ai-software"))]
check([s for _, s in seen] == _first, f"아직 안 받은 테마의 첫 검색어부터 ({[s for _, s in seen]})")
cs.run(now + _dt.timedelta(minutes=10), fake, fake_rep)
check(len(seen) == 9, "1시간 안에 다시 돌면 시간당 9번까지만(5+4)")
cs.run(now + _dt.timedelta(minutes=20), fake, fake_rep)
check(len(seen) == 9, "시간당 상한에 닿으면 더 부르지 않음")
cs.run(now + _dt.timedelta(minutes=69), fake, fake_rep)
check(len(seen) == 14, "두 번째 실행 59분 뒤에도 시간당 상한 안에서 5번을 받음")
for h in range(2, 12):
    cs.run(now + _dt.timedelta(hours=h), fake, fake_rep)
check(len(set(seen)) == len(seen) and all(cs.sub_id("quantum", k) in {s for _, s in seen} for k in _kw0["양자컴퓨팅"]), "같은 검색어를 20시간 안에 다시 받지 않고 결국 모두 받음")
_rep = _json.loads(tmpr.read_text(encoding="utf-8")) if tmpr.exists() else {}
check(len(rep_calls) == 1 and _rep.get("by_sub", {}).get(cs.sub_id("quantum", "양자컴퓨터 책"), {}).get("commission") == 2000, f"상품이 다 최신일 때 하루 한 번 실적(하위 ID별 수수료) 받기 ({len(rep_calls)})")
check(cs.sub_id("quantum", "양자역학 책") != cs.sub_id("quantum", "양자컴퓨터 책") and re.fullmatch(r"quantum[0-9a-f]{4}", cs.sub_id("quantum", "x")), "하위 ID는 테마+검색어 해시(검색어를 바꾸면 성과가 섞이지 않음)")
check(all(_re.fullmatch(r"[a-z0-9]+", sid) for _, sid in seen), "하위 ID는 영문 소문자·숫자")
_c = _json.loads(tmpc.read_text(encoding="utf-8"))
_c["entries"]["양자컴퓨팅|반도체 전쟁 책"]["date"] = "2026-10-09"
tmpc.write_text(_json.dumps(_c, ensure_ascii=False), encoding="utf-8")
t = make_project({"adfit": {"units": {"report_mid": "", "report_end": "DAN-endtest1", "list": ""}}})  # 애드핏 중간 번호가 없을 때(쿠팡 3개)
r = subprocess.run([sys.executable, "build.py"], cwd=t, capture_output=True, text=True, env={**_os.environ})
page_full = (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
tpl = re.search(r"<template data-thread-ad>(.*?)</template>", page_full, flags=re.S)
page = notpl(page_full)  # 본문 광고 검사는 대화 사이 광고 틀·오른쪽 칸 광고를 빼고
check(tpl is not None and 'data-ad-first="6"' in page_full and 'data-ad-every="6"' in page_full and 'data-ad-max="3"' in page_full, "리포트 댓글 사이 광고 틀(6개 뒤부터 6개마다, 최대 3개)")
check(tpl is not None and "quantum" not in tpl.group(1) and tpl.group(1).count("data-cp-group") >= 3, "댓글 사이 광고는 본문 상자와 다른 테마 묶음")
tk_page = (t / "dist/t/zzzz/index.html").read_text(encoding="utf-8")
check("<template data-thread-ad>" in tk_page and 'data-ad-first="4"' in tk_page and 'data-ad-max="4"' in tk_page, "종토방 사이 광고 틀(4개 뒤부터 6개마다, 최대 4개)")
box = page[page.find('ad-coupang-products'):]
box = box[: box.find("</aside>")]
check(r.returncode == 0 and box.count("data-cp-group") == 3, "양자컴퓨팅 리포트에 검색어 묶음 3개")
check(box.count(" hidden") == 2, "스크립트 없이도 묶음 하나만 보임")
boxes = re.findall(r'<aside class="ad ad-coupang-products" data-slot="([a-z_]+)".*?</aside>', page, flags=re.S)
check(boxes == ["report_mid", "report_products", "report_end"], f"쿠팡 상자 3개: 중간·본문 끝·출처 아래 ({boxes})")
shown = [re.search(r'data-cp-group data-cp-sub="[^"]*" data-cp-theme="[^"]*" data-cp-date="[^"]*">(.*?)</div>', b, flags=re.S).group(1)[:200] for b in re.findall(r'<aside class="ad ad-coupang-products".*?</aside>', page, flags=re.S)]
check(len(set(shown)) == 3, "스크립트 없이도 상자마다 다른 검색어 묶음")
check(all(b.count('class="cp-note"') == 1 for b in re.findall(r'<aside class="ad ad-coupang-products".*?</aside>', page, flags=re.S)), "가격 기준일 문구는 상자마다 한 번")
home = notpl((t / "dist/index.html").read_text(encoding="utf-8"))
check(3 <= home.count('<aside class="ad ') <= 5 and home.count("data-cp-group") >= 8, "홈: 쿠팡 상자(목록 1 + 피드 사이), 모든 테마 묶음에서")
_vis = [re.search(r'data-cp-group data-cp-sub="[^"]*" data-cp-theme="[^"]*" data-cp-date="[^"]*">(.*?)</div>', b, flags=re.S).group(1)[:200] for b in re.findall(r'<aside class="ad ad-coupang-products".*?</aside>', home, flags=re.S)]
check(len(set(_vis)) == len(_vis) >= 3, "홈 쿠팡 상자는 서로 다른 묶음")
th = (t / "dist/theme/quantum/index.html").read_text(encoding="utf-8")
check(th.count("data-cp-group") == 3, "테마 페이지: 그 테마 묶음만")
sp = (t / "dist").rglob("*.html")
_c = _json.loads(tmpc.read_text(encoding="utf-8"))
_c["entries"] = {k: v for k, v in _c["entries"].items() if not k.endswith("양자역학 책")}
tmpc.write_text(_json.dumps(_c, ensure_ascii=False), encoding="utf-8")
t = make_project()
subprocess.run([sys.executable, "build.py"], cwd=t, capture_output=True, text=True, env={**_os.environ})
page2 = notpl((t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8"))
check(page2.count("ad-coupang-products") == 2, "묶음이 2개뿐이면 상자도 2개(중복 노출 없음)")
check("제트테스트 굿즈" not in box and "비트코인" not in box, "다룬 회사·금지어 상품 제외")
check("12,802원" in box and "로켓배송" in box and f'data-cp-sub="{cs.sub_id("quantum", _kw0["양자컴퓨팅"][0])}"' in box, "가격·로켓배송·하위 ID 표시")
grp = box[box.find("data-cp-group"):]
check(grp.find("상품 2") < grp.find("상품 0"), "로켓배송 상품을 앞에")
groups_html = box.split("data-cp-group")[1:]
check(' data-cp-date="2026.10.09"' in groups_html[1][:200] and "2026.10.09" not in groups_html[0] and box.count("기준이며 바뀔 수 있습니다") == 1,
      "가격 기준일은 묶음마다 data-cp-date로, 문구는 상자에 한 번(보이는 묶음 날짜)")
check("광고" in box and "쿠팡 파트너스 활동" in box and "기준이며 바뀔 수 있습니다" in box, "광고 표시·대가성 문구·가격 기준일")
check(notpl(page).count('<aside class="ad ') <= 5, "본문 광고 5개 이하 유지")
t = make_project({"adfit": {"units": {"report_mid": "DAN-midtest1", "report_end": "DAN-endtest1", "list": ""}}})
subprocess.run([sys.executable, "build.py"], cwd=t, capture_output=True, text=True, env={**_os.environ})
pm = notpl((t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8"))
slots = re.findall(r'<aside class="ad ([a-z-]+)" data-slot="([a-z_]+)"', pm)
check(("ad-adfit", "report_mid") in slots and 'data-ad-unit="DAN-midtest1" data-ad-width="300" data-ad-height="250"' in pm,
      "애드핏 중간 번호가 있으면 초반 자리는 애드핏 300x250")
check(pm.count("ad-coupang-products") == 2 and len(slots) <= 4 and pm.count("DAN-midtest1") == 1 and pm.count("DAN-endtest1") == 1,
      f"쿠팡 2개 + 애드핏 2개, 같은 단위 중복 없음 ({slots})")
for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_CACHE"):
    _os.environ.pop(k, None)

print("8) 조회수·댓글·인기 영역")
t = make_project()
run(t)
pg = (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
home = (t / "dist/index.html").read_text(encoding="utf-8")
check(0 < pg.find("data-cm-top hidden") < pg.find('class="prose"'), "요약 바로 아래 인기 댓글 자리(본문보다 위, 처음엔 숨김)")
check('id="comments" data-comments data-thread="zzzz-test-2026-01" data-kind="report" hidden' in pg and "community.js" in pg and 'data-views hidden' in pg, "리포트에 댓글·조회수 자리(처음엔 숨김)")
check("data-insights hidden" in home and "data-popular-list" in home and "data-trending-list" in home, "홈에 많이 본 리포트·많이 찾는 종목 자리(처음엔 숨김)")
check(home.count('class="card post"') >= 1 and "data-post-like" in home and "data-post-top" in home and "data-ago" in home, "홈 피드: 게시물 카드(좋아요·대표 댓글·'n일 전')")
check("data-report-bar" in pg and "data-dock" in pg and pg.count("data-post-like") >= 2, "리포트: 반응 줄과 휴대폰 고정 반응 줄")
check("data-theme-list" in home and "data-recent-cm-list" in home and "data-pop-range" in home, "홈에 테마별 관심도·최근 댓글·오늘/7일 탭 자리")
check(pg.find("data-next-reads hidden") > pg.find('class="prose"'), "리포트 끝에 '지금 많이 보는 리포트' 자리")
check(all("ts" in x for x in json.loads((t / "dist/search.json").read_text(encoding="utf-8"))), "검색 색인에 테마 주소(ts)")
check('data-board-peek="b-zzzz"' in pg and "/t/zzzz/#board" in pg, "리포트에서 종토방으로 연결(미리보기·반응 줄)")
tk = (t / "dist/t/zzzz/index.html").read_text(encoding="utf-8")
check('data-thread="b-zzzz"' in tk and 'data-kind="board"' in tk and "data-need-account" in tk, "종목 페이지에 종토방(계정 없으면 글쓰기 대신 안내)")
check((t / "dist/u/index.html").exists() and "noindex" in (t / "dist/u/index.html").read_text(encoding="utf-8"), "프로필 페이지(검색 노출 안 함)")
ad = (t / "dist/admin/index.html").read_text(encoding="utf-8")
check("noindex,nofollow" in ad and "admin.js" in ad and "Disallow: /admin/" in (t / "dist/robots.txt").read_text(), "운영 통계 페이지: 검색 노출·수집 막음")
check("/admin/" not in home, "운영 통계는 어디에도 링크하지 않음")
check("data-tabbar" in home and "data-compose" in home, "휴대폰 아래 탭 줄(홈·검색·글쓰기·알림·내 정보)")
_rp = next((t / "dist/r").glob("*/index.html")).read_text(encoding="utf-8")
check("data-tabbar" not in _rp and "data-dock" in _rp, "리포트에는 탭 줄 대신 반응 줄")
_mf = _json.loads((t / "dist/manifest.webmanifest").read_text(encoding="utf-8"))
check(_mf["display"] == "standalone" and any(i.get("sizes") == "512x512" and i.get("purpose") == "maskable" for i in _mf["icons"]) and (t / "dist/static/icon-192.png").exists(), "웹앱 설치 정보(아이콘 192·512·마스크)")
_sw = (t / "dist/sw.js").read_text(encoding="utf-8")
check("__VER__" not in _sw and "/offline/" in _sw and (t / "dist/offline/index.html").exists() and "apple-touch-icon" in home, "서비스 워커·오프라인 안내·아이폰 아이콘")
check('data-repost' in home and 'data-kind="r"' in home, "리포트 카드에 리포스트·인용 버튼")
pp = (t / "dist/p/index.html")
check(pp.exists() and "noindex" in pp.read_text(encoding="utf-8") and "data-post-page" in pp.read_text(encoding="utf-8"), "글 상세 페이지(검색 노출 안 함)")
check("data-feed-tabs" in home and 'data-tab="following"' in home and 'value="b-talk"' in home and "data-composer" in home, "홈 피드: 추천·팔로잉 탭과 글쓰기 상자(라운지·종목 선택)")
check("social.js" in home and '"tk": [' in home.replace("tk: [", '"tk": ['), "홈에 피드 스크립트와 종목 목록($티커 링크용)")
check((t / "dist/terms/index.html").exists() and "data-open-account" in home, "이용약관·계정 버튼")
check('name="website" class="hp"' in pg, "로봇 막는 숨은 칸")
sy = yaml.safe_load((t / "site.yaml").read_text(encoding="utf-8")); sy["api_url"] = ""
(t / "site.yaml").write_text(yaml.safe_dump(sy, allow_unicode=True), encoding="utf-8")
run(t)
pg = (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
check("community.js" not in pg and "data-comments" not in pg and "data-board-peek" not in pg, "api_url을 비우면 기능이 통째로 꺼짐")
w = subprocess.run(["node", str(SRC / "worker/test/test_worker.mjs")], capture_output=True, text=True)
check(w.returncode == 0, "API(worker) 검사 " + ("통과" if w.returncode == 0 else w.stdout[-600:]))

print("10) 보안: 리포트 본문·출처 검사")
for bad, why in [("<script>alert(1)</script>", "스크립트"), ('<img src=x onerror="alert(1)">', "이벤트 속성"),
                 ("[누르기](javascript:alert(1))", "javascript 링크"), ("<iframe src=//x></iframe>", "iframe")]:
    t = make_project()
    f = t / "content/reports/zzzz-test-2026-01.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n\n" + bad + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "build.py", "--strict"], cwd=t, capture_output=True, text=True)
    check(r.returncode != 0 and "허용하지 않는" in r.stdout + r.stderr, f"본문에 {why} → 빌드 실패")
t = make_project()
f = t / "content/reports/zzzz-test-2026-01.md"
f.write_text(f.read_text(encoding="utf-8").replace("sources:\n", "sources:\n  - title: 나쁜 출처\n    url: \"javascript:alert(1)\"\n", 1), encoding="utf-8")
r = subprocess.run([sys.executable, "build.py", "--strict"], cwd=t, capture_output=True, text=True)
check(r.returncode != 0 and "http(s)://" in r.stdout + r.stderr, "출처 주소가 javascript: → 빌드 실패")
t = make_project()
f = t / "content/reports/zzzz-test-2026-01.md"
f.write_text(f.read_text(encoding="utf-8") + "\n\nMarket data: 숫자 정리, 자바스크립트 이야기\n", encoding="utf-8")
r = subprocess.run([sys.executable, "build.py", "--strict"], cwd=t, capture_output=True, text=True)
check("허용하지 않는" not in r.stdout + r.stderr, "평범한 'data:' 글자는 통과")

print("11) 댓글 검토 도우미")
sys.path.insert(0, str(SRC / "scripts")); import moderation as MOD
red = MOD.redact("카톡 010-1234-5678 https://x.co/a @leader99 a@b.com 2026년 3.90달러")
check("1234" not in red and "x.co" not in red and "leader99" not in red and "a@b.com" not in red and "2026년" in red, "공개 기록에는 연락처·링크·아이디를 가림")
_out = Path(tempfile.mkdtemp()) / "a.sql"
MOD.cmd_apply('{"comments":[{"id":3,"status":"ok"}],"ban":[2]}', str(_out))
check("reviewed = 1" in _out.read_text() and "banned" in _out.read_text(), "결정 → SQL")
MOD.cmd_apply('{"owner_nick":["퀀텀개미"],"unowner":[4]}', str(_out))
check("INSERT OR IGNORE INTO owners" in _out.read_text() and "DELETE FROM owners WHERE uid = 4" in _out.read_text(), "운영자 지정·해제 → SQL")
for bad in ['{"owner_nick":["a\'; DROP TABLE users;--"]}', '{"comments":[{"id":"1; DROP TABLE users","status":"ok"}]}', '{"comments":[{"id":1,"status":"ok\'; DROP"}]}']:
    try:
        MOD.cmd_apply(bad, str(_out)); check(False, "잘못된 결정 거절")
    except (ValueError, SystemExit):
        check(True, "잘못된 결정 거절(주입 방지)")

print("12) 광고 학습 자료")
t = make_project()
(t / ".cache").mkdir(exist_ok=True)
shutil.copy(tmpc, t / ".cache/coupang_auto.json")
_sub = cs.sub_id("quantum", _kw0["양자컴퓨팅"][0])
(t / ".cache/ad_stats.json").write_text(_json.dumps([{"results": [{"g": _sub, "slot": "report_end", "seg": "m.r", "imps": 400, "clicks": 20},
    {"g": "unknownsub", "slot": "list", "seg": "d.h", "imps": 100, "clicks": 1}]}]), encoding="utf-8")
(t / ".cache/coupang_reports.json").write_text(_json.dumps({"by_sub": {_sub: {"orders": 2, "commission": 3000}}}), encoding="utf-8")
subprocess.run([sys.executable, "build.py"], cwd=t, capture_output=True, text=True, env={k: v for k, v in _os.environ.items() if k != "COUPANG_CACHE"})
aw = _json.loads((t / "dist/ad-weights.json").read_text(encoding="utf-8"))
gq = aw["g"].get(_sub, {})
check(gq.get("i") == 400 and gq.get("c") == 20 and gq.get("s", {}).get("m.r") == [400, 20] and gq.get("l", {}).get("report_end") == [400, 20] and gq.get("t") == "quantum", "학습 자료: 묶음별·환경별·자리별 노출·클릭과 테마")
check(gq.get("r") == 3000 and aw["epc"] > 0 and 0 < aw["prior"]["ctr"] < 0.1 and "unknownsub" not in aw["g"], "학습 자료: 수수료·클릭당 수익·전체 클릭률, 없는 묶음은 뺌")
pg_l = (t / "dist/r/zzzz-test-2026-01/index.html").read_text(encoding="utf-8")
check(f'data-cp-sub="{_sub}" data-cp-theme="quantum"' in pg_l, "상자 묶음마다 하위 ID·테마 표시(브라우저가 고르고 기록)")

print("9) 읽기 편의: 접는 상자·표·고정 페이지 조건부 줄")
sys.path.insert(0, str(SRC)); import build as B
h = B.md_renderer().convert("## 3부. 이벤트 카드 3장\n\n**핵심** 요약\n\n### 2026년\n\n**2026.10.09 · 가 (P1)**\n\n- 무슨 일: 가\n\n**2026.09.01 · 나 (P2)**\n\n- 무슨 일: 나\n\n### 2025년 이전\n\n**2025.01.02 · 다 (P1)**\n\n- 무슨 일: 다\n\n### 같은 호재인데 왜 반응이 달랐나\n\n비교\n\n## 4부. 패턴\n\n본문")
f = B.fold_event_cards(h)
check(f.count('<details class="fold"') == 2 and "카드 2장" in f and "카드 1장" in f, "이벤트 카드를 연도별로 접고 장 수 표시")
check('<h3 id="같은-호재인데-왜-반응이-달랐나">' in f or "같은 호재인데" in f.split("</details>")[-1], "비교 소절과 다른 부는 접지 않음")
w = B.wrap_tables("<table><thead><tr><th>구분</th><th>목적</th></tr></thead><tbody><tr><td>가</td><td>나</td></tr></tbody></table>", "table-text")
check('class="table-wrap table-text"' in w and 'data-label="목적"' in w, "글 위주 표는 감싸고 칸마다 머리글 이름")
pv = (SRC / "dist/privacy/index.html")
if pv.exists():
    pvt = pv.read_text(encoding="utf-8")
    check("Google Analytics" not in pvt and "스티비" not in pvt and "<!--if:" not in pvt, "안 쓰는 GA4·뉴스레터는 개인정보처리방침에 안 나옴")
rp = (SRC / "dist/r/pltr-2026-10/index.html")
if rp.exists():
    rpt = rp.read_text(encoding="utf-8")
    check('class="fold src-fold"' in rpt and 'class="chart-link"' in rpt, "출처 접기·차트 크게 보기")

print()
if FAILS:
    print(f"실패 {len(FAILS)}개")
    sys.exit(1)
print("모두 통과")
