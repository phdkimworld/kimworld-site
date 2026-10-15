#!/usr/bin/env python3
"""Threads·Instagram 장기 토큰(60일)을 갱신해 GitHub 비밀값을 새 토큰으로 바꾼다.

.github/workflows/token-refresh.yml 이 매달 1일·15일에 실행한다.
필요한 비밀값: THREADS_ACCESS_TOKEN, IG_ACCESS_TOKEN, GH_SECRETS_PAT
(GH_SECRETS_PAT = 이 저장소에만 'Secrets: Read and write' 권한을 준 fine-grained 토큰)
토큰 값은 어디에도 출력하지 않는다.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "phdkimworld/kimworld-site")

CHANNELS = [
    # (비밀값 이름, 갱신 주소, grant_type)
    ("THREADS_ACCESS_TOKEN", "https://graph.threads.net/refresh_access_token", "th_refresh_token"),
    ("IG_ACCESS_TOKEN", "https://graph.instagram.com/refresh_access_token", "ig_refresh_token"),
]


def mask(value):
    if value:
        print(f"::add-mask::{value}")


def http(method, url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def refresh(url, grant, token):
    q = urllib.parse.urlencode({"grant_type": grant, "access_token": token})
    status, resp = http("GET", f"{url}?{q}")
    new = resp.get("access_token")
    if status != 200 or not new:
        err = resp.get("error", {})
        # 토큰이 들어갈 수 있는 필드는 빼고 오류 종류만 남긴다
        return None, f"HTTP {status} {err.get('type', '')} code={err.get('code', '')}: {err.get('message', '')}"
    return new, resp.get("expires_in")


def github_headers(pat):
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "kimworld-token-refresh",
    }


def put_secret(pat, name, value):
    from nacl import encoding, public  # PyNaCl

    h = github_headers(pat)
    status, key = http("GET", f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", h)
    if status != 200:
        return f"공개키 조회 실패 HTTP {status} (GH_SECRETS_PAT 권한 확인)"
    pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(value.encode())
    body = {"encrypted_value": base64.b64encode(sealed).decode(), "key_id": key["key_id"]}
    status, _ = http("PUT", f"https://api.github.com/repos/{REPO}/actions/secrets/{name}", h, body)
    if status not in (201, 204):
        return f"비밀값 저장 실패 HTTP {status}"
    return None


def main():
    pat = os.environ.get("GH_SECRETS_PAT", "")
    mask(pat)
    if not pat:
        print("::error::GH_SECRETS_PAT 비밀값이 없습니다. social/README.md '토큰 자동 갱신'을 보고 등록하세요.")
        return 1

    failed = 0
    for name, url, grant in CHANNELS:
        token = os.environ.get(name, "")
        mask(token)
        if not token:
            print(f"::warning::{name} 비밀값이 없어 건너뜀")
            continue
        new, info = refresh(url, grant, token)
        if not new:
            print(f"::error::{name} 갱신 실패 — {info}")
            failed += 1
            continue
        mask(new)
        err = put_secret(pat, name, new)
        if err:
            print(f"::error::{name} {err}")
            failed += 1
            continue
        days = f"{int(info) // 86400}일" if isinstance(info, (int, float)) else "알 수 없음"
        print(f"{name} 갱신 완료 (새 만료까지 약 {days})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
