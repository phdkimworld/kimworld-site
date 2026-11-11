"""유튜브 쿠팡 카테고리 실험(scripts/yt_shop.py) 선택 규칙 검사 (네트워크 없이)."""
import datetime as dt, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import yaml
import yt_shop as ys

ok = 0
def check(name, cond):
    global ok
    if not cond:
        print("FAIL", name); sys.exit(1)
    ok += 1; print("  ok ", name)

cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "data/yt_shop.yaml").read_text(encoding="utf-8"))
cats = list(cfg["categories"])
T = dt.date(2026, 11, 11)
check("카테고리 코드는 2자", all(len(c) == 2 for c in cats))
check("하위 ID 형식", ys.sub_id("bk", "LAES") == "ytbklaes" and ys.cat_of("ytbklaes", cats) == "bk" and ys.cat_of("blogger", cats) is None)
c, why = ys.choose(cfg, [], {}, "LAES", T)
check("기록 없으면 첫 카테고리 시험", (c, why) == (cats[0], "explore"))
log = [{"date": "2026-11-01", "ticker": f"T{i}", "cat": cats[i % len(cats)]} for i in range(len(cats) * 3 - 1)]
c, why = ys.choose(cfg, log, {}, "LAES", T)
check("3편 못 채운 카테고리 먼저", why == "explore" and sum(1 for e in log if e["cat"] == c) == 2)
log = [{"date": "2026-11-01", "ticker": f"T{i}", "cat": cats[i % len(cats)]} for i in range(len(cats) * 3)]
stats = {k: {"clicks": 0, "commission": 0} for k in cats}; stats["hl"] = {"clicks": 9, "commission": 300}
picks = [ys.choose(cfg, log, stats, f"X{i}", T) for i in range(200)]
share = sum(1 for c, w in picks if c == "hl") / len(picks)
check("성과 좋은 카테고리를 주로 고른다(약 75%)", 0.62 < share < 0.88)
check("나머지는 다른 카테고리 탐색", all(w == "explore-rand" for c, w in picks if c != "hl"))
check("같은 티커·날짜는 같은 결과", ys.choose(cfg, log, stats, "X1", T) == ys.choose(cfg, log, stats, "X1", T))
check("force 우선", ys.choose(cfg, log, stats, "X1", T, "bk") == ("bk", "force"))
old = [{"date": "2026-08-01", "ticker": "Z", "cat": "hl"}] * 5
check("기간 밖 기록은 세지 않음", ys.choose(cfg, old, {}, "A", T)[0] == cats[0])
p = ys.perf([{"subId": "ytbkaaa", "click": 3}, {"subId": "blogger", "click": 5}, {"subId": "YTHLB", "click": "2"}],
            [{"subId": "ytbkaaa", "commission": "1,200"}], cats)
check("실적을 카테고리로 묶음", p["bk"] == {"clicks": 3, "commission": 1200.0} and p["hl"]["clicks"] == 2)
check("책만: 책 아닌 상품 제외", [x["name"] for x in ys.pick([
    {"productName": "양자컴퓨터 입문", "productUrl": "https://link.coupang.com/a/1", "categoryName": "도서/음반/DVD"},
    {"productName": "태블릿 거치대", "productUrl": "https://link.coupang.com/a/2", "categoryName": "가전디지털"}], True)] == ["양자컴퓨터 입문"])
_dup = ys.pick([{"productName": n, "productUrl": f"https://link.coupang.com/a/{i}", "categoryName": "도서/음반"} for i, n in enumerate(
    ["파이썬과 IBM 퀀텀으로 배우는 양자 컴퓨팅 2/e (사은품 증정)", "(예약 11/13 발송) 파이썬과 IBM 퀀텀으로 배우는 양자 컴퓨팅 2e", "미래 양자기술 동향"])], True)
check("판매처만 다른 같은 상품은 하나로", len(_dup) == 2)
log2 = [{"cat": "bk", "kw": "{0} 책".format("양자컴퓨팅")}]
check("검색어는 덜 쓴 것부터", ys.keyword_for(cfg, "bk", log2, "양자컴퓨팅") == "미국 주식 투자 책")
check("테마 연관은 coupang.yaml 테마 검색어", ys.keyword_for(cfg, "th", [], "양자컴퓨팅") == "노트북")
print(f"yt_shop 검사 {ok}개 통과")
