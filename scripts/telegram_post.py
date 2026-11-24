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
_CL = ROOT / "data" / "cheer_links.yaml"
MALL = "https://drkimworld.com/mall/?utm_source=telegram&utm_medium=social&utm_content=mall"
CHEER = str((yaml.safe_load(_CL.read_text(encoding="utf-8")) or {}).get("telegram") or "") if _CL.exists() else ""  # 쿠팡 채널 응원 링크(2026-11-16)


def front(p: Path) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", p.read_text(encoding="utf-8"), re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def health_guide(slug: str):
    """사이트 ads.yaml house.health.guides 중 하나(글 slug로 돌림) → (이름, 주소) 또는 None."""
    import hashlib
    hh = ((yaml.safe_load((ROOT / "ads.yaml").read_text(encoding="utf-8")) or {}).get("house") or {}).get("health") or {}
    gs = [g for g in hh.get("guides") or [] if isinstance(g, dict) and g.get("slug") and g.get("name")]
    if not (gs and str(hh.get("base") or "").startswith("https://")):
        return None
    g = gs[int(hashlib.md5(slug.encode("utf-8")).hexdigest(), 16) % len(gs)]
    return str(g["name"]), f'{str(hh["base"]).rstrip("/")}/guide/{g["slug"]}/?utm_source=telegram&utm_medium=channel&utm_campaign={slug}#items'


def _short(kp: str, n: int = 110) -> str:
    """핵심 줄 하나를 휴대폰 두세 줄로: 첫 문장만, ' · ' 나열은 앞 세 개만(숫자는 원문 그대로 — 새 숫자를 만들지 않는다)."""
    x = re.split(r"(?<=[.다])\s", kp.strip(), maxsplit=1)[0]
    head, sep, rest = x.partition(": ")
    body = rest if sep else x
    items = body.split(" · ")
    if len(items) > 3:
        body = " · ".join(items[:3]) + " 등"
    out = (head + sep + body) if sep else body
    if len(out) <= n:
        return out
    cut = out[:n]  # 쉼표 경계에서 자르고 '등'(날짜·값 범위를 반쪽만 남기지 않게)
    i = max(cut.rfind(", "), cut.rfind(" · "))
    return cut[:i] + " 등" if i > n // 2 else cut.rsplit(" ", 1)[0] + "…"


def caption(slug: str, fm: dict) -> str:
    """2026-11-24 SNS 디자인 학습: 굵은 첫 줄(종목·질문) → 모순 한 줄 → 이름표 붙은 핵심 세 줄(각 두세 줄 이내) → 해시태그·고지.
    리포트 주소는 글 속 링크 대신 아래 버튼(reply_markup, button())으로 — 큰 채널들이 쓰는 '글은 짧게, 행동은 버튼 하나' 꼴."""
    e = lambda x: html.escape(x, quote=False)
    tk = str(fm.get("ticker") or "")
    name = str((TICK.get(tk) or {}).get("name") or fm.get("company") or tk)
    title = str(fm.get("title") or "").split(" | ")[0].strip()
    q, _, why = title.partition(" — ")
    kp = [str(x) for x in (fm.get("key_points") or [])][:3]
    lines = [f"<b>{e(q)}</b>"] + ([e(why)] if why else []) + [""]
    for x in kp:
        head, sep, rest = _short(x).partition(": ")
        lines.append(f"▪️ <b>{e(head)}</b> {e(rest)}" if sep and len(head) <= 8 else f"▪️ {e(_short(x))}")
    # 2026-11-19 운영자 "김박사 몰부터" → 2026-11-23 "랜딩페이지를 하나만 쓰자": 몰 줄 뺌(몰은 사이트 안에서만)
    cheer = []
    hg = health_guide(slug)  # 2026-11-22 "광고 꽉꽉": 김박사 건강몰 가이드 한 줄(영상 중간광고와 같은 세 성분, 질병명·효능 단정 없음)
    if hg:
        cheer.append(f'💊 <a href="{html.escape(hg[1])}">{e(hg[0])} 고르는 법</a> — 식약처 인정 문구와 연구 숫자로 정리한 건강몰 가이드')
    tail = [f"#{e(tk)} #{e(name.replace(' ', ''))} #미국주식", "<i>투자 권유가 아닌 공개 자료 정리입니다." + (" 쿠팡 파트너스 활동으로 일정액의 수수료를 받습니다." if cheer else "") + "</i>"]
    c = "\n".join(lines + [""] + cheer + ([""] if cheer else []) + tail)
    while len(c) > 1000 and len(lines) > 2:  # 사진 설명 한도 1024자
        lines.pop(); c = "\n".join(lines + [""] + cheer + [""] + tail)
    return c


def report_url(slug: str) -> str:
    return f"{BASE}/r/{slug}/?utm_source=telegram&utm_medium=channel&utm_campaign={slug}"


def button(slug: str) -> str:
    """글 아래 버튼 하나(전체 리포트). 텔레그램 Bot API inline_keyboard url 버튼."""
    return json.dumps({"inline_keyboard": [[{"text": "📊 전체 리포트 무료로 보기", "url": report_url(slug)}]]}, ensure_ascii=False)


def send(token: str, chat: str, slug: str, fm: dict) -> int:
    data = urllib.parse.urlencode({"chat_id": chat, "photo": f"{BASE}/og/{slug}.png", "caption": caption(slug, fm), "parse_mode": "HTML", "reply_markup": button(slug)}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=data), timeout=60) as r:
            return int(json.load(r)["result"]["message_id"])
    except urllib.error.HTTPError as ex:
        body = ex.read().decode("utf-8", "replace")[:300].replace(token, "***")
        if ex.code == 400 and ("HTTP URL content" in body or "wrong type of the web page content" in body or "IMAGE_PROCESS_FAILED" in body):
            # 텔레그램이 대표 그림(/og/<slug>.png)을 못 받아 오면 같은 글을 그림 없이(링크 미리보기로) 보낸다(2026-11-17: btq-2026-11-3에서 5회 연속 실패)
            print(f"::warning title=텔레그램 그림 실패::{slug} 그림 없이 글로 보냄")
            msg = urllib.parse.urlencode({"chat_id": chat, "text": caption(slug, fm), "parse_mode": "HTML", "reply_markup": button(slug)}).encode()
            try:
                with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=msg), timeout=60) as r:
                    return int(json.load(r)["result"]["message_id"])
            except urllib.error.HTTPError as ex2:
                body = ex2.read().decode("utf-8", "replace")[:300].replace(token, "***")
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
