#!/usr/bin/env python3
"""김박사 건강몰 검색 등록(health-search.yml). 결과는 주석(::notice)으로만, 토큰은 가린다."""
from __future__ import annotations

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
CFG = yaml.safe_load((ROOT / "health" / "health.yaml").read_text(encoding="utf-8"))
SITE = CFG["url"].rstrip("/") + "/"
SITEMAP = SITE + "sitemap.xml"


def note(t: str, m: str) -> None:
    print(f"::notice title={t}::{m}")


def call(method: str, url: str, tok: str | None = None, body: dict | None = None, raw: bytes | None = None, ctype: str = "application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": ctype}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode() or "{}"
            return r.status, (json.loads(txt) if txt.strip().startswith(("{", "[")) else {"_text": txt[:200]})
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        try:
            msg = json.loads(txt).get("error", {})
            msg = msg.get("message", "") if isinstance(msg, dict) else str(msg)
        except Exception:
            msg = txt[:160]
        return e.code, {"_err": str(msg)[:200]}


def token() -> str:
    body = urllib.parse.urlencode({"client_id": os.environ["CID"], "client_secret": os.environ["CSEC"],
                                   "refresh_token": os.environ["RT"], "grant_type": "refresh_token"}).encode()
    s, t = call("POST", "https://oauth2.googleapis.com/token", raw=body, ctype="application/x-www-form-urlencoded")
    if s != 200:
        print(f"::error title=건강몰 검색 등록::토큰 갱신 실패 {s} {t.get('_err','')}")
        sys.exit(1)
    print(f"::add-mask::{t['access_token']}")
    return t["access_token"]


def site_q() -> str:
    return urllib.parse.quote(SITE, safe="")


def main() -> int:
    mode = os.environ.get("MODE", "status")
    if mode == "indexnow":
        key = (CFG.get("indexnow_key") or "").strip()
        if not key:
            print("::error title=IndexNow::health.yaml indexnow_key 없음"); return 1
        # 사이트맵을 받지 않고 설정에서 주소를 만든다(워커가 기본 UA를 막을 수 있음). sitemap.xml 과 같은 목록
        urls = [SITE, SITE + "guide/", SITE + "about/"] + [f"{SITE}guide/{g['slug']}/" for g in CFG.get("guides") or []]
        host = urllib.parse.urlparse(SITE).netloc
        body = {"host": host, "key": key, "keyLocation": f"{SITE}{key}.txt", "urlList": urls}
        for ep in ("https://api.indexnow.org/indexnow", "https://searchadvisor.naver.com/indexnow"):
            try:
                s, r = call("POST", ep, body=body, ctype="application/json; charset=utf-8")
            except Exception as e:
                s, r = "실패", {"_err": f"{type(e).__name__} {str(e)[:120]}"}
            note("IndexNow", f"{urllib.parse.urlparse(ep).netloc} {s} · 주소 {len(urls)}개 {r.get('_err','')}")
        return 0
    tok = token()
    site = {"site": {"type": "SITE", "identifier": SITE}}
    if mode == "token":
        s, r = call("POST", "https://www.googleapis.com/siteVerification/v1/token", tok, {**site, "verificationMethod": "META"})
        m = re.search(r'content="([^"]+)"', r.get("token", ""))
        note("구글 확인 태그", f"{s} content={m.group(1) if m else r}")
        return 0 if m else 1
    if mode == "verify":
        s, r = call("POST", "https://www.googleapis.com/siteVerification/v1/webResource?verificationMethod=META", tok, site)
        note("구글 소유 확인", f"{s} {r.get('id', r.get('_err',''))}")
        if s != 200:
            return 1
        s, r = call("PUT", f"https://www.googleapis.com/webmasters/v3/sites/{site_q()}", tok)
        note("서치 콘솔 사이트 추가", f"{s} {r.get('_err','') or SITE}")
        s, r = call("PUT", f"https://www.googleapis.com/webmasters/v3/sites/{site_q()}/sitemaps/{urllib.parse.quote(SITEMAP, safe='')}", tok)
        note("사이트맵 제출", f"{s} {r.get('_err','') or SITEMAP}")
    s, r = call("GET", "https://www.googleapis.com/webmasters/v3/sites", tok)
    note("서치 콘솔 속성", ", ".join(f"{e['siteUrl']}({e['permissionLevel']})" for e in r.get("siteEntry", [])) or f"{s} 없음 {r.get('_err','')}")
    s, r = call("GET", f"https://www.googleapis.com/webmasters/v3/sites/{site_q()}/sitemaps", tok)
    for sm in r.get("sitemap", []):
        note("사이트맵 상태", f"{sm['path']} 제출 {sm.get('lastSubmitted','')} 읽음 {sm.get('lastDownloaded','-')} 오류 {sm.get('errors',0)} 경고 {sm.get('warnings',0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
