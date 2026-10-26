#!/usr/bin/env python3
"""새 리포트를 구글 블로거(김박사 월드 노트)에 짧은 소개 글로 올린다.

운영자 요청 2026-10-25(구글 노출 보조). 리포트를 그대로 옮기지 않는다: 요약·핵심 3줄·차트·영상·리포트 링크만.
스팸처럼 보이지 않도록 하루 최대 BLOGGER_DAILY(기본 2)건, 공개 7일 이내 리포트만, 이미 올린 건 다시 올리지 않는다.
올린 기록: social/blogger/posted.json {slug: {"url":…, "at":…}} (공개 저장소에는 주소·시각만)

환경변수: GOOGLE_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID
선택: SLUG(그 리포트 하나만), DRY=1(올리지 않고 내용만 출력), BLOGGER_DAILY
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "content" / "reports"
STATE = ROOT / "social" / "blogger" / "posted.json"
SITE = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
BASE = SITE["site_url"].rstrip("/")
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")


def front(p: Path) -> dict:
    t = p.read_text(encoding="utf-8")
    if not t.startswith("---"):
        return {}
    return yaml.safe_load(t.split("---", 2)[1]) or {}


def short_title(fm: dict) -> str:
    t = str(fm.get("title") or "").split(" | ")[0].strip()
    return t[:140]


def body(slug: str, fm: dict) -> str:
    u = f"{BASE}/r/{slug}/?utm_source=blogger&utm_medium=post&utm_campaign={slug}"
    e = html.escape
    tk = e(str(fm.get("ticker") or ""))
    parts = [
        f'<p><a href="{u}"><img src="{BASE}/og/{slug}.png" alt="{tk} 리포트 대표 이미지" style="max-width:100%;height:auto;border-radius:8px"></a></p>',
        f"<p>{e(str(fm.get('summary') or ''))}</p>",
    ]
    kp = [str(x) for x in (fm.get("key_points") or [])][:3]
    if kp:
        parts.append("<h3>핵심 3줄</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in kp) + "</ul>")
    parts.append(
        f'<p style="margin:20px 0"><a href="{u}" style="display:inline-block;padding:12px 18px;background:#f59e0b;color:#111;'
        f'border-radius:10px;font-weight:700;text-decoration:none">이벤트 카드·반복 패턴·체크리스트까지 전체 리포트 무료로 보기 →</a></p>'
    )
    yid = str(fm.get("youtube_id") or "").strip()
    if len(yid) == 11:
        parts.append(
            f'<p>영상으로 먼저 보기:</p><iframe width="560" height="315" style="max-width:100%" '
            f'src="https://www.youtube.com/embed/{yid}" title="{tk} 영상" frameborder="0" allowfullscreen></iframe>'
        )
    parts.append(
        f'<p style="color:#888;font-size:13px">숫자 기준일 {e(str(fm.get("data_as_of") or ""))}. '
        "공개 자료를 정리한 교육용 글이며 특정 종목의 매매를 권하지 않습니다. "
        f'다른 종목 리포트: <a href="{BASE}/?utm_source=blogger&utm_medium=post">김박사 월드</a></p>'
    )
    return "\n".join(parts)


def token() -> str:
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
        "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=30) as r:
        return json.load(r)["access_token"]


def publish(tok: str, title: str, content: str, labels: list) -> str:
    bid = os.environ["BLOGGER_BLOG_ID"]
    req = urllib.request.Request(
        f"https://www.googleapis.com/blogger/v3/blogs/{bid}/posts/",
        data=json.dumps({"kind": "blogger#post", "title": title, "content": content, "labels": labels}).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("url", "")


def live(slug: str) -> bool:
    try:
        req = urllib.request.Request(f"{BASE}/r/{slug}/", method="HEAD", headers={"User-Agent": "kimworld-blogger"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    now = dt.datetime.now(ET)
    today = now.date()
    daily = int(os.environ.get("BLOGGER_DAILY") or 2)
    done_today = sum(1 for v in state.values() if str(v.get("at", ""))[:10] == today.isoformat())
    want = (os.environ.get("SLUG") or "").strip()
    cands = []
    for p in sorted(REPORTS.glob("*.md")):
        slug = p.stem
        if slug in state or (want and slug != want):
            continue
        fm = front(p)
        if not fm or fm.get("draft"):
            continue
        try:
            d = dt.date.fromisoformat(str(fm.get("date"))[:10])
        except ValueError:
            continue
        if d > today or (not want and (today - d).days > 7):
            continue
        cands.append((d, slug, fm))
    cands.sort(reverse=True)  # 최신 먼저
    room = 1 if want else max(0, daily - done_today)
    if not cands or room == 0:
        print(f"올릴 글 없음(후보 {len(cands)}, 오늘 {done_today}/{daily})")
        return 0
    dry = os.environ.get("DRY") == "1"
    tok = None if dry else token()
    n = 0
    for d, slug, fm in cands:
        if n >= room:
            break
        if not dry and not live(slug):
            print(f"{slug}: 아직 사이트에 안 열림, 건너뜀")
            continue
        title = short_title(fm)
        labels = [x for x in [str(fm.get("ticker") or ""), str(fm.get("theme") or ""), "미국주식"] if x]
        content = body(slug, fm)
        if dry:
            print(title, labels, content[:400], sep="\n")
            n += 1
            continue
        url = publish(tok, title, content, labels)
        state[slug] = {"url": url, "at": now.isoformat(timespec="minutes")}
        print(f"::notice title=블로거 게시::{slug} → {url}")
        n += 1
    if not dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
