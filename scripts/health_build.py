#!/usr/bin/env python3
"""김박사 건강몰 — 영양제 성분 가이드 + 쿠팡 검색 결과 정적 사이트(운영자 지시 2026-11-19 ET, 설정 health/health.yaml).

1) 받기(--fetch): 쿠팡 파트너스 API — 헬스/건강식품 베스트(bestcategories/1024, 하위 ID hmbest) 1회 +
   성분 검색(search) searches_per_run 회(가장 오래된 성분부터, 하위 ID hm<코드>). 결과는 health/catalog.json(공개 — 이름·가격은 어차피 공개).
   실패한 칸은 지난 값을 그대로 둔다. 상품 이름에 질병·의약품 낱말(drop_words)이 있으면 진열하지 않는다.
2) 만들기(--build <출력 폴더>): 홈 · /guide/ · /guide/<slug>/ (성분 가이드 + 쿠팡 검색 결과) · /best/ (noindex) · /about/ ·
   sitemap.xml · robots.txt · 404. 검색 노출: canonical, 설명, OG, JSON-LD(WebSite·Article·BreadcrumbList·FAQPage 없음), 사이트맵 lastmod.
3) 검사(--check): 가이드 문구에 금지 낱말(banned)이 없는지, 출처·확인일이 있는지. 빌드도 같은 검사를 먼저 한다.
사용: python3 scripts/health_build.py --fetch --build dist-health
"""
from __future__ import annotations

import argparse
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coupang_sync as cs  # noqa: E402

CFG = ROOT / "health" / "health.yaml"
CAT = ROOT / "health" / "catalog.json"
BEST = "/v2/providers/affiliate_open_api/apis/openapi/products/bestcategories/"
DISCLOSURE = "김박사 건강몰은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SITE = "https://drkimworld.com/?utm_source=health&utm_medium=web"
MALL = "https://mall.drkimworld.com/?utm_source=health"
YT = "https://www.youtube.com/@drkimworld"
KST = dt.timezone(dt.timedelta(hours=9))


