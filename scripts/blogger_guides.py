"""블로거 '구매 의도' 비교 글(운영자 지시 2026-11-16 "우리 채널로 해볼만한걸 다 해봐" — 쿠팡 파트너스 벤치마킹: 사려는 사람이 검색하는 비교 글이 전환이 높다).

- 글 원고: social/blogger/guides/<id>.yaml (제목·라벨·도입·고르는 기준·항목별 쿠팡 검색어·맺음말)
- 상품: 항목마다 쿠팡 검색 API 상위 결과 하나(must 낱말이 이름에 있어야), 단축 링크는 하위 ID(bg…)로. 쿠팡 실적에서 '블로거' 칸·비공개 by_sub로 따로 센다.
- 쿠팡 검색 API는 시간당 10회(사이트 동기화 7 + 유튜브 2 몫) → 실행마다 GUIDE_SEARCHES(기본 1)개만 찾고 social/blogger/guides/state.json에 쌓는다. 다 차면 게시.
- 이미 올린 글은 다시 올리지 않는다(state의 url). 상품 이름·가격은 게시 글과 상태 파일에만 둔다(공개 로그에는 남기지 않음).
- 글 첫머리에 대가성 문구(공정위 추천·보증 심사지침), 링크는 rel="sponsored nofollow".
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yt_shop as ys  # noqa: E402  (search_raw·shorten·is_book 재사용)

GDIR = ROOT / "social" / "blogger" / "guides"
STATE = GDIR / "state.json"
DISCLOSURE = "이 글은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SITE = "https://drkimworld.com/?utm_source=blogger&utm_medium=guide"
YT = "https://www.youtube.com/@drkimworld"


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def guides() -> list[dict]:
    out = []
    for p in sorted(GDIR.glob("*.yaml")):
        g = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        g["id"] = p.stem
        out.append(g)
    return out


def items_of(g: dict) -> list[dict]:
    return [it for sec in g.get("sections") or [] for it in sec.get("items") or []]


def fill_one(g: dict, st: dict, access: str, secret: str) -> bool:
    """비어 있는 항목 하나를 쿠팡 검색으로 채운다. 채웠으면 True."""
    got = st.setdefault(g["id"], {}).setdefault("items", {})
    for it in items_of(g):
        kw = it["kw"]
        if kw in got:
            continue
        rows = ys.search_raw(kw, g["subid"], access, secret)
        must = str(it.get("must") or "").replace(" ", "")
        pick = None
        for x in rows:
            name = str(x.get("productName") or "")
            if must and must not in name.replace(" ", ""):
                continue
            if g.get("books_only") and not ys.is_book(x):
                continue
            pick = x
            break
        c = ys.pick([pick], False, 1) if pick else []
        if c:
            try:
                ys.shorten(c, g["subid"], access, secret)
            except Exception as e:
                print(f"::warning title=블로거 비교 글::단축 링크 실패 {type(e).__name__}(긴 링크 그대로)")
            got[kw] = {k: c[0].get(k) for k in ("name", "url", "price", "image")}
        else:
            got[kw] = {"missing": True}
        return True
    return False


def render(g: dict, got: dict) -> str:
    e = lambda s: html.escape(str(s), quote=True)
    today = dt.date.today()
    h = [f'<p style="color:#888;font-size:13px">{e(DISCLOSURE)}</p>']
    h += [f"<p>{e(p)}</p>" for p in g.get("intro") or []]
    if g.get("criteria"):
        h.append("<h2>고르는 기준</h2><ul>" + "".join(f"<li>{e(c)}</li>" for c in g["criteria"]) + "</ul>")
    for sec in g.get("sections") or []:
        h.append(f"<h2>{e(sec['heading'])}</h2>")
        if sec.get("text"):
            h.append(f"<p>{e(sec['text'])}</p>")
        for it in sec.get("items") or []:
            p = got.get(it["kw"]) or {}
            if p.get("missing") or not p.get("url"):
                continue
            img = f'<img src="{e(p["image"])}" alt="{e(it.get("label") or p["name"])}" style="width:120px;height:120px;object-fit:contain;flex:none;border-radius:8px;background:#fff" loading="lazy">' if p.get("image") else ""
            price = f'<span style="color:#888;font-size:13px">쿠팡 가격 {int(p["price"]):,}원({today.month}월 {today.day}일 기준, 바뀔 수 있음)</span><br>' if p.get("price") else ""
            h.append(
                '<div style="display:flex;gap:14px;align-items:flex-start;border:1px solid #e3e3e3;border-radius:12px;padding:14px;margin:14px 0">'
                f'{img}<div><strong>{e(it.get("label") or p["name"])}</strong><br>'
                f'<span style="font-size:14px">{e(it.get("note", ""))}</span><br>{price}'
                f'<a href="{e(p["url"])}" rel="sponsored nofollow noopener" target="_blank" '
                'style="display:inline-block;margin-top:8px;padding:8px 14px;border-radius:999px;background:#f5b83d;color:#0e1a2b;font-weight:700;text-decoration:none">쿠팡에서 가격·후기 보기</a></div></div>')
    h += [f"<p>{e(p)}</p>" for p in g.get("outro") or []]
    h.append(f'<p>미국 주식 종목별로 주가가 크게 움직인 날과 그 이유를 정리한 무료 리포트는 <a href="{SITE}">김박사 월드</a>에, 영상은 <a href="{YT}">유튜브 김박사 월드</a>에 있습니다.</p>')
    h.append(f'<p style="color:#888;font-size:12px">{e(DISCLOSURE)} 상품 선택은 고르는 기준을 설명하기 위한 예시이며, 가격·재고·사양은 쿠팡 상품 페이지에서 확인하세요.</p>')
    return "\n".join(h)


def main() -> int:
    access, secret = os.environ.get("COUPANG_ACCESS_KEY", "").strip(), os.environ.get("COUPANG_SECRET_KEY", "").strip()
    if not (access and secret):
        print("::notice title=블로거 비교 글::쿠팡 키 없음, 건너뜀")
        return 0
    st, budget, dry = load_state(), int(os.environ.get("GUIDE_SEARCHES") or 1), os.environ.get("DRY") == "1"
    changed = False
    for g in guides():
        s = st.setdefault(g["id"], {})
        if s.get("url"):
            continue
        while budget > 0:
            try:
                if not fill_one(g, st, access, secret):
                    break
                changed, budget = True, budget - 1
            except urllib.error.HTTPError as ex:
                print(f"::warning title=블로거 비교 글::검색 HTTP {ex.code}" + (" (시간당 한도)" if ex.code == 429 else ""))
                budget = 0
        got = s.get("items") or {}
        if any(it["kw"] not in got for it in items_of(g)):
            print(f"::notice title=블로거 비교 글::{g['id']} 상품 {len(got)}/{len(items_of(g))} 채움")
            continue
        content = render(g, got)
        if dry:
            print(f"::notice title=블로거 비교 글 미리보기::{g['id']} {len(content)}자")
            continue
        import blogger_post as bp
        url = bp.publish(bp.token(), g["title"], content, g.get("labels") or [], g.get("title_en", ""))
        s["url"], s["at"] = url, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        changed = True
        print(f"::notice title=블로거 비교 글 게시::{g['id']} {url}")
        time.sleep(5)
    if changed:
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
