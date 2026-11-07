#!/usr/bin/env python3
"""새 리포트를 텔레그램 채널(@drkimworld)에 대표 이미지 + 핵심 3줄 + 리포트 링크로 올린다(운영자 요청 2026-11-06).

- 새 리포트(공개일 3일 안)는 먼저, 그다음 지난 리포트를 하루 BACKFILL_DAILY(기본 3)건씩 채운다(채널을 막 연 터라 읽을거리를 쌓되 도배하지 않게).
- 한 번 실행에 최대 PER_RUN(기본 2)건, 이미 올린 건 다시 올리지 않는다. 기록: social/telegram/posted.json {slug: {"id":…, "at":…}}
- 환경변수: TELEGRAM_BOT_TOKEN(비밀값), TELEGRAM_CHAT(기본 @drkimworld). 선택: SLUG(그 리포트 하나만), DRY=1
- 토큰은 출력하지 않는다(실패 메시지의 주소에서도 지운다).
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "content" / "reports"
STATE = ROOT / "social" / "telegram" / "posted.json"
SITE = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
BASE = SITE["site_url"].rstrip("/")
TICK = yaml.safe_load((ROOT / "data" / "tickers.yaml").read_text(encoding="utf-8")) or {}
ET = ZoneInfo("America/New_York")


def front(p: Path) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", p.read_text(encoding="utf-8"), re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def caption(slug: str, fm: dict) -> str:
    e = lambda x: html.escape(x, quote=False)
    tk = str(fm.get("ticker") or "")
    name = str((TICK.get(tk) or {}).get("name") or fm.get("company") or tk)
    title = str(fm.get("title") or "").split(" | ")[0].strip()
    u = f"{BASE}/r/{slug}/?utm_source=telegram&utm_medium=channel&utm_campaign={slug}"
    kp = [str(x) for x in (fm.get("key_points") or [])][:3]
    lines = [f"<b>{e(title)}</b>", ""]
    lines += [f"• {e(x)}" for x in kp]
    lines += ["", f'👉 <a href="{html.escape(u)}">전체 리포트 무료로 보기</a>', "", f"#{e(tk)} #{e(name.replace(' ', ''))} #미국주식", "<i>투자 권유가 아닌 공개 자료 정리입니다.</i>"]
    c = "\n".join(lines)
    while len(c) > 1000 and kp:  # 사진 설명 한도 1024자
        kp.pop(); lines = [f"<b>{e(title)}</b>", ""] + [f"• {e(x)}" for x in kp] + lines[-5:]; c = "\n".join(lines)
    return c


def send(token: str, chat: str, slug: str, fm: dict) -> int:
    data = urllib.parse.urlencode({"chat_id": chat, "photo": f"{BASE}/og/{slug}.png", "caption": caption(slug, fm), "parse_mode": "HTML"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=data), timeout=60) as r:
            return int(json.load(r)["result"]["message_id"])
    except urllib.error.HTTPError as ex:
        body = ex.read().decode("utf-8", "replace")[:300].replace(token, "***")
        print(f"::error title=텔레그램 {ex.code}::{slug} {body}")
        raise SystemExit(1)


def main() -> int:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT", "@drkimworld").strip()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    today = dt.datetime.now(ET).date()
    per_run, daily = int(os.environ.get("PER_RUN") or 2), int(os.environ.get("BACKFILL_DAILY") or 3)
    want = (os.environ.get("SLUG") or "").strip()
    fresh, old = [], []
    for p in REPORTS.glob("*.md"):
        fm = front(p)
        if p.stem in state or not fm or fm.get("draft") or (want and p.stem != want):
            continue
        try:
            d = dt.date.fromisoformat(str(fm.get("date"))[:10])
        except ValueError:
            continue
        if d > today:
            continue
        (fresh if (today - d).days <= 3 else old).append((d, p.stem, fm))
    fresh.sort(reverse=True); old.sort(reverse=True)
    old_today = sum(1 for v in state.values() if v.get("old") and str(v.get("at", ""))[:10] == today.isoformat())
    todo = fresh + old[: max(0, daily - old_today)]
    todo = todo[:1] if want else todo[:per_run]
    if not todo:
        print(f"올릴 글 없음(새 {len(fresh)}, 지난 {len(old)}, 오늘 채운 지난 글 {old_today}/{daily})"); return 0
    if not token and os.environ.get("DRY") != "1":
        print("::warning title=텔레그램::TELEGRAM_BOT_TOKEN 없음 — 건너뜀"); return 0
    for d, slug, fm in todo:
        if os.environ.get("DRY") == "1":
            print(f"::notice title=미리보기 {slug}::{caption(slug, fm)[:400]}"); continue
        mid = send(token, chat, slug, fm)
        state[slug] = {"id": mid, "at": dt.datetime.now(ET).isoformat(timespec="minutes"), **({"old": True} if (today - d).days > 3 else {})}
        print(f"::notice title=텔레그램 게시::{slug} → https://t.me/{chat.lstrip('@')}/{mid}")
    if os.environ.get("DRY") != "1":
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
