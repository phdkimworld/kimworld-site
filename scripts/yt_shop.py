"""유튜브 영상 쿠팡 카테고리 실험: 카테고리를 고르고 상품 후보를 찾는다(data/yt_shop.yaml 설명 참고, 2026-11-10).

입력(환경변수)
  YT_TICKER  영상 종목 티커(필수)
  YT_FORCE   카테고리 코드를 직접 정할 때(선택, 예: bk)
  DRY        1이면 기록(social/youtube/shop.json)을 남기지 않는다
  COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY
출력
  OUT_DIR(기본 .cache/yt_shop)/candidates.json  고른 카테고리·이유·하위 ID·상품 후보 최대 6개(이름·링크·가격·표지/사진 파일)
  OUT_DIR/img_<n>.jpg                            상품 사진(영상 속 카드용)
  social/youtube/shop.json                        영상별 카테고리 기록(날짜·티커·카테고리·검색어·하위 ID). 숫자·상품명 없음
공개 로그·주석에는 카테고리 코드와 시험/활용 구분만 남긴다(실적 숫자·상품 이름은 남기지 않는다).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coupang_sync as cs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "social" / "youtube" / "shop.json"
BOOKISH = re.compile(r"(도서|책|입문|투자법|가이드|교과서|바이블|이야기|원칙|전략|경제|주식|산업|개정판|지음|출판)")
NOT_BOOK = re.compile(r"(케이스|필름|거치대|스탠드|노트북|태블릿|키보드|마우스|이어폰|충전|커버|독서대|북엔드|문구|다이어리|플래너)")
REPORTS = "/v2/providers/affiliate_open_api/apis/openapi/v1/reports/"
DISCLOSURE = "이 영상은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def sub_id(cat: str, ticker: str) -> str:
    return ("yt" + cat + re.sub(r"[^a-z0-9]", "", ticker.lower()))[:20]


def cat_of(sid: str, cats) -> str | None:
    s = str(sid or "").lower()
    return s[2:4] if s.startswith("yt") and s[2:4] in cats else None


def perf(rows_clicks: list[dict], rows_comm: list[dict], cats) -> dict:
    """쿠팡 보고서 행을 카테고리별 클릭·수수료로 묶는다."""
    out = {c: {"clicks": 0, "commission": 0.0} for c in cats}
    num = lambda v: float(str(v).replace(",", "")) if str(v).replace(",", "").replace(".", "", 1).lstrip("-").isdigit() else 0.0
    sid = lambda x: x.get("subId") or x.get("subid") or x.get("sub_id") or x.get("subParam") or ""
    for x in rows_clicks:
        c = cat_of(sid(x), cats)
        if c:
            out[c]["clicks"] += int(num(x.get("click") or x.get("clicks") or x.get("clickCount") or x.get("count") or 0))
    for x in rows_comm:
        c = cat_of(sid(x), cats)
        if c:
            out[c]["commission"] += num(x.get("commission") or x.get("commissionAmount") or x.get("amount") or 0)
    return out


def choose(cfg: dict, log: list[dict], stats: dict, ticker: str, today: dt.date, force: str = "") -> tuple[str, str]:
    """(카테고리, 이유) — 이유: force|explore|exploit|explore-rand"""
    cats = list(cfg["categories"])
    if force in cats:
        return force, "force"
    since = (today - dt.timedelta(days=int(cfg.get("window_days", 60)))).isoformat()
    n = {c: 0 for c in cats}
    for e in log:
        if e.get("date", "") >= since and e.get("cat") in n and not (e.get("ticker") == ticker.upper() and e.get("date") == today.isoformat()):
            n[e["cat"]] += 1
    low = [c for c in cats if n[c] < int(cfg.get("explore_min", 3))]
    if low:
        return min(low, key=lambda c: (n[c], cats.index(c))), "explore"
    rnd = random.Random(hashlib.md5(f"{ticker.upper()}{today}".encode()).hexdigest())
    score = lambda c: (stats.get(c, {}).get("commission", 0) / n[c], stats.get(c, {}).get("clicks", 0) / n[c])
    best = max(cats, key=lambda c: (score(c), -cats.index(c)))
    if rnd.random() * 100 < float(cfg.get("exploit_pct", 75)):
        return best, "exploit"
    return rnd.choice([c for c in cats if c != best]), "explore-rand"


def keyword_for(cfg: dict, cat: str, log: list[dict], theme: str) -> str:
    cc = cfg["categories"][cat]
    if cc.get("theme_items"):
        kws = list(((yaml.safe_load((ROOT / "data" / "coupang.yaml").read_text(encoding="utf-8")) or {}).get("keywords") or {}).get(theme) or [])
    else:
        kws = [k.replace("{theme}", theme or "미국 주식") for k in cc.get("keywords") or []]
    kws = kws or ["미국 주식 투자 책"]
    used = {k: 0 for k in kws}
    for e in log:
        if e.get("cat") == cat and e.get("kw") in used:
            used[e["kw"]] += 1
    return min(kws, key=lambda k: (used[k], kws.index(k)))


def is_book(x: dict) -> bool:
    cat = str(x.get("categoryName") or "")
    if cat:
        return "도서" in cat or "책" in cat
    name = str(x.get("productName") or "")
    return bool(BOOKISH.search(name)) and not NOT_BOOK.search(name)


def search_raw(keyword: str, sid: str, access: str, secret: str) -> list[dict]:
    q = urllib.parse.urlencode({"keyword": keyword, "limit": 10, "subId": sid})
    req = urllib.request.Request(f"{cs.DOMAIN}{cs.SEARCH_PATH}?{q}", headers={
        "Authorization": cs.authorization("GET", cs.SEARCH_PATH, q, access, secret, dt.datetime.now(dt.timezone.utc)),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        js = json.loads(r.read().decode("utf-8"))
    data = js.get("data") if isinstance(js, dict) else None
    items = data.get("productData") if isinstance(data, dict) else data
    return [x for x in items or [] if isinstance(x, dict)]


def pick(items: list[dict], books_only: bool, n: int = 6) -> list[dict]:
    out, seen = [], set()
    for x in items:
        url, name = str(x.get("productUrl") or ""), str(x.get("productName") or "").strip()
        if not url.startswith("https://") or not name or (books_only and not is_book(x)):
            continue
        key = re.sub(r"\W", "", re.sub(r"[(\[][^)\]]*[)\]]", "", name))[:14]  # 같은 책·상품의 판매처별 중복(괄호 속 사은품·예약 문구 차이)은 하나로
        if key in seen:
            continue
        seen.add(key)
        try:
            price = int(float(x.get("productPrice") or 0))
        except (TypeError, ValueError):
            price = 0
        out.append({"name": name, "url": url, "pid": str(x.get("productId") or ""), "price": price, "image": str(x.get("productImage") or ""),
                    "category": str(x.get("categoryName") or ""), "rocket": bool(x.get("isRocket"))})
        if len(out) >= n:
            break
    return out


DEEPLINK = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"


def shorten(cands: list[dict], sid: str, access: str, secret: str) -> None:
    """상품 페이지 주소를 쿠팡 단축 링크(link.coupang.com/a/…, 같은 하위 ID)로 바꾼다. 실패하면 검색 결과 링크를 그대로 둔다."""
    src = [f"https://www.coupang.com/vp/products/{c['pid']}" for c in cands if c.get("pid")]
    if not src:
        return
    body = json.dumps({"coupangUrls": src, "subId": sid}).encode()
    req = urllib.request.Request(cs.DOMAIN + DEEPLINK, data=body, method="POST", headers={
        "Authorization": cs.authorization("POST", DEEPLINK, "", access, secret, dt.datetime.now(dt.timezone.utc)),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        js = json.loads(r.read().decode("utf-8"))
    short = {}
    for x in js.get("data") or []:
        m = re.search(r"/products/(\d+)", str(x.get("originalUrl") or ""))
        if m and str(x.get("shortenUrl") or "").startswith("https://"):
            short[m.group(1)] = x["shortenUrl"]
    for c in cands:
        if c.get("pid") in short:
            c["long_url"], c["url"] = c["url"], short[c["pid"]]


def report_rows(kind: str, start: str, end: str, access: str, secret: str) -> list[dict]:
    out = []
    for page in range(10):
        q = urllib.parse.urlencode({"startDate": start, "endDate": end, "page": page})
        js = cs.report_get(REPORTS + kind, q, access, secret)
        d = js.get("data") if isinstance(js, dict) else None
        if isinstance(d, dict):
            d = d.get("data") or d.get("items") or d.get("content") or []
        rs = [x for x in d or [] if isinstance(x, dict)]
        out += rs
        if len(rs) < 1000:
            break
    return out


def main() -> int:
    access, secret = os.environ.get("COUPANG_ACCESS_KEY", "").strip(), os.environ.get("COUPANG_SECRET_KEY", "").strip()
    ticker = os.environ.get("YT_TICKER", "").strip().upper()
    force, dry = os.environ.get("YT_FORCE", "").strip().lower(), os.environ.get("DRY") == "1"
    out = Path(os.environ.get("OUT_DIR") or ROOT / ".cache" / "yt_shop")
    out.mkdir(parents=True, exist_ok=True)
    if not (access and secret and ticker):
        print("::error title=유튜브 쿠팡::키 또는 티커 없음")
        return 1
    cfg = yaml.safe_load((ROOT / "data" / "yt_shop.yaml").read_text(encoding="utf-8"))
    cats = list(cfg["categories"])
    tickers = yaml.safe_load((ROOT / "data" / "tickers.yaml").read_text(encoding="utf-8")) or {}
    theme = str((tickers.get(ticker) or {}).get("theme") or "")
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).date()

    stats = {}
    try:
        start = (kst - dt.timedelta(days=int(cfg.get("window_days", 60)))).strftime("%Y%m%d")
        end = (kst - dt.timedelta(days=1)).strftime("%Y%m%d")
        stats = perf(report_rows("clicks", start, end, access, secret), report_rows("commission", start, end, access, secret), cats)
    except Exception as e:  # 보고서를 못 받아도 시험 단계 규칙으로는 고를 수 있다
        print(f"::warning title=유튜브 쿠팡::실적 받기 실패 {type(e).__name__}")
    cat, why = choose(cfg, log, stats, ticker, today, force)
    cc = cfg["categories"][cat]
    kw = keyword_for(cfg, cat, log, theme)
    sid = sub_id(cat, ticker)
    q = kw if not cc.get("books_only") or re.search(r"책|도서", kw) else kw + " 책"
    items = []
    try:
        items = search_raw(q, sid, access, secret)
    except urllib.error.HTTPError as e:
        print(f"::warning title=유튜브 쿠팡::검색 HTTP {e.code}" + (" (시간당 한도. 다음 정시 뒤 다시)" if e.code == 429 else ""))
    except Exception as e:
        print(f"::warning title=유튜브 쿠팡::검색 실패 {type(e).__name__}")
    cands = pick(items, bool(cc.get("books_only")))
    try:
        shorten(cands, sid, access, secret)
    except Exception as e:
        print(f"::warning title=유튜브 쿠팡::단축 링크 실패 {type(e).__name__}(긴 링크 그대로)")
    for i, c in enumerate(cands):
        if c["image"].startswith("https://"):
            try:
                with urllib.request.urlopen(urllib.request.Request(c["image"], headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
                    (out / f"img_{i}.jpg").write_bytes(r.read())
                c["img"] = f"img_{i}.jpg"
            except Exception as e:
                print(f"::warning title=유튜브 쿠팡::사진 {i} 실패 {type(e).__name__}")
    (out / "candidates.json").write_text(json.dumps({
        "ticker": ticker, "date": today.isoformat(), "cat": cat, "cat_name": cc["name"], "line": cc.get("line", ""),
        "reason": why, "keyword": kw, "sub_id": sid, "disclosure": DISCLOSURE, "candidates": cands}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"::notice title=유튜브 쿠팡::{ticker} 카테고리 {cat}({why}), 후보 {len(cands)}개, 하위 ID {sid}")
    if cands and not dry:
        log = [e for e in log if not (e.get("ticker") == ticker and e.get("date") == today.isoformat())]
        log.append({"date": today.isoformat(), "ticker": ticker, "cat": cat, "kw": kw, "sub_id": sid, "why": why})
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0 if cands else 1


if __name__ == "__main__":
    sys.exit(main())
