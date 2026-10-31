"""쿠팡 파트너스 검색 API로 테마별 상품을 받아 .cache/coupang_auto.json 에 쌓는다.

- 키는 환경변수 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 로만 읽는다. 키·서명은 출력하지 않는다.
- 키가 없거나 실패해도 종료 코드는 0(사이트 빌드는 계속되고, 예전 결과나 ads.yaml 수동 상품을 쓴다).
- 호출 수는 data/coupang.yaml 의 상한을 지킨다. 오래된 검색어부터 새로 받는다.
- 이 결과 파일은 저장소에 올리지 않는다(.gitignore). GitHub Actions 캐시로만 이어 간다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
COMMON = "_common"   # 공통 검색어 묶음의 테마 이름(build.py와 같게)
CACHE = Path(os.environ.get("COUPANG_CACHE") or ROOT / ".cache" / "coupang_auto.json")


def signed_date(now: dt.datetime) -> str:
    return now.astimezone(dt.timezone.utc).strftime("%y%m%dT%H%M%SZ")


def authorization(method: str, path: str, query: str, access: str, secret: str, now: dt.datetime) -> str:
    sd = signed_date(now)
    msg = sd + method.upper() + path + query
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={sd}, signature={sig}"


def sub_id(theme_slug: str, keyword: str) -> str:
    """하위 ID = 테마 + 검색어 해시 4자리. 검색어를 바꾸면 하위 ID도 바뀌어 성과가 섞이지 않는다."""
    return re.sub(r"[^a-z0-9]", "", theme_slug.lower())[:16] + hashlib.md5(keyword.encode("utf-8")).hexdigest()[:4]


def parse(js: dict) -> list[dict]:
    data = js.get("data") if isinstance(js, dict) else None
    items = data.get("productData") if isinstance(data, dict) else data
    out = []
    for x in items or []:
        if not isinstance(x, dict):
            continue
        name, url = str(x.get("productName") or "").strip(), str(x.get("productUrl") or "").strip()
        img = str(x.get("productImage") or "").strip()
        if not name or not url.startswith("https://"):
            continue
        try:
            price = int(float(x.get("productPrice") or 0))
        except (TypeError, ValueError):
            price = 0
        out.append({"name": name, "url": url, "image": img if img.startswith("https://") else "",
                    "price": price, "rocket": bool(x.get("isRocket")), "rank": int(x.get("rank") or 999)})
    return out


def search(keyword: str, sid: str, limit: int, access: str, secret: str) -> list[dict]:
    query = urllib.parse.urlencode({"keyword": keyword, "limit": limit, "subId": sid})
    req = urllib.request.Request(
        f"{DOMAIN}{SEARCH_PATH}?{query}",
        headers={"Authorization": authorization("GET", SEARCH_PATH, query, access, secret, dt.datetime.now(dt.timezone.utc)),
                 "Content-Type": "application/json;charset=UTF-8"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return parse(json.loads(r.read().decode("utf-8")))


# 골드박스(쿠팡 '오늘의 특가', 매일 바뀜). 리포트 끝 '오늘의 특가' 한 장 카드에 쓴다(운영자 승인 2026-10-30). 하위 ID "deal"
GOLDBOX_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/goldbox"
DEAL_SUB = "deal"


def _num(x: dict, *keys) -> int:
    for k in keys:
        v = x.get(k)
        try:
            if v is not None and str(v).strip() != "":
                return int(float(str(v).replace(",", "").replace("%", "")))
        except (TypeError, ValueError):
            continue
    return 0


def parse_deals(js: dict) -> tuple[list[dict], list[str]]:
    """골드박스 응답 → 카드용 상품. 할인율·원래 가격은 응답에 있을 때만 쓴다(없으면 지어내지 않는다). 둘째 값은 받은 필드 이름(진단용)."""
    data = js.get("data") if isinstance(js, dict) else None
    items = data.get("productData") if isinstance(data, dict) else data
    out, keys = [], set()
    for x in items or []:
        if not isinstance(x, dict):
            continue
        keys.update(x.keys())
        name, url = str(x.get("productName") or "").strip(), str(x.get("productUrl") or "").strip()
        img = str(x.get("productImage") or "").strip()
        if not name or not url.startswith("https://"):
            continue
        price = _num(x, "productPrice", "salePrice")
        orig = _num(x, "originalPrice", "basePrice", "productOriginalPrice", "listPrice")
        rate = _num(x, "discountRate", "discountPercent", "discountRatio")
        if not rate and orig > price > 0:
            rate = round((orig - price) * 100 / orig)
        if orig <= price:
            orig = 0
        out.append({"name": name, "url": url, "image": img if img.startswith("https://") else "", "price": price,
                    "orig": orig, "rate": rate if 0 < rate < 100 else 0, "rocket": bool(x.get("isRocket")),
                    "free": bool(x.get("isFreeShipping")), "id": str(x.get("productId") or "")})
    return out, sorted(keys)


def goldbox(access: str, secret: str) -> tuple[list[dict], list[str]]:
    query = urllib.parse.urlencode({"subId": DEAL_SUB})
    req = urllib.request.Request(
        f"{DOMAIN}{GOLDBOX_PATH}?{query}",
        headers={"Authorization": authorization("GET", GOLDBOX_PATH, query, access, secret, dt.datetime.now(dt.timezone.utc)),
                 "Content-Type": "application/json;charset=UTF-8"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return parse_deals(json.loads(r.read().decode("utf-8")))


REPORT_PATHS = ["/v2/providers/affiliate_open_api/apis/openapi/v1/reports/orders",
                "/v2/providers/affiliate_open_api/apis/openapi/v1/reports/commission"]
REPORTS = Path(os.environ.get("COUPANG_REPORTS") or ROOT / ".cache" / "coupang_reports.json")


def parse_report(js: dict) -> dict:
    """실적 응답에서 하위 ID별 주문 수·수수료를 모은다. 필드 이름이 달라도 흔한 이름은 모두 받는다."""
    rows = js.get("data") if isinstance(js, dict) else None
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("items") or []
    by, total = {}, 0.0
    for x in rows or []:
        if not isinstance(x, dict):
            continue
        sid = str(x.get("subId") or x.get("subid") or x.get("sub_id") or x.get("subParam") or "").lower()
        com = 0.0
        for k in ("commission", "commissionAmount", "commission_amount", "amount"):
            try:
                if x.get(k) is not None:
                    com = float(x[k]); break
            except (TypeError, ValueError):
                pass
        total += com
        if sid:
            b = by.setdefault(sid, {"orders": 0, "commission": 0.0})
            b["orders"] += int(x.get("orderCount") or x.get("quantity") or 1)
            b["commission"] += com
    return {"by_sub": by, "total": total}


def report_get(path: str, query: str, access: str, secret: str) -> dict:
    req = urllib.request.Request(f"{DOMAIN}{path}?{query}", headers={
        "Authorization": authorization("GET", path, query, access, secret, dt.datetime.now(dt.timezone.utc)),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def sync_reports(now: dt.datetime, access: str, secret: str, budget: int, getter=report_get) -> int:
    """하루 한 번, 지난 30일 실적(하위 ID별 주문·수수료)을 받아 학습에 쓴다. 쓴 호출 수를 돌려준다."""
    try:
        old = json.loads(REPORTS.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    if budget <= 0 or now.timestamp() - float(old.get("ts", 0)) < 20 * 3600:
        return 0
    # 실패해도 시도한 시각을 남겨 하루에 한 번만 시도한다(검색 호출 몫을 뺏지 않게). 이전 실적은 그대로 둔다
    REPORTS.parent.mkdir(parents=True, exist_ok=True)
    REPORTS.write_text(json.dumps({**old, "ts": now.timestamp()}, ensure_ascii=False), encoding="utf-8")
    kst = now.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
    q = urllib.parse.urlencode({"startDate": (kst - dt.timedelta(days=30)).strftime("%Y%m%d"),
                                "endDate": (kst - dt.timedelta(days=1)).strftime("%Y%m%d"), "page": 0})
    used = 0
    for path in REPORT_PATHS[:budget]:
        used += 1
        try:
            res = parse_report(getter(path, q, access, secret))
        except Exception as e:
            print(f"[coupang] 실적 받기 실패({path.rsplit('/', 1)[-1]}): {type(e).__name__}")
            continue
        if res["by_sub"] or path.endswith("commission"):
            REPORTS.parent.mkdir(parents=True, exist_ok=True)
            REPORTS.write_text(json.dumps({"ts": now.timestamp(), "source": path.rsplit("/", 1)[-1], **res}, ensure_ascii=False), encoding="utf-8")
            print(f"[coupang] 실적: 하위 ID {len(res['by_sub'])}개, 30일 수수료 합계 {res['total']:.0f}원")
            break
    return used


def plan(cfg: dict, themes: list[dict]) -> list[dict]:
    slug = {t["name"]: t["slug"] for t in themes}
    jobs = []
    for theme, kws in (cfg.get("keywords") or {}).items():
        if theme not in slug:
            print(f"[coupang] data/themes.yaml 에 없는 테마는 건너뜀: {theme}")
            continue
        for i, kw in enumerate(kws or []):
            jobs.append({"theme": theme, "keyword": str(kw), "sub_id": sub_id(slug[theme], str(kw)), "idx": i})
    # 공통 검색어(독자층이 많이 사는 생활·건강·취미 상품): 테마 이름 "_common", 하위 ID는 common+해시
    for i, kw in enumerate(cfg.get("common") or []):
        jobs.append({"theme": COMMON, "keyword": str(kw), "sub_id": sub_id("common", str(kw)), "idx": i})
    return jobs


def run(now: dt.datetime | None = None, searcher=search, reporter=report_get, dealer=None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    access, secret = os.environ.get("COUPANG_ACCESS_KEY", "").strip(), os.environ.get("COUPANG_SECRET_KEY", "").strip()
    if not access or not secret:
        print("[coupang] 키가 없어 동기화를 건너뜀(ads.yaml 수동 상품을 씀)")
        return 0
    cfg = yaml.safe_load((ROOT / "data" / "coupang.yaml").read_text(encoding="utf-8")) or {}
    themes = yaml.safe_load((ROOT / "data" / "themes.yaml").read_text(encoding="utf-8")) or []
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    entries = cache.get("entries") or {}
    calls = [c for c in cache.get("calls") or [] if now.timestamp() - c < 3600]

    jobs = plan(cfg, themes)
    keys = {f'{j["theme"]}|{j["keyword"]}' for j in jobs}
    entries = {k: v for k, v in entries.items() if k in keys}  # 설정에서 빠진 검색어는 버린다
    fresh_after = now.timestamp() - float(cfg.get("refresh_hours", 20)) * 3600
    todo = [j for j in jobs if entries.get(f'{j["theme"]}|{j["keyword"]}', {}).get("ts", 0) < fresh_after]
    # 오래된 것부터. 아직 한 번도 안 받은 것끼리는 각 테마의 첫 번째 검색어부터(상품이 하나도 없는 테마를 먼저 채운다)
    todo.sort(key=lambda j: (entries.get(f'{j["theme"]}|{j["keyword"]}', {}).get("ts", 0), j["idx"]))
    budget = min(int(cfg.get("max_calls_per_run", 8)), int(cfg.get("max_calls_per_hour", 8)) - len(calls))
    limit = max(1, min(10, int(cfg.get("results_per_keyword", 10))))
    # 골드박스(하루 안에 바뀌므로 3시간마다 다시 받는다). 시간당 10회 상한은 검색 API 몫이라 여기 호출은 세지 않는다
    gb = cache.get("goldbox") or {}
    if now.timestamp() - float(gb.get("ts") or 0) > 3 * 3600:
        gb = {**gb, "ts": now.timestamp() - 2 * 3600}  # 실패해도 매 실행마다 두드리지 않게(1시간 뒤 다시)
        try:
            deals, keys = (dealer or goldbox)(access, secret)
            if deals:
                gb = {"ts": now.timestamp(), "fetched": now.timestamp(), "date": now.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat(), "items": deals[:20]}
            if keys:
                print(f"::notice title=쿠팡 골드박스::상품 {len(deals)}개, 할인율 있는 상품 {sum(1 for d in deals if d['rate'])}개, 응답 필드 {', '.join(keys)}")
        except urllib.error.HTTPError as e:
            print(f"::warning title=쿠팡 골드박스::HTTP {e.code}")
        except Exception as e:
            print(f"::warning title=쿠팡 골드박스::{type(e).__name__}")
    done = 0
    for j in todo[: max(0, budget)]:
        calls.append(now.timestamp())
        try:
            items = searcher(j["keyword"], j["sub_id"], limit, access, secret)
        except urllib.error.HTTPError as e:
            print(f'[coupang] 검색 실패 "{j["keyword"]}": HTTP {e.code}')
            if e.code == 429:
                break
            continue
        except Exception as e:  # 네트워크 등. 키는 출력하지 않는다
            print(f'[coupang] 검색 실패 "{j["keyword"]}": {type(e).__name__}')
            continue
        entries[f'{j["theme"]}|{j["keyword"]}'] = {**{k: v for k, v in j.items() if k != "idx"}, "ts": now.timestamp(), "date": now.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat(), "products": items}
        done += 1
    # 상품이 모두 최신이고 호출 여유가 있으면 하루 한 번 실적을 받는다(검색과 같은 시간당 상한 안에서)
    left = int(cfg.get("max_calls_per_hour", 8)) - len(calls) if len(todo) <= done else 0
    for _ in range(sync_reports(now, access, secret, min(2, left), reporter)):
        calls.append(now.timestamp())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"entries": entries, "calls": calls, "goldbox": gb}, ensure_ascii=False), encoding="utf-8")
    print(f"[coupang] 새로 받은 검색어 {done}개, 보관 중 {len(entries)}/{len(jobs)}개, 남은 대기 {max(0, len(todo) - done)}개")
    return 0


if __name__ == "__main__":
    sys.exit(run())
