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
CACHE = Path(os.environ.get("COUPANG_CACHE") or ROOT / ".cache" / "coupang_auto.json")


def signed_date(now: dt.datetime) -> str:
    return now.astimezone(dt.timezone.utc).strftime("%y%m%dT%H%M%SZ")


def authorization(method: str, path: str, query: str, access: str, secret: str, now: dt.datetime) -> str:
    sd = signed_date(now)
    msg = sd + method.upper() + path + query
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={sd}, signature={sig}"


def sub_id(theme_slug: str, idx: int) -> str:
    return re.sub(r"[^a-z0-9]", "", theme_slug.lower())[:20] + str(idx + 1)


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


def plan(cfg: dict, themes: list[dict]) -> list[dict]:
    slug = {t["name"]: t["slug"] for t in themes}
    jobs = []
    for theme, kws in (cfg.get("keywords") or {}).items():
        if theme not in slug:
            print(f"[coupang] data/themes.yaml 에 없는 테마는 건너뜀: {theme}")
            continue
        for i, kw in enumerate(kws or []):
            jobs.append({"theme": theme, "keyword": str(kw), "sub_id": sub_id(slug[theme], i)})
    return jobs


def run(now: dt.datetime | None = None, searcher=search) -> int:
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
    todo.sort(key=lambda j: entries.get(f'{j["theme"]}|{j["keyword"]}', {}).get("ts", 0))  # 오래된 것부터
    budget = min(int(cfg.get("max_calls_per_run", 8)), int(cfg.get("max_calls_per_hour", 8)) - len(calls))
    limit = max(1, min(10, int(cfg.get("results_per_keyword", 10))))
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
        entries[f'{j["theme"]}|{j["keyword"]}'] = {**j, "ts": now.timestamp(), "date": now.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat(), "products": items}
        done += 1
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"entries": entries, "calls": calls}, ensure_ascii=False), encoding="utf-8")
    print(f"[coupang] 새로 받은 검색어 {done}개, 보관 중 {len(entries)}/{len(jobs)}개, 남은 대기 {max(0, len(todo) - done)}개")
    return 0


if __name__ == "__main__":
    sys.exit(run())
