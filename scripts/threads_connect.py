#!/usr/bin/env python3
"""Threads @drkimworld 토큰을 휴대폰 승인만으로 다시 받기(2026-11-26 운영자 "삭제 권한 얻어서 해결해").

옛 형식 글을 지우려면 threads_delete 권한이 든 토큰이 필요하다. 개발자 화면의 토큰 생성기(데스크톱 팝업) 대신
Threads 로그인(OAuth) 코드 → 단기 토큰 → 장기 토큰(60일) 교환을 Actions 안에서 하고,
토큰은 출력하지 않고 바로 비밀값 DRKIM_THREADS_ACCESS_TOKEN 에 넣는다(scripts/ig_connect.py 와 같은 방식).

환경: CODE(리디렉션 주소 ?code= 값 또는 주소 전체, 1시간·1회용), THREADS_APP_SECRET, GH_SECRETS_PAT, EXPECT(기대 아이디)
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from token_refresh import http, put_secret  # noqa: E402

APP_ID = "2171942756723397"  # Meta 앱 phdkimworld-poster 의 Threads 앱 ID(공개값)
REDIRECT = "https://drkimworld.com/"
SCOPES = "threads_basic,threads_content_publish,threads_manage_insights,threads_manage_replies,threads_read_replies,threads_delete"
AUTH_URL = "https://threads.net/oauth/authorize?" + urllib.parse.urlencode(
    {"client_id": APP_ID, "redirect_uri": REDIRECT, "scope": SCOPES, "response_type": "code"})


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "url":
        print(AUTH_URL)
        return 0
    code = os.environ.get("CODE", "").strip().split("#")[0]
    if code.startswith("http"):
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    secret = os.environ.get("THREADS_APP_SECRET", "")
    pat = os.environ.get("GH_SECRETS_PAT", "")
    expect = os.environ.get("EXPECT", "drkimworld").lstrip("@")
    if not (code and secret and pat):
        print("::error::code·THREADS_APP_SECRET·GH_SECRETS_PAT 중 빠진 것이 있음")
        return 1
    print(f"::add-mask::{code}")
    st, r = post_form("https://graph.threads.net/oauth/access_token",
                      {"client_id": APP_ID, "client_secret": secret, "grant_type": "authorization_code",
                       "redirect_uri": REDIRECT, "code": code})
    short = r.get("access_token") if isinstance(r, dict) else None
    if st != 200 or not short:
        err = (r.get("error", {}) or {}).get("message", "") if isinstance(r, dict) else ""
        print(f"::error::코드 교환 실패 HTTP {st}: {str(err)[:200]} — 코드는 1시간·1회용이니 승인을 다시 하고 새 코드로")
        return 1
    print(f"::add-mask::{short}")
    q = urllib.parse.urlencode({"grant_type": "th_exchange_token", "client_secret": secret, "access_token": short})
    st, r = http("GET", f"https://graph.threads.net/access_token?{q}")
    long_tok = r.get("access_token") if isinstance(r, dict) else None
    if st != 200 or not long_tok:
        print(f"::error::장기 토큰 교환 실패 HTTP {st}")
        return 1
    print(f"::add-mask::{long_tok}")
    q = urllib.parse.urlencode({"fields": "id,username", "access_token": long_tok})
    st, me = http("GET", f"https://graph.threads.net/v1.0/me?{q}")
    name = me.get("username", "") if isinstance(me, dict) else ""
    if st != 200 or name != expect:
        print(f"::error::다른 계정으로 승인됨(@{name}) — @{expect} 로 로그인한 뒤 다시 승인. 비밀값은 바꾸지 않음")
        return 1
    err = put_secret(pat, "DRKIM_THREADS_ACCESS_TOKEN", long_tok)
    if err:
        print(f"::error::DRKIM_THREADS_ACCESS_TOKEN 저장 실패: {err}")
        return 1
    print(f"::notice::연결됨 @{name} → 비밀값 DRKIM_THREADS_ACCESS_TOKEN 저장(삭제 권한 포함, 60일, token-refresh 가 갱신)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
