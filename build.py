#!/usr/bin/env python3
"""김박사 월드 정적 사이트 생성기.

  python3 build.py            # 공개 리포트만 빌드 → dist/
  python3 build.py --drafts   # 초안까지 빌드(초안은 noindex, 목록·사이트맵 제외, 주소로만 열림)
  python3 build.py --strict   # 경고도 실패로 처리(CI에서 사용)

입력:  site.yaml, ads.yaml, data/*.yaml, content/reports/*.md, content/pages/*.md, templates/, static/
출력:  dist/ (GitHub Pages가 그대로 서비스)
"""
from __future__ import annotations

import os

import argparse
import datetime as dt
import html
import json
import math
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
KST = dt.timezone(dt.timedelta(hours=9))

REQUIRED = ["ticker", "title", "theme", "date", "data_as_of", "summary", "sources"]
COUPANG_DISCLOSURE = "이 영역은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
COUPANG_PAGE_NOTICE = "이 페이지에는 쿠팡 파트너스 링크가 포함되어 있습니다."
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
ADSENSE_CLIENT_RE = re.compile(r"^ca-pub-\d{10,20}$")
ADFIT_RE = re.compile(r"^DAN-[A-Za-z0-9]+$")


class BuildError(Exception):
    pass


class Log:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)


# ---------------------------------------------------------------- 읽기

def load_yaml(p: Path, default=None):
    if not p.exists():
        return default
    return yaml.safe_load(p.read_text(encoding="utf-8")) or default


def parse_front(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        raise BuildError(f"{path.relative_to(ROOT)}: 맨 위에 --- 로 감싼 머리말이 없습니다.")
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def to_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v).strip())


def md_renderer():
    return markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "footnotes", "toc"],
        extension_configs={"toc": {"slugify": slugify_unicode, "toc_depth": "2-3"}},
    )


# ---------------------------------------------------------------- 본문 가공

SKIP_TAGS = {"a", "summary", "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "th", "button", "sup", "script", "style"}


def apply_glossary(body_html: str, glossary: list[dict]) -> tuple[str, list[dict]]:
    """각 용어가 처음 나오는 본문 텍스트에 표시를 단다(제목·링크·코드·표 머리 제외)."""
    used = []
    remaining = []
    for g in glossary:
        t = str(g["term"])
        if re.fullmatch(r"[A-Za-z0-9/\-.]+", t):
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])")
        else:
            pat = re.compile(re.escape(t))
        remaining.append((t, str(g["def"]), pat))
    parts = re.split(r"(<[^>]+>)", body_html)
    stack: list[str] = []
    out = []
    for part in parts:
        if part.startswith("<"):
            m = re.match(r"<\s*(/)?\s*([a-zA-Z0-9]+)", part)
            if m:
                tag = m.group(2).lower()
                if m.group(1):
                    if tag in stack:
                        while stack and stack.pop() != tag:
                            pass
                elif not part.endswith("/>") and tag in SKIP_TAGS:
                    stack.append(tag)
            out.append(part)
            continue
        if stack or not part.strip() or not remaining:
            out.append(part)
            continue
        # 한 텍스트 조각 안에서 아직 안 쓴 용어를 하나씩 찾는다
        text = part
        changed = True
        while changed and remaining:
            changed = False
            best = None
            for i, (t, d, pat) in enumerate(remaining):
                m = pat.search(text) if "\x00" not in text else None
                if m and (best is None or m.start() < best[1].start()):
                    best = (i, m)
            if best:
                i, m = best
                t, d, _ = remaining.pop(i)
                tid = f"term-{len(used)}"
                used.append({"term": t, "def": d, "id": tid})
                text = text[: m.start()] + f"\x00{len(used)-1}\x00" + text[m.end():]
                changed = True
        def put(mm):
            u = used[int(mm.group(1))]
            return (
                f'<button type="button" class="term" aria-describedby="{u["id"]}" data-def="{html.escape(u["def"], quote=True)}">'
                f'{html.escape(u["term"])}</button>'
            )
        out.append(re.sub(r"\x00(\d+)\x00", put, text))
    return "".join(out), used


