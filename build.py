#!/usr/bin/env python3
"""김박사 월드 정적 사이트 생성기.

  python3 build.py            # 공개 리포트만 빌드 → dist/
  python3 build.py --drafts   # 초안까지 빌드(초안은 noindex, 목록·사이트맵 제외, 주소로만 열림)
  python3 build.py --strict   # 경고도 실패로 처리(CI에서 사용)

입력:  site.yaml, ads.yaml, data/*.yaml, content/reports/*.md, content/pages/*.md, templates/, static/
출력:  dist/ (GitHub Pages가 그대로 서비스)
"""
from __future__ import annotations

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

HOLDING_TEXT = {
    "none": "작성일 기준 운영자는 이 종목을 보유하지 않습니다.",
    "holding": "작성일 기준 운영자는 이 종목을 보유하고 있습니다.",
    "plan": "작성일 기준 운영자는 이 종목을 보유하지 않지만 매수를 검토하고 있습니다.",
}
HOLDING_SUFFIX = " 리포트에서 다룬 종목은 보유 여부와 관계없이 공개 후 7일 동안 매매하지 않습니다."
REQUIRED = ["ticker", "title", "theme", "date", "data_as_of", "summary", "holding", "sources"]
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

SKIP_TAGS = {"a", "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "th", "button", "sup", "script", "style"}


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


def split_for_ads(body_html: str, want_mid: bool, want_products: bool) -> list[tuple[str, str]]:
    """본문을 광고 자리에서 나눈다. 반환: [("html", 조각) | ("ad", 자리이름)]"""
    h2 = [m.start() for m in re.finditer(r"<h2[\s>]", body_html)]
    mid = h2[2] if want_mid and len(h2) >= 3 else -1
    prod = -1
    if want_products:
        prod = len(body_html)
        for i, pos in enumerate(h2):
            end = body_html.find("</h2>", pos)
            if "운영자 판단" in body_html[pos:end]:
                prod = h2[i + 1] if i + 1 < len(h2) else len(body_html)
                break
        if prod == mid:
            prod = -1  # 두 광고가 붙으면 아래쪽을 끈다
    cuts = sorted([(p, n) for p, n in ((mid, "report_mid"), (prod, "report_products")) if p >= 0])
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
        self.place = self.cfg.get("placements") or {}
        valid = {"adsense_in_article", "adsense_display", "adfit_report_end", "adfit_list", "coupang_banner", "coupang_products", "none", None}
        for k, v in self.place.items():
            if v not in valid:
                log.err(f"ads.yaml placements.{k} 값 '{v}' 을 알 수 없습니다")

    def bad_hosts(self, s: str) -> list[str]:
        hosts = {h.lower() for h in re.findall(r"(?:https?:)?//([A-Za-z0-9.-]+)", s)}
        return sorted(h for h in hosts if not any(h == d or h.endswith("." + d) for d in self.c_allowed))

    # 자리 → 광고 종류
    def kind(self, slot: str):
        return self.place.get(slot) if self.on else None

    def available(self, kind) -> bool:
        if not self.on or not kind or kind == "none":
            return False
        if kind == "adsense_in_article":
            return bool(self.adsense_client and self.adsense_slots.get("in_article"))
        if kind == "adsense_display":
            return bool(self.adsense_client and self.adsense_slots.get("display"))
        if kind == "adfit_report_end":
            return bool(self.adfit_units.get("report_end"))
        if kind == "adfit_list":
            return bool(self.adfit_units.get("list") or self.adfit_units.get("report_end"))
        if kind == "coupang_banner":
            return bool(self.c_banner)
        if kind == "coupang_products":
            return bool(self.c_products)
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
        if kind in ("adfit_report_end", "adfit_list"):
            unit = self.adfit_units.get("report_end") if kind == "adfit_report_end" else (self.adfit_units.get("list") or self.adfit_units.get("report_end"))
            return (
                f'<aside class="ad ad-adfit" data-slot="{slot}" aria-label="광고" style="min-height:{self.adfit_h + 24}px">{label}'
                f'<ins class="kakao_ad_area" style="display:none;" data-ad-unit="{unit}" '
                f'data-ad-width="{self.adfit_w}" data-ad-height="{self.adfit_h}" data-ad-onfail="kwAdFail"></ins>'
                f'<script async src="https://t1.daumcdn.net/kas/static/ba.min.js"></script></aside>'
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
    site["site_url"] = str(site.get("site_url", "")).rstrip("/")
    base_path = urlparse(site["site_url"]).path.rstrip("/")  # GitHub Pages 프로젝트 주소면 /kimworld-site
    ads = Ads(load_yaml(ROOT / "ads.yaml", {}), log)
    themes = load_yaml(ROOT / "data" / "themes.yaml", [])
    theme_by_name = {t["name"]: t for t in themes}
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
        if meta["holding"] not in HOLDING_TEXT:
            log.err(f"{name}: holding 은 none / holding / plan 중 하나")
            continue
        try:
            d, upd, asof = to_date(meta["date"]), to_date(meta.get("updated")), to_date(meta["data_as_of"])
        except Exception:
            log.err(f"{name}: 날짜는 YYYY-MM-DD 형식")
            continue
        sources = meta.get("sources") or []
        for i, s in enumerate(sources):
            if not isinstance(s, dict) or not s.get("title"):
                log.err(f"{name}: sources[{i}] 에 title 이 없습니다")
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
        body_html = md.convert(body)
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
            "holding": meta["holding"], "holding_text": HOLDING_TEXT[meta["holding"]] + HOLDING_SUFFIX,
            "holding_detail": str(meta.get("holding_detail") or ""),
            "ai_use": str(meta.get("ai_use") or site.get("ai_use_default", "")),
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
    }

    def write(rel: str, tpl: str, **ctx):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        page_url = site["site_url"] + "/" + rel.replace("index.html", "")
        dest.write_text(env.get_template(tpl).render(**common, page_url=page_url, **ctx), encoding="utf-8")

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
        for kind, val in split_for_ads(body, bool(mid_html), bool(prod_html)):
            if kind == "html":
                pieces.append(val)
            else:
                pieces.append(mid_html if val == "report_mid" else prod_html)
        end_html = ads.render("report_end", ad_ctx)
        bottom_html = "" if r["sponsor"] else ads.render("report_bottom", ad_ctx)
        used_ads = [x for x in pieces if x.startswith('<aside class="ad')] + [x for x in (end_html, bottom_html) if x]
        if len(used_ads) > 4:
            log.err(f"{r['slug']}: 광고가 4개를 넘습니다")
        has_coupang = any("ad-coupang" in x for x in used_ads)
        og_rel = f"og/{r['slug']}.png"
        r["og_image"] = f"{site['site_url']}/{og_rel}" if make_og(og_dir / f"{r['slug']}.png", r, site, og_font) else f"{site['site_url']}/static/og-default.png"
        write(f"r/{r['slug']}/index.html", "report.html", r=r, body_pieces=pieces, end_ad=end_html,
              bottom_ad=bottom_html, has_coupang=has_coupang, terms=used_terms, today=today,
              stale=(today - r["data_as_of"]).days > int(site.get("stale_days", 180)))

    # ---- 종목·테마·홈·검색
    ticker_list = []
    for code, rs in sorted(by_ticker.items(), key=lambda kv: kv[1][0]["date"], reverse=True):
        t = tickers[code]
        ticker_list.append({"code": code, "name": t.get("name"), "count": len(rs), "last": rs[0]["date"], "theme": t.get("theme")})
        write(f"t/{code.lower()}/index.html", "ticker.html", code=code, t=t, rs=rs, list_ad=ads.render("list"))
    for th in themes:
        rs = [r for r in public if r["theme"] == th["name"]]
        write(f"theme/{th['slug']}/index.html", "theme.html", th=th, rs=rs, list_ad=ads.render("list"))
    write("index.html", "index.html", rs=public, ticker_list=ticker_list, list_ad=ads.render("list"), is_home=True)
    write("search/index.html", "search.html")
    write("404.html", "404.html")

    # ---- 고정 페이지
    pages = []
    op = site.get("operator", {})
    repl = {
        "{{site_name}}": site.get("site_name", ""),
        "{{operator_display_name}}": op.get("display_name") or "준비 중",
        "{{operator_real_name}}": op.get("real_name_or_business") or "운영자",
        "{{operator_email}}": op.get("email") or "(연락처 준비 중)",
        "{{youtube_url}}": op.get("youtube_url") or "#",
    }
    for p in sorted((ROOT / "content" / "pages").glob("*.md")):
        meta, body = parse_front(p)
        for k, v in repl.items():
            body = body.replace(k, v)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        html_body = md_renderer().convert(body)
        pages.append({"slug": p.stem, "title": meta.get("title", p.stem)})
        write(f"{p.stem}/index.html", "page.html", p={"title": meta.get("title"), "description": meta.get("description", ""),
              "updated": to_date(meta.get("updated")), "html": html_body})
    if not op.get("email"):
        print("ℹ️  site.yaml operator.email 이 비어 있습니다(애드센스 심사·개인정보처리방침에 연락처가 필요)")

    # ---- 검색 색인, 피드, 사이트맵, 기타
    index = [{
        "u": r["url"], "t": r["title"], "k": r["ticker"], "c": r["company"], "e": r["company_en"],
        "a": r["aliases"], "th": r["theme"], "s": r["summary"], "d": r["date"].isoformat(),
    } for r in public]
    (out / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

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