def cfg(path: Path = CFG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_cat(path: Path = CAT) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# ---------- 검사 ----------
def check(c: dict) -> list[str]:
    errs = []
    banned = c.get("banned") or []
    seen = set()
    for g in c.get("guides") or []:
        s = g.get("slug", "?")
        if s in seen:
            errs.append(f"{s}: slug 중복")
        seen.add(s)
        if not str(g.get("sub", "")).startswith("hm"):
            errs.append(f"{s}: 하위 ID는 hm 으로 시작해야 함")
        if not (g.get("keywords") or g.get("keyword")):
            errs.append(f"{s}: keywords 없음")
        for k in ("name", "match", "intro", "functions", "cautions", "choose", "sources", "verified"):
            if not g.get(k):
                errs.append(f"{s}: {k} 없음")
        text = " ".join([str(g.get("intro", ""))] + [f.get("text", "") + f.get("dose", "") for f in g.get("functions") or []]
                        + [str(x) for x in g.get("choose") or []])
        for w in banned:
            if w in text:
                errs.append(f"{s}: 금지 낱말 '{w}'")
        # 주의사항은 공식 문구에 '당뇨치료제' 같은 약 이름이 들어가므로 '치료'·'처방'만 빼고 검사
        ctext = " ".join(str(x) for x in g.get("cautions") or [])
        for w in banned:
            if w not in ("치료", "처방") and w in ctext:
                errs.append(f"{s}: 주의사항 금지 낱말 '{w}'")
        for src in g.get("sources") or []:
            if not str(src.get("url", "")).startswith("https://"):
                errs.append(f"{s}: 출처 주소는 https:// 만")
    return errs


def clean(items: list[dict], drop: list[str], match: list[str] | None = None) -> list[dict]:
    out, names = [], set()
    for p in items:
        n = p.get("name", "")
        if not n or n in names or any(w in n for w in drop):
            continue
        if match is not None and not any(m.lower() in n.lower() for m in match):
            continue
        names.add(n)
        out.append(p)
    return out


# ---------- 받기 ----------
def get(path: str, q: dict, access: str, secret: str) -> dict:
    query = urllib.parse.urlencode(q)
    req = urllib.request.Request(f"{cs.DOMAIN}{path}?{query}", headers={
        "Authorization": cs.authorization("GET", path, query, access, secret, dt.datetime.now(dt.timezone.utc)),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def pairs(c: dict) -> list[tuple[dict, str]]:
    return [(g, k) for g in c.get("guides") or [] for k in (g.get("keywords") or [g["keyword"]])]


def plan(c: dict, cat: dict) -> list[tuple[dict, str]]:
    """가장 오래 전에 받은(또는 한 번도 안 받은) (성분, 검색어)부터 searches_per_run 개. 같은 성분이 한 번에 두 번 걸리지 않게."""
    at = cat.get("at") or {}
    out, used = [], set()
    for g, k in sorted(pairs(c), key=lambda gk: at.get(f"{gk[0]['slug']}|{gk[1]}", "")):
        if g["slug"] in used:
            continue
        out.append((g, k)); used.add(g["slug"])
        if len(out) >= int(c.get("searches_per_run") or 2):
            break
    return out


def merge(new: list[dict], old: list[dict], today: str, keep: int, days: int) -> list[dict]:
    """새로 찾은 상품을 앞에, 예전 상품은 뒤에(이름 기준 중복 제거). days 일 동안 다시 안 잡힌 것은 뺀다."""
    cut = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    out, seen = [], set()
    for p in [{**x, "seen": today} for x in new] + [{**x, "seen": x.get("seen") or today} for x in old if (x.get("seen") or today) >= cut]:
        if p["name"] in seen:
            continue
        seen.add(p["name"]); out.append(p)
    return out[:keep]


def fetch(c: dict, searcher=None, getter=get) -> dict:
    access, secret = os.environ.get("COUPANG_ACCESS_KEY", "").strip(), os.environ.get("COUPANG_SECRET_KEY", "").strip()
    cat = load_cat()
    if not (access and secret):
        print("::notice title=김박사 건강몰::쿠팡 키 없음 — 저장된 진열로 만든다")
        return cat
    drop = c.get("drop_words") or []
    ok = 0
    try:
        items, _ = cs.parse_deals(getter(BEST + str(c["best_category"]), {"limit": 50, "subId": c["best_subid"], "imageSize": "230x230"}, access, secret))
        allm = [m for g in c.get("guides") or [] for m in g.get("match") or []]
        items = clean(items, drop, allm)
        cat["best"] = items  # 성분과 무관한 베스트는 비운다(빈 목록이면 화면에서 빠짐)
        ok += bool(items)
    except Exception as e:
        print(f"::warning title=김박사 건강몰::베스트 실패 {type(e).__name__}")
    prods, at = cat.setdefault("products", {}), cat.setdefault("at", {})
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    today = now[:10]
    for g, kw in plan(c, cat):
        key = f"{g['slug']}|{kw}"
        at[key] = now  # 실패해도 다음 차례로 넘어가도록 시도 시각은 남긴다
        try:
            if searcher is None:
                js = getter(cs.SEARCH_PATH, {"keyword": kw, "limit": int(c.get("per_search") or 10), "subId": g["sub"]}, access, secret)
                raw = cs.parse(js)
                if not raw:
                    print(f"::warning title=김박사 건강몰::{kw} 검색 0개 rCode={js.get('rCode')} {str(js.get('rMessage') or '')[:80]}")
            else:
                raw = searcher(kw, g["sub"], int(c.get("per_search") or 10), access, secret)
            items = clean(raw, drop, g.get("match") or [g["name"]])
            prods[g["slug"]] = merge(items, prods.get(g["slug"]) or [], today, int(c.get("keep_items") or 24), int(c.get("keep_days") or 14))
            ok += bool(items)
            print(f"{kw}: 받은 {len(raw)} · 관련 {len(items)} · 쌓인 {len(prods[g['slug']])}")
        except Exception as e:
            print(f"::warning title=김박사 건강몰::{kw} 검색 실패 {type(e).__name__} {str(e)[:80]}")
    if ok:
        cat["updated"] = now
    CAT.parent.mkdir(parents=True, exist_ok=True)
    CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"::notice title=김박사 건강몰::받은 칸 {ok} · 베스트 {len(cat.get('best') or [])} · 성분 {len(prods)}/{len(c.get('guides') or [])}")
    return cat


# ---------- 화면 ----------
CSS = """
:root{--bg:#f6f8f6;--card:#fff;--ink:#14231c;--muted:#5f6b66;--line:#dfe6e1;--accent:#2f9e6b;--accent-ink:#fff;--soft:#e8f4ee;--red:#c8442f}
@media (prefers-color-scheme:dark){:root{--bg:#0e1512;--card:#16201b;--ink:#e6eeea;--muted:#9aa9a2;--line:#27342e;--accent:#4cc38a;--accent-ink:#06120c;--soft:#1b2a23;--red:#ff8a75}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
a{color:inherit}.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.top{display:flex;align-items:center;gap:12px;padding:10px 0}.logo{font-weight:800;font-size:19px;text-decoration:none;white-space:nowrap}.logo span{color:var(--accent)}
.tag{color:var(--muted);font-size:13px;display:none}@media(min-width:720px){.tag{display:inline}}
nav.gn{display:flex;gap:6px;overflow-x:auto;padding:0 0 10px;scrollbar-width:none}nav.gn::-webkit-scrollbar{display:none}
nav.gn a{flex:none;padding:5px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:13px;background:var(--bg)}nav.gn a.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent);font-weight:700}
.disc{font-size:12px;color:var(--muted);padding:8px 0;margin:0}
.hero{margin:14px 0 6px;padding:22px 18px;border-radius:16px;background:var(--soft)}.hero h1{margin:0 0 6px;font-size:23px;line-height:1.35}.hero p{margin:0;color:var(--muted);font-size:14px}
h1.t{font-size:24px;line-height:1.35;margin:18px 0 6px}.lead{color:var(--muted);margin:0 0 14px}
h2{font-size:19px;margin:28px 0 10px}h2 small{font-size:12px;color:var(--muted);font-weight:400;margin-left:6px}
.gl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}@media(min-width:720px){.gl{grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}}
.gc{display:block;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;text-decoration:none}.gc b{font-size:16px}.gc small{display:block;color:var(--muted);font-size:12px;margin-top:2px}.gc p{margin:6px 0 0;font-size:12px;line-height:1.45;color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}@media(min-width:720px){.gc p{font-size:13px}}
table.fn{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px}
table.fn th,table.fn td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}table.fn th{background:var(--soft);font-size:13px}
ul.ck{padding-left:20px}ul.ck li{margin:4px 0}.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px}
.note{font-size:13px;color:var(--muted)}.src{font-size:13px}.src li{margin:2px 0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}@media(min-width:640px){.grid{grid-template-columns:repeat(3,1fr)}}@media(min-width:900px){.grid{grid-template-columns:repeat(5,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;text-decoration:none}
.card .im{aspect-ratio:1;background:#fff;display:flex;align-items:center;justify-content:center}.card img{width:100%;height:100%;object-fit:contain}
.card .b{padding:9px 10px 11px;display:flex;flex-direction:column;gap:4px;flex:1}.card .n{font-size:13px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.7em}
.pr{font-weight:800;font-size:15px}.go{margin-top:auto;font-size:12px;color:var(--muted)}
.ad{font-size:11px;font-weight:700;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-left:6px;vertical-align:middle}
.fnl{margin:22px 0;padding:16px;border-radius:14px;border:2px solid var(--accent);background:var(--card)}.fnl h3{margin:0 0 4px;font-size:17px}.fnl p{margin:0 0 10px;color:var(--muted);font-size:14px}
.btn{display:inline-block;padding:10px 18px;border-radius:999px;background:var(--accent);color:var(--accent-ink);font-weight:800;text-decoration:none}
.kicker{margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--accent)}.hero .btn{margin-top:14px}
@media(min-width:720px){.hero{padding:38px 34px}.hero h1{font-size:32px}}
nav.chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 4px}nav.chips a{padding:5px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:13px;background:var(--card)}
.row h2{display:flex;align-items:baseline;gap:6px;font-size:17px}.row h2 a.more{margin-left:auto;font-size:13px;font-weight:400;color:var(--muted);text-decoration:none}
h2.sec{margin-top:40px;padding-top:18px;border-top:1px solid var(--line)}.row{scroll-margin-top:110px}
.crumb{font-size:12px;color:var(--muted);margin:12px 0 0}.crumb a{text-decoration:none}
footer{margin-top:40px;padding:22px 0 40px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}footer a{color:var(--ink)}
.empty{color:var(--muted);padding:20px 0}
"""


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def card(p: dict) -> str:
    price = f'<div class="pr">{p["price"]:,}원</div>' if p.get("price") else ""
    img = f'<img src="{esc(p["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if p.get("image") else ""
    return (f'<a class="card" href="{esc(p["url"])}" rel="sponsored nofollow noopener" target="_blank">'
            f'<div class="im">{img}</div><div class="b"><div class="n">{esc(p["name"])}</div>{price}<div class="go">쿠팡에서 보기 ›</div></div></a>')


def funnel(c: dict, *slots: str) -> str:
    f = c.get("funnels") or {}
    for s in slots:
        x = f.get(s)
        if x and x.get("url", "").startswith("https://"):
            return (f'<section class="fnl" data-slot="{esc(s)}"><h3>{esc(x.get("title"))}</h3><p>{esc(x.get("text"))}</p>'
                    f'<a class="btn" href="{esc(x["url"])}">{esc(x.get("button") or "자세히 보기")}</a></section>')
    return ""


def page(c: dict, cat: dict, title: str, body: str, path: str, desc: str, on: str = "", noindex: bool = False, ld: list | None = None) -> str:
    depth = path.count("/")
    up = "../" * depth
    base = c["url"].rstrip("/")
    canon = f"{base}/{path}"
    nav = [f'<a href="{up}" class="{"on" if on == "home" else ""}">홈</a>', f'<a href="{up}guide/" class="{"on" if on == "guide" else ""}">성분 가이드</a>']
    nav += [f'<a href="{up}guide/{g["slug"]}/" class="{"on" if on == g["slug"] else ""}">{esc(g["name"])}</a>' for g in c.get("guides") or []]
    if cat.get("best_shown"):
        nav.append(f'<a href="{up}best/" class="{"on" if on == "best" else ""}">건강식품 베스트</a>')
    v = c.get("verification") or {}
    meta = "".join(f'<meta name="{n}" content="{esc(v[k])}">' for k, n in (("google", "google-site-verification"), ("naver", "naver-site-verification"), ("bing", "msvalidate.01")) if v.get(k))
    robots = '<meta name="robots" content="noindex,follow">' if noindex else '<meta name="robots" content="index,follow,max-image-preview:large">'
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in (ld or []))
    upd = esc(cat.get("updated") or "")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">{robots}<link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{esc(c['name'])}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canon)}"><meta property="og:locale" content="ko_KR">
<meta name="theme-color" content="#2f9e6b">{meta}
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%232f9e6b'/%3E%3Ctext x='32' y='44' font-size='32' text-anchor='middle' font-family='sans-serif' font-weight='800' fill='%23fff'%3E건%3C/text%3E%3C/svg%3E">
<style>{CSS}</style>{lds}</head><body>
<header><div class="wrap"><div class="top"><a class="logo" href="{up}">김박사 <span>건강몰</span></a><span class="tag">{esc(c['tagline'])}</span></div>
<nav class="gn" aria-label="메뉴">{''.join(nav)}</nav></div></header>
<main class="wrap"><p class="disc">{esc(DISCLOSURE)}</p>
{body}</main>
<footer><div class="wrap"><p>{esc(DISCLOSURE)} 성분 가이드는 식약처가 인정한 기능성 문구와 공개된 섭취 시 주의사항을 옮겨 정리한 일반 정보이며, 의학적 진단·상담을 대신하지 않습니다. 질환이 있거나 의약품을 복용 중이라면 의사·약사와 먼저 상담하세요.
상품 목록은 쿠팡 검색·베스트 결과를 자동으로 가져온 것으로 추천·보증이 아니며, 건강기능식품 여부·함량·가격은 쿠팡 상품 페이지의 표시사항이 기준입니다{f" · 상품 갱신 {upd}(한국 시각)" if upd else ""}.</p>
<p><a href="{SITE}">김박사 월드</a> · <a href="{MALL}">김박사 몰(장보기)</a> · <a href="{YT}">유튜브 김박사 월드</a> · <a href="{up}about/">김박사 건강몰 소개</a></p></div></footer></body></html>"""


def guide_body(c: dict, cat: dict, g: dict) -> tuple[str, str]:
    others = '<h2>다른 성분 가이드</h2><nav class="chips">' + "".join(
        f'<a href="../{o["slug"]}/">{esc(o["name"])}</a>' for o in c.get("guides") or [] if o["slug"] != g["slug"]) + "</nav>"
    rows = "".join(f"<tr><td>{esc(f['text'])}</td><td>{esc(f['dose'])}</td></tr>" for f in g["functions"])
    items = clean((cat.get("products") or {}).get(g["slug"]) or [], c.get("drop_words") or [], g.get("match") or [g["name"]])
    prods = (f'<h2 id="items">쿠팡 검색 결과: {esc(g["keyword"])}<span class="ad">광고</span></h2>'
             f'<p class="note">쿠팡 검색 결과를 자동으로 보여 줍니다. 추천·보증이 아니며, 건강기능식품 여부·기능성·함량은 상품 페이지의 표시사항에서 위 기준과 비교해 확인하세요.</p>'
             f'<div class="grid">{"".join(card(p) for p in items[:20])}</div>') if items else '<p class="empty">상품 목록을 준비하고 있습니다.</p>'
    body = f"""<p class="crumb"><a href="../../">홈</a> › <a href="../">성분 가이드</a> › {esc(g['name'])}</p>
<h1 class="t">{esc(g['name'])} 고르는 법: 식약처 기능성·하루 섭취량·주의사항</h1>
<p class="lead">{esc(g['intro'])}</p>
<h2>식약처가 인정한 기능성 <small>{esc(g['aka'])}</small></h2>
<table class="fn"><thead><tr><th>기능성 내용(인정 문구)</th><th>1일 섭취량 기준</th></tr></thead><tbody>{rows}</tbody></table>
<p class="note">기능성 문구는 그 기능성 원료를 기준 섭취량만큼 넣어 인정받은 '건강기능식품'에만 표시할 수 있습니다. 같은 성분 이름이어도 일반식품에는 이 기능성이 없습니다.</p>
<h2>섭취 시 주의사항</h2><div class="box"><ul class="ck">{"".join(f"<li>{esc(x)}</li>" for x in g['cautions'])}</ul></div>
<h2>고를 때 확인할 것</h2><ul class="ck">{"".join(f"<li>{esc(x)}</li>" for x in g['choose'])}</ul>
{funnel(c, "guide-" + g["slug"], "guide")}
{prods}
{others}
<h2>출처</h2><ul class="src">{"".join(f'<li><a href="{esc(s["url"])}" rel="nofollow noopener" target="_blank">{esc(s["title"])}</a></li>' for s in g['sources'])}</ul>
<p class="note">내용 확인일 {esc(g['verified'])}. 기준은 바뀔 수 있으니 제품 표시사항과 식품안전나라에서 함께 확인하세요.</p>"""
    desc = f"{g['name']}({g['aka']}) 식약처 인정 기능성 문구, 1일 섭취량 기준, 섭취 시 주의사항과 고를 때 확인할 것을 한 페이지에 정리했습니다."
    return body, desc


def build(c: dict, cat: dict, out: Path) -> int:
    errs = check(c)
    if errs:
        for e in errs:
            print(f"::error title=김박사 건강몰 검사::{e}")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    base = c["url"].rstrip("/")
    today = dt.datetime.now(KST).date().isoformat()
    w = lambda rel, s: ((out / rel).parent.mkdir(parents=True, exist_ok=True), (out / rel).write_text(s, encoding="utf-8"))
    guides = c.get("guides") or []
    org = {"@type": "Organization", "name": "김박사 월드", "url": "https://drkimworld.com/"}
    gl = '<div class="gl">' + "".join(
        f'<a class="gc" href="{{up}}guide/{g["slug"]}/"><b>{esc(g["name"])}</b><small>{esc(g["aka"])}</small><p>{esc(g["functions"][0]["text"])}</p></a>' for g in guides) + "</div>"
    # 홈
    best = clean(cat.get("best") or [], c.get("drop_words") or [], [m for g in guides for m in g.get("match") or []])
    cat = {**cat, "best_shown": bool(best)}
    prods = cat.get("products") or {}
    chips = '<nav class="chips" aria-label="성분">' + "".join(f'<a href="#{g["slug"]}">{esc(g["name"])}</a>' for g in guides if prods.get(g["slug"])) + "</nav>"
    home = ['<section class="hero"><p class="kicker">김박사 건강몰</p><h1>영양제, 사기 전에<br>확인할 것만 모았습니다</h1>'
            '<p>성분마다 식약처가 인정한 기능성 문구, 하루 섭취량 기준, 섭취 시 주의사항을 먼저 정리했습니다. 확인한 다음 쿠팡에서 비교해 보세요.</p>'
            '<a class="btn" href="guide/">성분 가이드 보기</a></section>',
            '<h2>성분 가이드<small>기능성·섭취량·주의사항</small></h2>' + gl.replace("{up}", ""), funnel(c, "home")]
    rows = []
    for g in guides:
        items = clean(prods.get(g["slug"]) or [], c.get("drop_words") or [], g.get("match") or [g["name"]])
        if items:
            rows.append(f'<section class="row" id="{g["slug"]}"><h2>{esc(g["name"])}<span class="ad">광고</span><a class="more" href="guide/{g["slug"]}/">고르는 법 먼저 보기 ›</a></h2>'
                        f'<div class="grid">{"".join(card(p) for p in items[:5])}</div></section>')
    if rows:
        home.append('<h2 class="sec">성분별 쿠팡 상품<small>쿠팡 검색 결과 · 추천·보증 아님</small></h2>' + chips + "".join(rows))
    if best:
        home.append(f'<h2>헬스·건강식품 베스트<span class="ad">광고</span><small>쿠팡 카테고리 베스트</small></h2><div class="grid">{"".join(card(p) for p in best[:10])}</div><p><a href="best/">전체 보기 ›</a></p>')
    w("index.html", page(c, cat, f"{c['name']} — {c['tagline']}", "".join(home), "", "오메가3·루테인·밀크씨슬·홍삼 등 영양제의 식약처 인정 기능성, 하루 섭취량, 섭취 시 주의사항을 성분별로 정리한 가이드.", "home",
                         ld=[{"@context": "https://schema.org", "@type": "WebSite", "name": c["name"], "url": base + "/", "inLanguage": "ko-KR", "publisher": org}]))
    # 가이드 목록
    w("guide/index.html", page(c, cat, f"영양제 성분 가이드 | {c['name']}", '<p class="crumb"><a href="../">홈</a> › 성분 가이드</p><h1 class="t">영양제 성분 가이드</h1><p class="lead">성분마다 식약처 인정 기능성, 1일 섭취량 기준, 섭취 시 주의사항, 고를 때 확인할 것을 정리했습니다.</p>' + gl.replace("{up}", "../"),
                              "guide/", "영양제 성분별 식약처 인정 기능성·하루 섭취량·주의사항 가이드 모음.", "guide",
                              ld=[{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                                  {"@type": "ListItem", "position": 1, "name": "홈", "item": base + "/"},
                                  {"@type": "ListItem", "position": 2, "name": "성분 가이드", "item": base + "/guide/"}]}]))
    # 가이드
    lastmod = {"": today, "guide/": today}
    for g in guides:
        body, desc = guide_body(c, cat, g)
        p = f"guide/{g['slug']}/"
        title = f"{g['name']} 고르는 법: 식약처 기능성·하루 섭취량·주의사항 | {c['name']}"
        ld = [{"@context": "https://schema.org", "@type": "Article", "headline": f"{g['name']} 고르는 법: 식약처 기능성·하루 섭취량·주의사항",
               "description": desc, "inLanguage": "ko-KR", "dateModified": g["verified"], "author": org, "publisher": org, "mainEntityOfPage": base + "/" + p},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "홈", "item": base + "/"},
                  {"@type": "ListItem", "position": 2, "name": "성분 가이드", "item": base + "/guide/"},
                  {"@type": "ListItem", "position": 3, "name": g["name"], "item": base + "/" + p}]}]
        w(p + "index.html", page(c, cat, title, body, p, desc, g["slug"], ld=ld))
        seen = [x.get("seen", "") for x in (cat.get("products") or {}).get(g["slug"]) or []]
        lastmod[p] = max([g["verified"]] + seen)
    # 베스트(상품만 있는 페이지 — 검색 색인 제외)
    if best:
        w("best/index.html", page(c, cat, f"헬스·건강식품 베스트 | {c['name']}", f'<h1 class="t">헬스·건강식품 베스트<span class="ad">광고</span></h1><p class="lead">쿠팡 헬스/건강식품 카테고리 베스트를 자동으로 가져옵니다. 추천·보증이 아닙니다.</p><div class="grid">{"".join(card(p) for p in best)}</div>',
                                  "best/", "쿠팡 헬스·건강식품 카테고리 베스트.", "best", noindex=True))
    w("about/index.html", page(c, cat, f"김박사 건강몰 소개 | {c['name']}", f"""<h1 class="t">김박사 건강몰은</h1>
<p>미국 주식 미스터리 리포트를 무료로 만드는 <a href="{SITE}">김박사 월드</a>가 운영하는 영양제 정보·쇼핑 연결 사이트입니다.</p>
<p>성분 가이드는 식품의약품안전처가 인정한 기능성 문구와 공개된 섭취 시 주의사항을 옮겨 정리합니다. 질병의 예방·치료를 위한 정보가 아니며, 의사·약사의 상담을 대신하지 않습니다.</p>
<p>상품 목록은 쿠팡 파트너스가 제공하는 검색·베스트 결과를 자동으로 가져온 것입니다. 김박사 월드가 제품을 직접 써 보고 고른 것이 아니며, 효능·품질을 보증하지 않습니다. 가격·재고·배송·교환·환불은 쿠팡에서 처리됩니다.</p>
<p>{esc(DISCLOSURE)}</p>""", "about/", "김박사 건강몰 운영 방식과 대가성 안내.", ""))
    w("404.html", page(c, cat, f"페이지를 찾을 수 없습니다 | {c['name']}", '<h1 class="t">페이지를 찾을 수 없습니다</h1><p><a href="/">홈으로</a> · <a href="/guide/">성분 가이드</a></p>', "404.html", "페이지를 찾을 수 없습니다.", noindex=True))
    lastmod["about/"] = today
    w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
      + "".join(f"<url><loc>{esc(base)}/{u}</loc><lastmod>{d}</lastmod></url>" for u, d in lastmod.items()) + "</urlset>")
    # /best/ 는 막지 않는다(막으면 noindex를 못 읽음). 페이지의 noindex로 색인에서 뺀다
    w("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    print(f"김박사 건강몰 만들기: 가이드 {len(guides)} · 상품 있는 가이드 {len(cat.get('products') or {})} · 베스트 {len(best)} → {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--build", metavar="OUT")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    c = cfg()
    if a.check:
        errs = check(c)
        for e in errs:
            print(e)
        return 1 if errs else 0
    cat = fetch(c) if a.fetch else load_cat()
    if a.build:
        return build(c, cat, Path(a.build))
    return 0


if __name__ == "__main__":
    sys.exit(main())