def ad_weights(ads) -> dict:
    """쿠팡 상자 학습 자료(정적 파일, 매시 빌드 때 갱신). 브라우저가 이걸 보고 묶음을 고른다(API 부담 없음).
    - 노출·클릭: Cloudflare 기록(.cache/ad_stats.json, 지난 30일) → 묶음별 합계, 이용 환경별(s), 자리별(l)
    - 수수료: 쿠팡 실적(.cache/coupang_reports.json, 지난 30일) → 묶음별 주문·수수료"""
    def load(name):
        try:
            return json.loads((ROOT / ".cache" / name).read_text(encoding="utf-8"))
        except Exception:
            return {}
    raw = load("ad_stats.json")
    rows = raw[0].get("results", []) if isinstance(raw, list) and raw else (raw.get("results", []) if isinstance(raw, dict) else [])
    rep = load("coupang_reports.json").get("by_sub", {})
    g: dict[str, dict] = {}
    for gs in ads.c_auto.values():
        for x in gs:
            sid = str(x.get("sub_id") or "")
            if sid:
                g[sid] = {"t": ads.theme_slug.get(x.get("theme"), ""), "i": 0, "c": 0, "s": {}, "l": {}}
    tot_i = tot_c = 0
    for r in rows:
        sid = str(r.get("g") or "")
        i, c = int(r.get("imps") or 0), int(r.get("clicks") or 0)
        tot_i += i; tot_c += c
        if sid not in g:
            continue
        e = g[sid]; e["i"] += i; e["c"] += c
        for key, k in (("s", str(r.get("seg") or "")), ("l", str(r.get("slot") or ""))):
            v = e[key].setdefault(k, [0, 0]); v[0] += i; v[1] += c
    tot_r = 0.0
    for sid, v in rep.items():
        if sid in g:
            g[sid]["r"] = round(float(v.get("commission") or 0)); g[sid]["o"] = int(v.get("orders") or 0)
        tot_r += float(v.get("commission") or 0)
    ctr = (tot_c + 2) / (tot_i + 100)                      # 전체 클릭률(자료가 적으면 2%에 가깝게)
    epc = (tot_r / tot_c) if tot_c and tot_r else 0.0      # 클릭 1번당 평균 수수료(실적이 있을 때만)
    return {"v": 1, "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "prior": {"ctr": round(ctr, 5), "n": 40}, "epc": round(epc, 2), "explore": 0.1, "g": g}


def chart_info(slug: str) -> dict | None:
    """피드 카드에 붙일 대표 차트(static/charts/<slug>.png)와 크기(레이아웃 밀림 방지)."""
    f = ROOT / "static" / "charts" / f"{slug}.png"
    if not f.exists():
        return None
    try:
        from PIL import Image
        with Image.open(f) as im:
            w, h = im.size
    except Exception:
        w, h = 1080, 1080
    return {"src": f"/static/charts/{slug}.png", "w": w, "h": h}


def wrap_tables(html_in: str, extra: str = "") -> str:
    """표를 가로 스크롤 상자로 감싼다(표 자체는 폭을 꽉 채우고, 넘칠 때만 상자 안에서 밀린다)."""
    cls = ("table-wrap " + extra).strip()
    if "table-text" in extra:
        # 글 위주 표(개인정보처리방침 등): 휴대폰에서 칸마다 머리글을 붙인 카드로 보이도록 data-label을 단다
        def label(tm: re.Match) -> str:
            t = tm.group(0)
            heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", t, flags=re.S)]
            def row(rm: re.Match) -> str:
                i = iter(heads)
                return re.sub(r"<td(\s[^>]*)?>", lambda m: f'<td data-label="{html.escape(next(i, ""))}"{m.group(1) or ""}>', rm.group(0))
            return re.sub(r"<tr>.*?</tr>", row, t, flags=re.S)
        html_in = re.sub(r"<table>.*?</table>", label, html_in, flags=re.S)
    return html_in.replace("<table>", f'<div class="{cls}"><table>').replace("</table>", "</table></div>")


def fold_event_cards(body_html: str) -> str:
    """'이벤트 카드' 부의 연도별 묶음(### 2026년 …)을 접힌 상자로 바꾼다. 모바일에서 길이를 줄이기 위해서다."""
    h2s = [m.start() for m in re.finditer(r"<h2[\s>]", body_html)]
    for i, pos in enumerate(h2s):
        end_h = body_html.find("</h2>", pos)
        if "이벤트 카드" not in body_html[pos:end_h]:
            continue
        sec_end = h2s[i + 1] if i + 1 < len(h2s) else len(body_html)
        sec = body_html[pos:sec_end]
        h3 = list(re.finditer(r'<h3( id="[^"]*")?>(.*?)</h3>', sec, flags=re.S))
        out, last = [], 0
        for j, m in enumerate(h3):
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not re.match(r"\d{4}", title):
                continue
            stop = h3[j + 1].start() if j + 1 < len(h3) else len(sec)
            inner = sec[m.end():stop]
            n = len(re.findall(r"<p><strong>\d{4}\.\d{1,2}", inner))
            cnt = f' <span class="fold-n">카드 {n}장</span>' if n else ""
            out.append(sec[last:m.start()])
            out.append(f'<details class="fold"{m.group(1) or ""}><summary><span class="fold-t">{title}</span>{cnt}</summary>{inner}</details>\n')
            last = stop
        out.append(sec[last:])
        return body_html[:pos] + "".join(out) + body_html[sec_end:]
    return body_html


def split_for_ads(body_html: str, want_mid: bool, want_products: bool, want_late: bool = False) -> list[tuple[str, str]]:
    """본문을 광고 자리에서 나눈다. 반환: [("html", 조각) | ("ad", 자리이름)]
    want_late: 긴 리포트에서 본문 4분의 3쯤 소제목 앞에 한 자리 더(가운데 광고와 끝 광고 사이가 너무 멀지 않게)."""
    h2 = [m.start() for m in re.finditer(r"<h2[\s>]", body_html)]
    mid = h2[2] if want_mid and len(h2) >= 3 else -1
    prod = -1
    if want_products:
        prod = len(body_html)
        found = False
        for i, pos in enumerate(h2):
            end = body_html.find("</h2>", pos)
            if "운영자 판단" in body_html[pos:end]:
                prod = h2[i + 1] if i + 1 < len(h2) else len(body_html)
                found = True
                break
        if not found:
            # "운영자 판단"이 없는 긴 리포트는 본문 한가운데에 가장 가까운 소제목 앞에 둔다(끝의 광고와 몰리지 않게)
            later = [p for p in h2 if p > mid + 1]
            if later:
                prod = min(later, key=lambda p: abs(p - len(body_html) / 2))
        if prod == mid:
            prod = -1  # 두 광고가 붙으면 아래쪽을 끈다
    late = -1
    if want_late:
        cands = [p for p in h2 if p > max(mid, prod) + 1 and p < len(body_html) * 0.9]
        if cands:
            late = min(cands, key=lambda p: abs(p - len(body_html) * 0.75))
    cuts = sorted([(p, n) for p, n in ((mid, "report_mid"), (prod, "report_products"), (late, "report_late")) if p >= 0])
    out, last = [], 0
    for p, n in cuts:
        if p > last:
            out.append(("html", body_html[last:p]))
        out.append(("ad", n))
        last = p
    if last < len(body_html):
        out.append(("html", body_html[last:]))
    return out


def plain_len(s: str) -> int:
    return len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", s)))


# ---------------------------------------------------------------- 광고

class Ads:
    def __init__(self, cfg: dict, log: Log):
        self.cfg = cfg or {}
        self.on = bool(self.cfg.get("enabled", True))
        self.log = log
        a = self.cfg.get("adsense") or {}
        self.adsense_client = str(a.get("client") or "").strip()
        if self.adsense_client and not ADSENSE_CLIENT_RE.match(self.adsense_client):
            log.err(f"ads.yaml adsense.client 형식 오류: ca-pub- 뒤에 숫자가 와야 합니다")
            self.adsense_client = ""
        self.adsense_slots = {k: str(v or "").strip() for k, v in (a.get("slots") or {}).items()}
        for k, v in self.adsense_slots.items():
            if v and not v.isdigit():
                log.err(f"ads.yaml adsense.slots.{k} 는 숫자여야 합니다")
                self.adsense_slots[k] = ""
        f = self.cfg.get("adfit") or {}
        self.adfit_w = int(f.get("width") or 320)
        self.adfit_h = int(f.get("height") or 100)
        # 단위마다 크기가 다를 수 있다(예: 본문 중간 300x250). 없으면 width/height
        self.adfit_sizes = {k: (int(v[0]), int(v[1])) for k, v in (f.get("sizes") or {}).items() if isinstance(v, (list, tuple)) and len(v) == 2}
        self.adfit_units = {k: str(v or "").strip() for k, v in (f.get("units") or {}).items()}
        for k, v in self.adfit_units.items():
            if v and not ADFIT_RE.match(v):
                log.err(f"ads.yaml adfit.units.{k} 형식 오류(DAN-로 시작)")
                self.adfit_units[k] = ""
        c = self.cfg.get("coupang") or {}
        self.c_allowed = [d.lower() for d in (c.get("allowed_domains") or ["coupang.com", "coupangcdn.com"])]
        self.c_banner = str(c.get("banner_html") or "").strip()
        self.c_banner_h = int(c.get("banner_height") or 140)
        if self.c_banner:
            bad = self.bad_hosts(self.c_banner)
            if bad:
                log.err(f"ads.yaml coupang.banner_html 에 쿠팡 밖 주소가 있습니다: {', '.join(bad)}")
                self.c_banner = ""
        self.c_products = c.get("products") or {}
        for theme, items in self.c_products.items():
            for it in items or []:
                bad = self.bad_hosts(str(it.get("url", "")) + " " + str(it.get("image", "")))
                if bad or not str(it.get("url", "")).startswith("https://"):
                    log.err(f"ads.yaml coupang.products.{theme} 의 '{it.get('name')}' 주소가 쿠팡 https 주소가 아닙니다")
        self.c_per_box = int(c.get("products_per_box") or 3)
        self.c_blocked = [str(w).lower() for w in (c.get("blocked_words") or [])]
        self.c_book_blocked = [str(w).lower() for w in (c.get("book_blocked_words") or [])]
        # 쿠팡 API 자동 상품(scripts/coupang_sync.py 결과). 없으면 위 수동 상품만 쓴다.
        self.c_auto: dict[str, list[dict]] = {}
        auto_path = Path(os.environ.get("COUPANG_CACHE") or ROOT / ".cache" / "coupang_auto.json")
        try:
            entries = (json.loads(auto_path.read_text(encoding="utf-8")).get("entries") or {}).values()
        except Exception:
            entries = []
        for e in entries:
            prods = [x for x in (e.get("products") or [])
                     if str(x.get("url", "")).startswith("https://") and not self.bad_hosts(str(x.get("url", "")) + " " + str(x.get("image", "")))]
            if prods:
                self.c_auto.setdefault(str(e.get("theme")), []).append(
                    {"keyword": e.get("keyword"), "sub_id": e.get("sub_id"), "date": e.get("date", ""), "products": prods, "theme": str(e.get("theme"))})
        for groups in self.c_auto.values():
            groups.sort(key=lambda g: str(g.get("sub_id")))
        self.theme_slug: dict[str, str] = {}  # 테마 이름 → 주소용 이름(build 에서 채움). 맞춤형 광고 선택에 쓴다
        self.place = self.cfg.get("placements") or {}
        # 대화 사이 광고 리듬(first번째 글 뒤부터 every개마다, 최대 max개)
        rh = self.cfg.get("rhythm") or {}
        def _r(k, d):
            v = rh.get(k) or {}
            return {"first": int(v.get("first", d[0])), "every": int(v.get("every", d[1])), "max": int(v.get("max", d[2]))}
        self.rhythm = {"report_comments": _r("report_comments", (6, 6, 3)), "board": _r("board", (4, 6, 4)),
                       "home_feed": _r("home_feed", (4, 6, 5))}
        if self.rhythm["report_comments"]["max"] > 3 or self.rhythm["board"]["max"] > 4 or self.rhythm["home_feed"]["max"] > 5:
            log.err("ads.yaml rhythm: 리포트 댓글 사이 최대 3개, 종토방 최대 4개, 홈 피드 최대 5개")
        if min(self.rhythm[k]["every"] for k in self.rhythm) < 5:
            log.err("ads.yaml rhythm: 광고 사이 간격(every)은 글 5개 이상")
        valid = {"adsense_in_article", "adsense_display", "adfit_report_mid", "adfit_report_end", "adfit_list", "coupang_banner", "coupang_products", "none", None}
        for k, v in self.place.items():
            for one in (v if isinstance(v, list) else [v]):
                if one not in valid:
                    log.err(f"ads.yaml placements.{k} 값 '{one}' 을 알 수 없습니다")
                if k == "thread_inline" and one not in ("coupang_products", "adsense_in_article", "none", None):
                    log.err("ads.yaml placements.thread_inline 은 coupang_products·adsense_in_article·none 만 가능(화면에서 끼워 넣는 자리)")

    def bad_hosts(self, s: str) -> list[str]:
        hosts = {h.lower() for h in re.findall(r"(?:https?:)?//([A-Za-z0-9.-]+)", s)}
        return sorted(h for h in hosts if not any(h == d or h.endswith("." + d) for d in self.c_allowed))

    # 자리 → 광고 종류
    def kind(self, slot: str):
        """자리에 낼 광고 종류. 목록이면 앞에서부터 실제로 낼 수 있는 첫 번째(예: 애드핏 번호가 없으면 쿠팡)."""
        if not self.on:
            return None
        v = self.place.get(slot)
        for one in (v if isinstance(v, list) else [v]):
            if self.available(one):
                return one
        return None

    def available(self, kind) -> bool:
        if not self.on or not kind or kind == "none":
            return False
        if kind == "adsense_in_article":
            return bool(self.adsense_client and self.adsense_slots.get("in_article"))
        if kind == "adsense_display":
            return bool(self.adsense_client and self.adsense_slots.get("display"))
        if kind == "adfit_report_mid":
            return bool(self.adfit_units.get("report_mid"))
        if kind == "adfit_report_end":
            return bool(self.adfit_units.get("report_end"))
        if kind == "adfit_list":
            return bool(self.adfit_units.get("list") or self.adfit_units.get("report_end"))
        if kind == "coupang_banner":
            return bool(self.c_banner)
        if kind == "coupang_products":
            return bool(self.c_products or self.c_auto)
        return False

    def products_for(self, theme: str, exclude_words: list[str]) -> list[dict]:
        items = list(self.c_products.get(theme) or []) + list(self.c_products.get("_default") or [])
        ex = [w.lower() for w in exclude_words if w] + self.c_blocked
        out, seen = [], set()
        for it in items:
            name = str(it.get("name") or "").strip()
            url = str(it.get("url") or "").strip()
            if not name or not url.startswith("https://") or url in seen or self.bad_hosts(url):
                continue
            if any(w in name.lower() for w in ex):
                continue
            seen.add(url)
            out.append({"name": name, "url": url, "image": str(it.get("image") or "").strip()})
            if len(out) >= self.c_per_box:
                break
        return out

    def auto_groups_for(self, theme: str, exclude_words: list[str], skip_theme: str = "") -> list[dict]:
        """테마의 자동 상품 묶음(검색어별). 다룬 회사·금지어 상품은 빼고, 로켓배송 → 쿠팡 순위 순으로 고른다.
        theme="*"이면 모든 테마, skip_theme은 뺄 테마(리포트 본문 상자와 겹치지 않게)."""
        ex = [w.lower() for w in exclude_words if w] + self.c_blocked
        out = []
        src = [g for t, gs in self.c_auto.items() if t != skip_theme for g in gs] if theme == "*" else (self.c_auto.get(theme) or [])
        for g in src:
            ex_g = ex + (self.c_book_blocked if "책" in str(g.get("keyword") or "") else [])
            prods = [x for x in g["products"] if not any(w in str(x.get("name", "")).lower() for w in ex_g)]
            prods.sort(key=lambda x: (not x.get("rocket"), int(x.get("rank") or 999)))
            if prods:
                out.append({**g, "products": prods[: self.c_per_box]})
        return out

    @staticmethod
    def _card(it: dict, slot: str, sub: str = "") -> str:
        img = (f'<span class="cp-img"><img src="{html.escape(it["image"])}" alt="" loading="lazy" width="160" height="160"></span>'
               if it.get("image") else "")
        price = f'<span class="cp-price">{int(it["price"]):,}원</span>' if it.get("price") else ""
        rocket = '<span class="cp-rocket">로켓배송</span>' if it.get("rocket") else ""
        sub_attr = f' data-cp-sub="{html.escape(sub)}"' if sub else ""
        return (f'<a class="cp-card" href="{html.escape(it["url"])}" target="_blank" rel="sponsored noopener" '
                f'data-cp-slot="{slot}"{sub_attr}>{img}<span class="cp-name">{html.escape(it["name"])}</span>'
                f'{price}{rocket}<span class="cp-go">쿠팡에서 보기</span></a>')

    def render(self, slot: str, ctx: dict | None = None) -> str:
        """slot의 광고 HTML. 설정이 없으면 빈 문자열."""
        kind = self.kind(slot)
        if not self.available(kind):
            return ""
        ctx = ctx or {}
        label = '<div class="ad-label">광고</div>'
        if kind in ("adsense_in_article", "adsense_display"):
            slot_id = self.adsense_slots["in_article" if kind == "adsense_in_article" else "display"]
            attrs = 'data-ad-layout="in-article" data-ad-format="fluid"' if kind == "adsense_in_article" else 'data-ad-format="auto" data-full-width-responsive="true"'
            return (
                f'<aside class="ad ad-adsense" data-slot="{slot}" aria-label="광고">{label}'
                f'<ins class="adsbygoogle" style="display:block;text-align:center" {attrs} '
                f'data-ad-client="{self.adsense_client}" data-ad-slot="{slot_id}"></ins>'
                f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></aside>'
            )
        if kind in ("adfit_report_mid", "adfit_report_end", "adfit_list"):
            key = {"adfit_report_mid": "report_mid", "adfit_report_end": "report_end"}.get(kind) or ("list" if self.adfit_units.get("list") else "report_end")
            unit = self.adfit_units.get(key)
            w, h = self.adfit_sizes.get(key, (self.adfit_w, self.adfit_h))
            return (
                f'<aside class="ad ad-adfit" data-slot="{slot}" aria-label="광고" style="min-height:{h + 24}px">{label}'
                f'<ins class="kakao_ad_area" style="display:none;" data-ad-unit="{unit}" '
                f'data-ad-width="{w}" data-ad-height="{h}" data-ad-onfail="kwAdFail"></ins>'
                f'<script async src="https://t1.daumcdn.net/kas/static/ba.min.js" onerror="this.parentNode.classList.add(\'hidden\')"></script></aside>'
            )
        if kind == "coupang_banner":
            doc = (
                '<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;overflow:hidden}</style></head><body>'
                + self.c_banner + "</body></html>"
            )
            return (
                f'<aside class="ad ad-coupang" data-slot="{slot}" aria-label="광고">{label}'
                f'<p class="ad-disclosure">{COUPANG_DISCLOSURE}</p>'
                f'<iframe title="쿠팡 파트너스 배너" loading="lazy" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" '
                f'style="height:{self.c_banner_h}px" srcdoc="{html.escape(doc, quote=True)}"></iframe></aside>'
            )
        if kind == "coupang_products":
            groups = self.auto_groups_for(ctx.get("theme", ""), ctx.get("exclude", []), ctx.get("skip_theme", ""))
            if groups:
                # 묶음을 모두 넣고, 방문마다 하나를 무작위로 보여 준다(site.js). 스크립트가 없으면 첫 묶음.
                # 가격 기준일은 묶음마다 다르다(검색어마다 받은 날이 다름). 보이는 묶음의 날짜가 함께 보이도록 묶음 안에 둔다.
                # 이 페이지에서 몇 번째 쿠팡 상자인지(앞 자리가 다른 광고면 번호를 당긴다). 스크립트 없어도 상자마다 다른 묶음
                first = int(ctx.get("_cp_i", 0))
                if first >= len(groups):
                    return ""  # 묶음이 상자 수보다 적으면 같은 상품이 두 번 보이지 않게 이 상자는 뺀다
                ctx["_cp_i"] = first + 1
                inner = "".join(
                    f'<div class="cp-group" data-cp-group data-cp-sub="{html.escape(str(g.get("sub_id") or ""))}" data-cp-theme="{html.escape(self.theme_slug.get(g.get("theme"), ""))}" data-cp-date="{str(g.get("date") or "").replace("-", ".")}"{"" if i == first else " hidden"}><div class="cp-grid">'
                    + "".join(self._card(it, slot, g["sub_id"]) for it in g["products"]) + "</div></div>"
                    for i, g in enumerate(groups))
                # 가격 기준일 문구는 상자에 한 번. 보이는 묶음이 바뀌면 site.js가 날짜를 바꾼다
                d0 = str(groups[first].get("date") or "").replace("-", ".")
                note = f'<p class="cp-note" data-cp-note{"" if d0 else " hidden"}>가격은 <span>{d0}</span> 기준이며 바뀔 수 있습니다.</p>'
                return (f'<aside class="ad ad-coupang-products" data-slot="{slot}" aria-label="광고">{label}'
                        f'<p class="ad-disclosure">{COUPANG_DISCLOSURE}</p><div class="cp-rot">{inner}</div>{note}</aside>')
            items = self.products_for(ctx.get("theme", ""), ctx.get("exclude", []))
            if not items:
                return ""
            cards = []
            for it in items:
                img = (
                    f'<span class="cp-img"><img src="{html.escape(it["image"])}" alt="" loading="lazy" width="160" height="160"></span>'
                    if it["image"] else ""
                )
                cards.append(
                    f'<a class="cp-card" href="{html.escape(it["url"])}" target="_blank" rel="sponsored noopener" '
                    f'data-cp-slot="{slot}">{img}<span class="cp-name">{html.escape(it["name"])}</span><span class="cp-go">쿠팡에서 보기</span></a>'
                )
            return (
                f'<aside class="ad ad-coupang-products" data-slot="{slot}" aria-label="광고">{label}'
                f'<p class="ad-disclosure">{COUPANG_DISCLOSURE}</p><div class="cp-grid">{"".join(cards)}</div></aside>'
            )
        return ""

    def head_tags(self) -> str:
        if self.on and self.adsense_client:
            return (
                '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
                f'{self.adsense_client}" crossorigin="anonymous"></script>'
            )
        return ""

    def ads_txt(self) -> str:
        lines = ["# KimWorld ads.txt"]
        if self.adsense_client:
            lines.append(f"google.com, {self.adsense_client.replace('ca-', '')}, DIRECT, f08c47fec0942fa0")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 빌드

def build(drafts=False, strict=False, out: Path = DIST):
    log = Log()
    site = load_yaml(ROOT / "site.yaml", {})
    # 도메인 연결 전에는 워크플로가 SITE_URL 에 github.io 주소를 넣어 준다(그 주소에서도 화면이 깨지지 않게)
    site["site_url"] = str(os.environ.get("SITE_URL") or site.get("site_url", "")).rstrip("/")
    base_path = urlparse(site["site_url"]).path.rstrip("/")  # GitHub Pages 프로젝트 주소면 /kimworld-site
    ads = Ads(load_yaml(ROOT / "ads.yaml", {}), log)
    themes = load_yaml(ROOT / "data" / "themes.yaml", [])
    theme_by_name = {t["name"]: t for t in themes}
    ads.theme_slug = {t["name"]: t["slug"] for t in themes}
    tickers = load_yaml(ROOT / "data" / "tickers.yaml", {})
    glossary = load_yaml(ROOT / "data" / "glossary.yaml", [])
    today = dt.datetime.now(KST).date()

    # ---- 리포트 읽기
    reports = []
    for p in sorted((ROOT / "content" / "reports").glob("*.md")):
        if p.name.startswith("_"):
            continue
        slug = p.stem
        name = f"content/reports/{p.name}"
        try:
            meta, body = parse_front(p)
        except Exception as e:
            log.err(str(e))
            continue
        if not SLUG_RE.match(slug):
            log.err(f"{name}: 파일 이름은 영문 소문자·숫자·하이픈만 씁니다(예: rgti-2026-10)")
            continue
        missing = [k for k in REQUIRED if meta.get(k) in (None, "", [])]
        if missing:
            log.err(f"{name}: 필수 항목 없음 → {', '.join(missing)}")
            continue
        ticker = str(meta["ticker"]).upper()
        if ticker not in tickers:
            log.err(f"{name}: ticker {ticker} 가 data/tickers.yaml 에 없습니다")
            continue
        if meta["theme"] not in theme_by_name:
            log.err(f"{name}: theme '{meta['theme']}' 가 data/themes.yaml 에 없습니다")
            continue
        for k in ("holding", "holding_detail"):
            if k in meta:
                log.err(f"{name}: '{k}' 항목은 쓰지 않습니다(운영자 보유 여부는 공개하지 않음)")
        try:
            d, upd, asof = to_date(meta["date"]), to_date(meta.get("updated")), to_date(meta["data_as_of"])
        except Exception:
            log.err(f"{name}: 날짜는 YYYY-MM-DD 형식")
            continue
        sources = meta.get("sources") or []
        for i, s in enumerate(sources):
            if not isinstance(s, dict) or not s.get("title"):
                log.err(f"{name}: sources[{i}] 에 title 이 없습니다")
            elif s.get("url") and not re.match(r"https?://[^\s\"'<>]+$", str(s["url"])):
                log.err(f"{name}: sources[{i}] 주소는 http(s):// 로 시작하는 정상 주소여야 합니다")
        # 보안: 리포트 본문에 스크립트·외부 틀·이벤트 속성·위험한 링크를 넣지 못하게 한다(조사 중 섞여 들어온 악성 내용 차단)
        for pat, why in ((r"<\s*(script|iframe|object|embed|form|meta|link|style|base)\b", "실행·삽입 태그"),
                         (r"\son[a-z]+\s*=", "이벤트 속성(on...=)"),
                         (r"(\]\(|<|href\s*=\s*[\"']?|src\s*=\s*[\"']?)\s*(javascript|vbscript|data)\s*:", "위험한 링크 주소")):
            if re.search(pat, body, flags=re.I):
                log.err(f"{name}: 본문에 허용하지 않는 {why}가 있습니다")
        is_draft = bool(meta.get("draft"))
        if is_draft and not drafts:
            continue
        if d > today and not drafts:
            continue  # 예약 공개: 날짜가 되면 다음 빌드에 나타난다
        sponsor = meta.get("sponsor")
        if sponsor and not (isinstance(sponsor, dict) and sponsor.get("unrelated_to_covered_company") is True):
            log.err(f"{name}: sponsor 는 unrelated_to_covered_company: true 확인이 필요합니다")
        for ph in site.get("lint", {}).get("banned_phrases", []):
            if ph in body or ph in str(meta.get("title")) or ph in str(meta.get("summary")):
                log.err(f"{name}: 금지 표현 '{ph}'")
        md = md_renderer()
        body_html = fold_event_cards(wrap_tables(md.convert(body)))
        # 차트 이미지는 눌러서 원본 크기로 볼 수 있게(모바일에서 글자가 작다)
        body_html = re.sub(r'(<img [^>]*src="(/static/charts/[^"]+)"[^>]*>)',
                           r'<a class="chart-link" href="\2" target="_blank" rel="noopener" aria-label="차트 크게 보기">\1</a>', body_html)
        toc = [t for t in md.toc_tokens]
        chars = plain_len(body_html)
        min_chars = int(site.get("lint", {}).get("min_chars", 0))
        if not is_draft and chars < min_chars:
            log.warn(f"{name}: 본문이 짧습니다({chars}자 < {min_chars}자)")
        if not is_draft and len(sources) < 2:
            log.warn(f"{name}: 출처가 2개 미만입니다")
        tk = tickers[ticker]
        reports.append({
            "slug": slug, "ticker": ticker, "company": tk.get("name", ""), "company_en": tk.get("name_en", ""),
            "exchange": tk.get("exchange", ""), "aliases": tk.get("aliases", []),
            "title": str(meta["title"]), "theme": meta["theme"], "theme_slug": theme_by_name[meta["theme"]]["slug"],
            "date": d, "updated": upd, "data_as_of": asof, "summary": str(meta["summary"]).strip(),
            "key_points": [str(x) for x in (meta.get("key_points") or [])][:5],
            "chart": chart_info(slug),
            "youtube_id": str(meta.get("youtube_id") or "").strip(),
            "sources": sources, "sponsor": sponsor if isinstance(sponsor, dict) else None,
            "draft": is_draft, "body_html": body_html, "toc": toc, "chars": chars,
            "minutes": max(1, math.ceil(chars / 600)), "url": f"{base_path}/r/{slug}/",
        })
        if reports[-1]["youtube_id"] and not re.fullmatch(r"[A-Za-z0-9_-]{11}", reports[-1]["youtube_id"]):
            log.err(f"{name}: youtube_id 는 11자리 영상 ID")

    reports.sort(key=lambda r: (r["date"], r["slug"]), reverse=True)
    public = [r for r in reports if not r["draft"]]

    # ---- 관계 계산
    by_ticker: dict[str, list] = {}
    for r in public:
        by_ticker.setdefault(r["ticker"], []).append(r)
    for r in reports:
        same = by_ticker.get(r["ticker"], [])
        r["ticker_reports"] = [x for x in same if x is not r]
        newer = [x for x in same if x["date"] > r["date"]]
        r["newer"] = newer[-1] if newer else None
        r["related"] = [x for x in public if x["theme"] == r["theme"] and x["ticker"] != r["ticker"]][:4]
        idx = public.index(r) if r in public else -1
        r["prev"] = public[idx + 1] if idx >= 0 and idx + 1 < len(public) else None
        r["next"] = public[idx - 1] if idx > 0 else None

    # ---- 출력 준비
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "static", out / "static")

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "xml"]))
    env.filters["kdate"] = lambda d: f"{d.year}년 {d.month}월 {d.day}일" if d else ""
    env.filters["iso"] = lambda d: d.isoformat() if d else ""
    asset_ver = str(int(dt.datetime.now().timestamp()))
    common = {
        "site": site, "base": base_path, "themes": themes, "ads": ads, "ads_head": ads.head_tags(),
        "asset_ver": asset_ver, "year": today.year, "tickers": tickers,
        "COUPANG_PAGE_NOTICE": COUPANG_PAGE_NOTICE,
        # 종토방이 있는 종목(리포트가 있는 종목). 글 속 $TSLA 링크와 글쓰기 상자에 쓴다
        "board_ticks": [{"c": c, "n": (tickers.get(c) or {}).get("name", "")} for c in sorted(by_ticker)],
    }

    def write(rel: str, tpl: str, **ctx):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        page_url = site["site_url"] + "/" + rel.replace("index.html", "")
        html_out = env.get_template(tpl).render(**common, page_url=page_url, **ctx)
        if base_path:  # 본문 마크다운의 /static/…, /disclaimer/ 같은 링크에도 하위 경로를 붙인다
            html_out = re.sub(r'((?:href|src|action)=")/(?!/)(?!' + re.escape(base_path.lstrip("/")) + r'/)',
                              r"\1" + base_path + "/", html_out)
        dest.write_text(html_out, encoding="utf-8")

    # ---- 리포트 페이지
    og_dir = out / "og"
    og_dir.mkdir()
    og_font = find_font()
    for r in reports:
        body, used_terms = apply_glossary(r["body_html"], glossary)
        exclude = [r["ticker"], r["company"], r["company_en"], *r["aliases"]]
        ad_ctx = {"theme": r["theme"], "exclude": exclude}
        pieces = []
        mid_html = ads.render("report_mid", ad_ctx)
        prod_html = ads.render("report_products", ad_ctx)
        # 긴 리포트(본문 1만 5천 자 이상)만 4분의 3 지점에 한 자리 더. 본문 상자와 겹치지 않게 다른 테마 상품에서
        far_ctx = {"theme": "*", "skip_theme": r["theme"], "exclude": exclude}
        late_html = ads.render("report_late", far_ctx) if r["chars"] >= 15000 else ""
        slot_html = {"report_mid": mid_html, "report_products": prod_html, "report_late": late_html}
        for kind, val in split_for_ads(body, bool(mid_html), bool(prod_html), bool(late_html)):
            if kind == "html":
                pieces.append(val)
            else:
                pieces.append(slot_html[val])
        # 넓은 화면 오른쪽 목차 아래에 따라 내려오는 상자(휴대폰에서는 안 보임)
        rail_html = ads.render("rail", far_ctx)
        end_html = ads.render("report_end", ad_ctx)
        bottom_html = "" if r["sponsor"] else ads.render("report_bottom", ad_ctx)
        used_ads = [x for x in pieces if x.startswith('<aside class="ad')] + [x for x in (end_html, bottom_html) if x]
        if len(used_ads) > 5:
            log.err(f"{r['slug']}: 본문 광고가 5개를 넘습니다")
        has_coupang = any("ad-coupang" in x for x in used_ads)
        og_rel = f"og/{r['slug']}.png"
        r["og_image"] = f"{site['site_url']}/{og_rel}" if make_og(og_dir / f"{r['slug']}.png", r, site, og_font) else f"{site['site_url']}/static/og-default.png"
        # 댓글 사이 광고(댓글이 쌓였을 때만 화면에서 끼워 넣음): 다른 테마 상품 묶음에서 골라 본문 상자와 겹치지 않게
        thread_ad = ads.render("thread_inline", {"theme": "*", "skip_theme": r["theme"], "exclude": exclude})
        write(f"r/{r['slug']}/index.html", "report.html", r=r, body_pieces=pieces, end_ad=end_html, thread_ad=thread_ad, rail_ad=rail_html,
              bottom_ad=bottom_html, has_coupang=has_coupang, terms=used_terms, today=today,
              stale=(today - r["data_as_of"]).days > int(site.get("stale_days", 180)))

    # ---- 종목·테마·홈·검색
    ticker_list = []
    for code, rs in sorted(by_ticker.items(), key=lambda kv: kv[1][0]["date"], reverse=True):
        t = tickers[code]
        ticker_list.append({"code": code, "name": t.get("name"), "count": len(rs), "last": rs[0]["date"], "theme": t.get("theme")})
        tex = [code, t.get("name", ""), t.get("name_en", ""), *(t.get("aliases") or [])]
        write(f"t/{code.lower()}/index.html", "ticker.html", code=code, t=t, rs=rs,
              list_ad=ads.render("list", {"theme": t.get("theme", ""), "exclude": tex}),
              thread_ad=ads.render("thread_inline", {"theme": "*", "exclude": tex}))
    for th in themes:
        rs = [r for r in public if r["theme"] == th["name"]]
        write(f"theme/{th['slug']}/index.html", "theme.html", th=th, rs=rs, list_ad=ads.render("list", {"theme": th["name"]}))
    home_ctx = {"theme": "*"}  # 같은 ctx를 이어 써서 피드 광고마다 다른 상품 묶음
    home_list = ads.render("list", home_ctx)
    hf = ads.rhythm["home_feed"]
    feed_ads = [x for x in (ads.render("feed_inline", home_ctx) for _ in range(max(0, hf["max"] - 1))) if x]
    home_rail = ads.render("rail", home_ctx)
    write("index.html", "index.html", rs=public, ticker_list=ticker_list, list_ad=home_list, feed_ads=feed_ads,
          feed_first=hf["first"], feed_every=hf["every"], rail_ad=home_rail, is_home=True)
    write("search/index.html", "search.html")
    if site.get("api_url"):
        write("u/index.html", "user.html")  # 이용자 프로필(화면에서 API로 채움, 검색 노출 안 함)
        # 글 상세(종토방·라운지 글 하나와 답글). 답글 사이 광고는 종토방과 같은 리듬
        write("p/index.html", "post.html", thread_ad=ads.render("thread_inline", {"theme": "*"}), rhythm=ads.rhythm["board"])
    write("404.html", "404.html")

    # ---- 고정 페이지
    pages = []
    op = site.get("operator", {})
    repl = {
        "{{site_name}}": site.get("site_name", ""),
        "{{channel_name}}": op.get("display_name") or site.get("site_name", ""),
        "{{youtube_url}}": op.get("youtube_url") or "#",
    }
    page_flags = {
        "ga4": bool((site.get("analytics") or {}).get("ga4_id")),
        "newsletter": bool((site.get("newsletter") or {}).get("url")),
        "api": bool(site.get("api_url")),
    }
    for p in sorted((ROOT / "content" / "pages").glob("*.md")):
        meta, body = parse_front(p)
        for k, v in repl.items():
            body = body.replace(k, v)
        # 줄 끝에 <!--if:이름--> 이 붙은 줄은 그 기능을 켰을 때만 남긴다(안 쓰는 서비스를 방침·고지에 적지 않기 위해)
        body = "\n".join(ln for ln in body.split("\n")
                         if not (m := re.search(r"<!--if:(\w+)-->", ln)) or page_flags.get(m.group(1)))
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        html_body = wrap_tables(md_renderer().convert(body), "table-text")
        pages.append({"slug": p.stem, "title": meta.get("title", p.stem)})
        write(f"{p.stem}/index.html", "page.html", p={"title": meta.get("title"), "description": meta.get("description", ""),
              "updated": to_date(meta.get("updated")), "html": html_body})

    # ---- 검색 색인, 피드, 사이트맵, 기타
    index = [{
        "u": r["url"], "t": r["title"], "k": r["ticker"], "c": r["company"], "e": r["company_en"],
        "a": r["aliases"], "th": r["theme"], "ts": r["theme_slug"], "s": r["summary"], "d": r["date"].isoformat(),
    } for r in public]
    (out / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "ad-weights.json").write_text(json.dumps(ad_weights(ads), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    su = site["site_url"]
    urls = [(f"{su}/", today)] + [(f"{su}/r/{r['slug']}/", r["updated"] or r["date"]) for r in public]
    urls += [(f"{su}/t/{c.lower()}/", rs[0]["date"]) for c, rs in by_ticker.items()]
    urls += [(f"{su}/theme/{t['slug']}/", None) for t in themes]
    urls += [(f"{su}/{p['slug']}/", None) for p in pages]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm in urls:
        sm.append(f"<url><loc>{html.escape(u)}</loc>" + (f"<lastmod>{lm.isoformat()}</lastmod>" if lm else "") + "</url>")
    sm.append("</urlset>")
    (out / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    items = []
    for r in public[:30]:
        pub = dt.datetime.combine(r["date"], dt.time(9, 0), KST)
        items.append(
            f"<item><title>{html.escape(r['ticker'] + ' · ' + r['title'])}</title><link>{su}/r/{r['slug']}/</link>"
            f"<guid>{su}/r/{r['slug']}/</guid><pubDate>{format_datetime(pub)}</pubDate>"
            f"<description>{html.escape(r['summary'])}</description></item>"
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{html.escape(site['site_name'])}</title><link>{su}/</link>"
        f"<description>{html.escape(site.get('description', ''))}</description><language>ko</language>"
        + "".join(items) + "</channel></rss>"
    )
    (out / "rss.xml").write_text(rss, encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {su}/sitemap.xml\n", encoding="utf-8")
    (out / "ads.txt").write_text(ads.ads_txt(), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    manifest = {
        "name": site["site_name"], "short_name": site["site_name"], "start_url": f"{base_path}/",
        "display": "standalone", "background_color": "#ffffff", "theme_color": "#0f172a", "lang": "ko",
        "icons": [{"src": f"{base_path}/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
    }
    (out / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    host = urlparse(su).hostname or ""
    if host and not host.endswith("github.io"):
        (out / "CNAME").write_text(host + "\n", encoding="utf-8")
    if not (out / "static" / "og-default.png").exists():
        make_default_og(out / "static" / "og-default.png", site, og_font)

    # ---- 결과
    for w in log.warnings:
        print("⚠️ ", w)
    for e in log.errors:
        print("❌", e)
    print(f"리포트 {len(public)}개 공개" + (f", 초안 {len(reports) - len(public)}개" if drafts else "") + f" → {out}")
    if log.errors or (strict and log.warnings):
        raise SystemExit(1)
    return {"reports": reports, "log": log}


# ---------------------------------------------------------------- 공유 이미지

def find_font():
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if Path(p).exists():
            return p
    return None


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= width:
            cur += ch
        else:
            # 가능하면 공백에서 줄바꿈
            cut = cur.rfind(" ")
            if cut > len(cur) * 0.6:
                lines.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


def make_og(dest: Path, r: dict, site: dict, font_path) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return False
    if not font_path:
        return False
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#0f172a")
    d = ImageDraw.Draw(img)
    f_small = ImageFont.truetype(font_path, 34, index=1)
    f_tick = ImageFont.truetype(font_path, 84, index=1)
    f_title = ImageFont.truetype(font_path, 54, index=1)
    d.rectangle([0, 0, W, 10], fill="#f59e0b")
    d.text((72, 64), f"{site.get('site_name', '')} · {r['theme']}", font=f_small, fill="#94a3b8")
    d.text((72, 120), r["ticker"], font=f_tick, fill="#f59e0b")
    tx = 72 + d.textlength(r["ticker"], font=f_tick) + 28
    d.text((tx, 160), r["company"], font=f_small, fill="#e2e8f0")
    lines = _wrap(d, r["title"], f_title, W - 144)[:3]
    y = 262
    for ln in lines:
        d.text((72, y), ln, font=f_title, fill="#f8fafc")
        y += 74
    d.text((72, H - 76), f"{r['date'].isoformat()} · 무료 리포트 · 투자 권유 아님", font=f_small, fill="#94a3b8")
    img.save(dest, "PNG", optimize=True)
    return True


def make_default_og(dest: Path, site: dict, font_path):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return
    img = Image.new("RGB", (1200, 630), "#0f172a")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1200, 10], fill="#f59e0b")
    if font_path:
        d.text((72, 220), site.get("site_name", ""), font=ImageFont.truetype(font_path, 96, index=1), fill="#f8fafc")
        d.text((72, 360), site.get("tagline", ""), font=ImageFont.truetype(font_path, 44, index=1), fill="#cbd5e1")
    img.save(dest, "PNG", optimize=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--out", default=str(DIST))
    a = ap.parse_args()
    try:
        build(drafts=a.drafts, strict=a.strict, out=Path(a.out))
    except BuildError as e:
        print("❌", e)
        sys.exit(1)
