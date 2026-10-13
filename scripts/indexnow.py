"""새로 생기거나 바뀐 주소를 IndexNow로 빙·네이버(그리고 IndexNow 참여 검색엔진)에 바로 알린다.

사용
  python scripts/indexnow.py diff dist/sitemap.xml > /tmp/indexnow.txt   # 배포 전: 지금 공개된 사이트맵과 비교
  python scripts/indexnow.py submit /tmp/indexnow.txt                  # 배포 뒤: 알리기

- 키는 site.yaml 의 seo.indexnow_key (공개값, /<키>.txt 로 공개된다).
- 매시 빌드에서도 바뀐 것이 없으면 아무것도 보내지 않는다. 처음(공개 사이트맵에 키 파일이 없을 때)은 전체를 보낸다.
- 구글은 IndexNow를 쓰지 않는다. 구글은 서치 콘솔에 제출한 사이트맵을 읽는다.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = ["https://api.indexnow.org/indexnow", "https://searchadvisor.naver.com/indexnow"]


def site():
    return yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))


def entries(xml: str) -> dict:
    out = {}
    for m in re.finditer(r"<url><loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", xml):
        out[m.group(1)] = m.group(2) or ""
    return out


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "kimworld-indexnow"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def diff(new_path: str):
    s = site()
    su = s["site_url"].rstrip("/")
    new = entries(Path(new_path).read_text(encoding="utf-8"))
    try:
        old = entries(fetch(f"{su}/sitemap.xml"))
    except Exception as e:  # 처음이거나 접속 실패: 전체를 보낸다
        print(f"공개 사이트맵을 못 읽음({e}) → 전체", file=sys.stderr)
        old = {}
    key = str((s.get("seo") or {}).get("indexnow_key") or "")
    if key and old:
        try:
            if fetch(f"{su}/{key}.txt").strip() != key:
                old = {}
        except Exception:
            old = {}  # 키 파일이 아직 공개 전이면 이번 배포가 첫 제출
    changed = [u for u, lm in new.items() if old.get(u) != lm]
    print("\n".join(changed))
    print(f"알릴 주소 {len(changed)}개", file=sys.stderr)


def submit(list_path: str):
    s = site()
    key = str((s.get("seo") or {}).get("indexnow_key") or "")
    urls = [u.strip() for u in Path(list_path).read_text(encoding="utf-8").splitlines() if u.strip()]
    if not key or not urls:
        print("보낼 것 없음")
        return
    host = re.sub(r"^https?://", "", s["site_url"]).strip("/")
    body = json.dumps({"host": host, "key": key, "keyLocation": f"{s['site_url'].rstrip('/')}/{key}.txt",
                       "urlList": urls[:10000]}).encode()
    for ep in ENDPOINTS:
        req = urllib.request.Request(ep, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"{ep}: {r.status} ({len(urls)}개)")
        except urllib.error.HTTPError as e:
            print(f"::warning::{ep}: HTTP {e.code} {e.read()[:200]!r}")
        except Exception as e:
            print(f"::warning::{ep}: {e}")


if __name__ == "__main__":
    {"diff": diff, "submit": submit}[sys.argv[1]](sys.argv[2])
