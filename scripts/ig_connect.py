#!/usr/bin/env python3
"""인스타 계정을 휴대폰만으로 연결(2026-11-26 운영자 "폰으론 못해?").

개발자 화면의 토큰 생성기는 데스크톱 팝업이 필요하고, 그 맥은 인스타가 429로 막았다.
대신 Instagram 로그인(OAuth) 코드 → 장기 토큰(60일) 교환을 Actions 안에서 하고,
토큰은 출력하지 않고 바로 GitHub 비밀값에 넣는다.

환경: CODE(리디렉션 주소 ?code= 값, 1시간·1회용), IG_APP_SECRET, GH_SECRETS_PAT,
      EXPECT(기대하는 인스타 아이디), PREFIX(비밀값 이름 앞부분, 예 HEALTH_IG)
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from token_refresh import http, put_secret  # noqa: E402

APP_ID = "1760771078519770"  # Meta 앱 phdkimworld-poster 의 Instagram 앱 ID(공개값)
TH_APP_ID = "2171942756723397"  # 같은 앱의 Threads 앱 ID(공개값). PLATFORM=threads 일 때(2026-11-27 @drkimworld 토큰 끊김)
REDIRECT = "https://drkimworld.com/"


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
    code = os.environ.get("CODE", "").strip().split("#")[0]
    if code.startswith("http"):  # 주소 전체를 붙여 넣은 경우
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    secret = os.environ.get("IG_APP_SECRET", "")
    pat = os.environ.get("GH_SECRETS_PAT", "")
    expect = os.environ.get("EXPECT", "").lstrip("@")
    prefix = os.environ.get("PREFIX", "HEALTH_IG")
    if os.environ.get("PLATFORM") == "threads":
        return threads(code, secret, pat, expect, prefix)
    if not (code and secret and pat):
        print("::error::code·HEALTH_IG_APP_SECRET·GH_SECRETS_PAT 중 빠진 것이 있음")
        return 1
    print(f"::add-mask::{code}")
    st, r = post_form("https://api.instagram.com/oauth/access_token",
                      {"client_id": APP_ID, "client_secret": secret, "grant_type": "authorization_code",
                       "redirect_uri": REDIRECT, "code": code})
    short = (r or {}).get("access_token") if isinstance(r, dict) else None
    if st != 200 or not short:
        err = r.get("error_message") or r.get("error", {}) if isinstance(r, dict) else ""
        print(f"::error::코드 교환 실패 HTTP {st}: {str(err)[:200]} — 코드는 1시간·1회용이니 승인을 다시 하고 새 코드로")
        return 1
    print(f"::add-mask::{short}")
    q = urllib.parse.urlencode({"grant_type": "ig_exchange_token", "client_secret": secret, "access_token": short})
    st, r = http("GET", f"https://graph.instagram.com/access_token?{q}")
    long_tok = (r or {}).get("access_token") if isinstance(r, dict) else None
    if st != 200 or not long_tok:
        print(f"::error::장기 토큰 교환 실패 HTTP {st}")
        return 1
    print(f"::add-mask::{long_tok}")
    q = urllib.parse.urlencode({"fields": "user_id,username,account_type", "access_token": long_tok})
    st, me = http("GET", f"https://graph.instagram.com/v23.0/me?{q}")
    if st != 200 or not isinstance(me, dict):
        print(f"::error::계정 확인 실패 HTTP {st}")
        return 1
    name = me.get("username", "")
    if expect and name != expect:
        print(f"::error::다른 계정으로 승인됨(@{name}). @{expect} 로 로그인한 뒤 다시 승인. 비밀값은 바꾸지 않음")
        return 1
    for k, v in ((f"{prefix}_ACCESS_TOKEN", long_tok), (f"{prefix}_USER_ID", str(me.get("user_id", "")))):
        err = put_secret(pat, k, v)
        if err:
            print(f"::error::{k} 저장 실패: {err}")
            return 1
    print(f"::notice::연결됨 @{name} ({me.get('account_type')}) → 비밀값 {prefix}_ACCESS_TOKEN·{prefix}_USER_ID 저장(60일, token-refresh 가 갱신)")
    return 0



def threads(code: str, secret: str, pat: str, expect: str, prefix: str) -> int:
    """Threads: 코드 → 짧은 토큰 → 장기(60일) 토큰 → @아이디 확인 → <prefix>_ACCESS_TOKEN 저장."""
    if not (code and secret and pat):
        print("::error::code·THREADS_APP_SECRET·GH_SECRETS_PAT 중 빠진 것이 있음")
        return 1
    print(f"::add-mask::{code}")
    st, r = post_form("https://graph.threads.net/oauth/access_token",
                      {"client_id": TH_APP_ID, "client_secret": secret, "grant_type": "authorization_code",
                       "redirect_uri": REDIRECT, "code": code})
    short = r.get("access_token") if isinstance(r, dict) else None
    if st != 200 or not short:
        err = (r.get("error") or {}).get("message", "") if isinstance(r, dict) and isinstance(r.get("error"), dict) else r.get("error_message", "") if isinstance(r, dict) else ""
        print(f"::error::코드 교환 실패 HTTP {st}: {str(err)[:200]} — 코드는 1시간·1회용이니 승인을 다시 하고 새 코드로")
        return 1
    print(f"::add-mask::{short}")
    q = urllib.parse.urlencode({"grant_type": "th_exchange_token", "client_secret": secret, "access_token": short})
    st, r = http("GET", f"https://graph.threads.net/access_token?{q}")
    long_tok = (r or {}).get("access_token") if isinstance(r, dict) else None
    if st != 200 or not long_tok:
        print(f"::error::장기 토큰 교환 실패 HTTP {st}")
        return 1
    print(f"::add-mask::{long_tok}")
    st, me = http("GET", "https://graph.threads.net/v1.0/me?" + urllib.parse.urlencode({"fields": "id,username", "access_token": long_tok}))
    name = me.get("username", "") if isinstance(me, dict) else ""
    if st != 200 or (expect and name != expect):
        print(f"::error::계정 확인 실패(HTTP {st}, @{name}). @{expect} 로 승인했는지 확인. 비밀값은 바꾸지 않음")
        return 1
    err = put_secret(pat, f"{prefix}_ACCESS_TOKEN", long_tok)
    if err:
        print(f"::error::{prefix}_ACCESS_TOKEN 저장 실패: {err}")
        return 1
    print(f"::notice::연결됨 Threads @{name} → 비밀값 {prefix}_ACCESS_TOKEN 저장(60일, token-refresh 가 갱신)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
