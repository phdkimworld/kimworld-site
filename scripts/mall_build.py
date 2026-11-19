#!/usr/bin/env python3
"""김박사 몰 — 정적 쇼핑몰 만들기(운영자 지시 2026-11-19 "블로거 말고 제대로된 쇼핑몰로 만들어").

1) 받기(--fetch): 쿠팡 파트너스 API — 오늘의 특가(goldbox, 하위 ID mallgb), 카테고리 베스트(bestcategories/{id}, 카테고리별 하위 ID),
   입구 단축 링크(deeplink 쿠팡 첫 화면, mallgo, 처음 한 번). 결과는 mall/catalog.json(공개 저장소 — 상품 이름·가격은 어차피 몰에 공개).
   실패한 칸은 지난 값을 그대로 둔다. 하루 1회(mall.yml)면 API 호출 약 12회.
2) 만들기(--build <출력 폴더>): 홈(입구·특가·카테고리별 8개) · /c/<slug>/(카테고리 전체) · /deals/ · /search/(브라우저 안 검색) · /about/ ·
   sitemap.xml · robots.txt. 모든 쿠팡 링크는 rel="sponsored nofollow noopener", 모든 화면 위·아래에 대가성 문구.
설정: mall/mall.yaml. 사용: python3 scripts/mall_build.py --fetch --build dist-mall
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

CFG = ROOT / "mall" / "mall.yaml"
CAT = ROOT / "mall" / "catalog.json"
BEST = "/v2/providers/affiliate_open_api/apis/openapi/products/bestcategories/"
DISCLOSURE = "김박사 몰은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SITE = "https://drkimworld.com/?utm_source=mall&utm_medium=web"
YT = "https://www.youtube.com/@drkimworld"
KST = dt.timezone(dt.timedelta(hours=9))


def cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}


def get(path: str, q: dict, access: str, secret: str) -> dict:
    query = urllib.parse.urlencode(q)
    req = urllib.request.Request(f"{cs.DOMAIN}{path}?{query}", headers={
        "Authorization": cs.authorization("GET", path, query, access, secret, dt.datetime.now(dt.timezone.utc)),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(c: dict) -> dict:
    access, secret = os.environ.get("COUPANG_ACCESS_KEY", "").strip(), os.environ.get("COUPANG_SECRET_KEY", "").strip()
    cat = json.loads(CAT.read_text(encoding="utf-8")) if CAT.exists() else {}
    if not (access and secret):
        print("::notice title=김박사 몰::쿠팡 키 없음 — 저장된 진열로 만든다")
        return cat
    ok = 0
    try:
        deals, _ = cs.parse_deals(get(cs.GOLDBOX_PATH, {"subId": c["deal_subid"], "imageSize": "230x230"}, access, secret))
        if deals:
            cat["deals"] = deals; ok += 1
    except Exception as e:
        print(f"::warning title=김박사 몰::오늘의 특가 실패 {type(e).__name__}")
    cats = cat.setdefault("cats", {})
    for k in c.get("categories") or []:
        try:
            items, _ = cs.parse_deals(get(BEST + str(k["id"]), {"limit": int(c.get("per_category") or 30), "subId": k["sub"], "imageSize": "230x230"}, access, secret))
            if items:
                cats[k["slug"]] = items; ok += 1
        except Exception as e:
            print(f"::warning title=김박사 몰::{k['name']} 실패 {type(e).__name__} {str(e)[:80]}")
    ent = cat.setdefault("entry", {})
    if not ent.get("go"):
        try:
            import yt_shop as ys
            m = ys.deeplink(["https://www.coupang.com/"], c["entry_subid"], access, secret)
            ent["go"] = next(iter(m.values()), "") if m else ""
        except Exception as e:
            print(f"::warning title=김박사 몰::입구 링크 실패 {type(e).__name__}")
    if ok:
        cat["updated"] = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"::notice title=김박사 몰::받은 칸 {ok}/{1 + len(c.get('categories') or [])} · 특가 {len(cat.get('deals') or [])} · 카테고리 {sum(len(v) for v in cats.values())}")
    return cat


# ---------- 화면 ----------
CSS = """
:root{--bg:#f7f6f2;--card:#fff;--ink:#16202c;--muted:#6b7280;--line:#e6e3dc;--accent:#f5b83d;--accent-ink:#0e1a2b;--red:#d9402b;--blue:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#0f141b;--card:#171e27;--ink:#e8eaee;--muted:#9aa3ae;--line:#2a3340;--accent:#f5b83d;--accent-ink:#0e1a2b;--red:#ff7a66;--blue:#7aa7ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
a{color:inherit}.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
header{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.top{display:flex;align-items:center;gap:12px;padding:10px 0}.logo{font-weight:800;font-size:20px;text-decoration:none;white-space:nowrap}.logo span{color:var(--accent)}
.tag{color:var(--muted);font-size:12px;display:none}@media(min-width:720px){.tag{display:inline}}
form.q{margin-left:auto;flex:1;max-width:360px;display:flex}form.q input{width:100%;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:var(--bg);color:var(--ink);font-size:14px}
nav.cats{display:flex;gap:6px;overflow-x:auto;padding:0 0 10px;scrollbar-width:none}nav.cats::-webkit-scrollbar{display:none}
nav.cats a{flex:none;padding:6px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:13px;background:var(--bg)}nav.cats a.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent);font-weight:700}
.disc{font-size:12px;color:var(--muted);padding:8px 0}
.entry{margin:16px 0;padding:20px 16px;border-radius:16px;background:var(--card);border:2px solid var(--accent);display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
.entry h1{margin:0 0 4px;font-size:20px}.entry p{margin:0;color:var(--muted);font-size:13px}
.btn{display:inline-block;padding:11px 20px;border-radius:999px;background:var(--accent);color:var(--accent-ink);font-weight:800;text-decoration:none;white-space:nowrap}
.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--ink);font-weight:600;padding:7px 14px;font-size:13px}
h2{font-size:18px;margin:26px 0 10px;display:flex;align-items:baseline;gap:8px}h2 small{font-size:12px;color:var(--muted);font-weight:400}h2 a.more{margin-left:auto;font-size:13px;color:var(--muted);text-decoration:none}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}@media(min-width:640px){.grid{grid-template-columns:repeat(3,1fr)}}@media(min-width:900px){.grid{grid-template-columns:repeat(4,1fr)}}@media(min-width:1100px){.grid.wide{grid-template-columns:repeat(5,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;text-decoration:none}
.card .im{aspect-ratio:1;background:#fff;display:flex;align-items:center;justify-content:center;position:relative}.card img{width:100%;height:100%;object-fit:contain}
.badge{position:absolute;left:6px;top:6px;font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;background:var(--blue);color:#fff}
.card .b{padding:9px 10px 11px;display:flex;flex-direction:column;gap:4px;flex:1}.card .n{font-size:13px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.7em}
.pr{font-weight:800;font-size:15px}.pr .r{color:var(--red);margin-right:4px}.pr s{color:var(--muted);font-weight:400;font-size:12px;margin-left:4px}
.go{margin-top:auto;font-size:12px;color:var(--muted)}
footer{margin-top:40px;padding:22px 0 40px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}footer a{color:var(--ink)}
.empty{color:var(--muted);padding:30px 0;text-align:center}
"""


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def card(p: dict) -> str:
    rate = f'<span class="r">{p["rate"]}%</span>' if p.get("rate") else ""
    orig = f'<s>{p["orig"]:,}원</s>' if p.get("orig") else ""
    price = f'<div class="pr">{rate}{p["price"]:,}원{orig}</div>' if p.get("price") else ""
    img = f'<img src="{esc(p["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if p.get("image") else ""
    badge = '<span class="badge">로켓배송</span>' if p.get("rocket") else ""
    return (f'<a class="card" href="{esc(p["url"])}" rel="sponsored nofollow noopener" target="_blank">'
            f'<div class="im">{img}{badge}</div><div class="b"><div class="n">{esc(p["name"])}</div>{price}<div class="go">쿠팡에서 보기 ›</div></div></a>')


def page(c: dict, cat: dict, title: str, body: str, on: str = "", desc: str = "", depth: int = 0) -> str:
    up = "../" * depth
    nav = [f'<a href="{up}" class="{"on" if on == "home" else ""}">홈</a>', f'<a href="{up}deals/" class="{"on" if on == "deals" else ""}">오늘의 특가</a>']
    nav += [f'<a href="{up}c/{k["slug"]}/" class="{"on" if on == k["slug"] else ""}">{esc(k["name"])}</a>' for k in c.get("categories") or [] if (cat.get("cats") or {}).get(k["slug"])]
    upd = esc(cat.get("updated") or "")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc or c['tagline'])}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc or c['tagline'])}"><meta name="theme-color" content="#f5b83d">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23f5b83d'/%3E%3Ctext x='32' y='44' font-size='34' text-anchor='middle' font-family='sans-serif' font-weight='800' fill='%230e1a2b'%3E몰%3C/text%3E%3C/svg%3E">
<style>{CSS}</style></head><body>
<header><div class="wrap"><div class="top"><a class="logo" href="{up}">김박사 <span>몰</span></a><span class="tag">{esc(c['tagline'])}</span>
<form class="q" action="{up}search/" role="search"><input name="q" type="search" placeholder="상품 찾기" aria-label="상품 찾기"></form></div>
<nav class="cats" aria-label="카테고리">{''.join(nav)}</nav></div></header>
<main class="wrap"><p class="disc">{esc(DISCLOSURE)} 가격·재고·배송은 쿠팡 상품 페이지가 기준입니다.</p>
{body}</main>
<footer><div class="wrap"><p>{esc(DISCLOSURE)} 진열은 쿠팡의 오늘의 특가·카테고리 베스트에서 자동으로 가져오며 추천·보증이 아닙니다. 가격·재고·사양은 쿠팡 상품 페이지에서 확인하세요{f" · 마지막 갱신 {upd}(한국 시각)" if upd else ""}.</p>
<p>미국 주식 미스터리 무료 리포트 <a href="{SITE}">김박사 월드</a> · <a href="{YT}">유튜브 김박사 월드</a> · <a href="{up}about/">김박사 몰 소개</a></p></div></footer></body></html>"""


def entry(cat: dict, depth: int = 0) -> str:
    go = (cat.get("entry") or {}).get("go")
    if not go:
        return ""
    return (f'<section class="entry"><div><h1>쿠팡 장보기, 이 문으로 들어가 주세요</h1>'
            f'<p>들어간 뒤 24시간 안에 무엇을 사시든 같은 가격에 김박사 월드 운영에 도움이 됩니다.</p></div>'
            f'<a class="btn" href="{esc(go)}" rel="sponsored nofollow noopener" target="_blank">쿠팡 들어가기</a></section>')


def build(c: dict, cat: dict, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    cats = cat.get("cats") or {}
    deals = cat.get("deals") or []
    w = lambda rel, s: ((out / rel).parent.mkdir(parents=True, exist_ok=True), (out / rel).write_text(s, encoding="utf-8"))
    # 홈
    b = [entry(cat)]
    if deals:
        b.append(f'<h2>오늘의 특가 <small>매일 바뀜</small><a class="more" href="deals/">전체 {len(deals)}개 ›</a></h2><div class="grid wide">' + "".join(card(p) for p in deals[:10]) + "</div>")
    for grp in ("장보기", "취향"):
        for k in [k for k in c.get("categories") or [] if k.get("group") == grp and cats.get(k["slug"])]:
            b.append(f'<h2>{esc(k["name"])} <small>{grp} · 베스트</small><a class="more" href="c/{k["slug"]}/">전체 ›</a></h2><div class="grid">' + "".join(card(p) for p in cats[k["slug"]][:8]) + "</div>")
    if not deals and not cats:
        b.append('<p class="empty">진열을 준비하고 있습니다. 위 입구로 쿠팡에 들어가실 수 있습니다.</p>')
    w("index.html", page(c, cat, f"{c['name']} — {c['tagline']}", "".join(b), "home", "오늘의 특가와 식품·생활·주방·가전·스포츠·도서 베스트를 매일 모아 둔 김박사 월드 시청자 장보기 입구."))
    # 특가
    w("deals/index.html", page(c, cat, f"오늘의 특가 | {c['name']}", entry(cat, 1) + '<h2>오늘의 특가 <small>매일 바뀜</small></h2><div class="grid wide">' + "".join(card(p) for p in deals) + "</div>", "deals", depth=1))
    # 카테고리
    n = 0
    for k in c.get("categories") or []:
        items = cats.get(k["slug"]) or []
        if not items:
            continue
        w(f"c/{k['slug']}/index.html", page(c, cat, f"{k['name']} 베스트 | {c['name']}", entry(cat, 2) + f'<h2>{esc(k["name"])} 베스트 <small>쿠팡 카테고리 베스트 {len(items)}</small></h2><div class="grid wide">' + "".join(card(p) for p in items) + "</div>", k["slug"], f"쿠팡 {k['name']} 베스트 상품 모음.", depth=2))
        n += 1
    # 검색(브라우저 안) — 진열 전체를 작은 JSON으로
    idx = [{"n": p["name"], "u": p["url"], "i": p.get("image", ""), "p": p.get("price", 0), "r": p.get("rate", 0), "o": p.get("orig", 0), "k": bool(p.get("rocket"))}
           for p in deals + [p for v in cats.values() for p in v]]
    seen, uniq = set(), []
    for x in idx:
        if x["n"] not in seen:
            seen.add(x["n"]); uniq.append(x)
    w("catalog.json", json.dumps(uniq, ensure_ascii=False, separators=(",", ":")))
    js = """<div id="res" class="grid wide"></div><p id="none" class="empty" hidden>찾는 상품이 진열에 없습니다. 위 입구로 쿠팡에 들어가 검색해 보세요.</p>
<script>(function(){var q=new URLSearchParams(location.search).get('q')||'';var f=document.querySelector('form.q input');if(f)f.value=q;
var h=document.getElementById('hq');h.textContent=q?'“'+q+'” 찾기':'상품 찾기';
fetch('../catalog.json').then(function(r){return r.json()}).then(function(a){var t=q.trim().toLowerCase().split(/\\s+/).filter(Boolean);
var m=a.filter(function(x){var n=x.n.toLowerCase();return t.length&&t.every(function(w){return n.indexOf(w)>=0})});
var e=function(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
document.getElementById('res').innerHTML=m.slice(0,60).map(function(x){return '<a class="card" href="'+e(x.u)+'" rel="sponsored nofollow noopener" target="_blank"><div class="im">'+(x.i?'<img src="'+e(x.i)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'')+(x.k?'<span class="badge">로켓배송</span>':'')+'</div><div class="b"><div class="n">'+e(x.n)+'</div>'+(x.p?'<div class="pr">'+(x.r?'<span class="r">'+x.r+'%</span>':'')+x.p.toLocaleString()+'원</div>':'')+'<div class="go">쿠팡에서 보기 ›</div></div></a>'}).join('');
document.getElementById('none').hidden=m.length>0;});})();</script>"""
    w("search/index.html", page(c, cat, f"상품 찾기 | {c['name']}", entry(cat, 1) + '<h2 id="hq">상품 찾기</h2>' + js, "", depth=1))
    w("about/index.html", page(c, cat, f"김박사 몰 소개 | {c['name']}", f"""<h2>김박사 몰은</h2>
<p>미국 주식 미스터리 리포트와 영상을 무료로 만드는 <a href="{SITE}">김박사 월드</a>가 운영하는 쿠팡 파트너스 장보기 입구입니다.
쿠팡에 들어가실 때 이곳의 링크를 거치시면, 같은 가격으로 사시는 물건의 일부가 수수료로 채널 운영에 쓰입니다.</p>
<p>진열은 쿠팡이 공개하는 오늘의 특가와 카테고리 베스트를 매일 자동으로 가져옵니다. 김박사 월드가 상품을 직접 써 보고 고른 것이 아니며, 효능·품질을 보증하지 않습니다.
가격·재고·배송·교환·환불은 모두 쿠팡에서 처리됩니다.</p><p>{esc(DISCLOSURE)}</p>""", "", depth=1))
    urls = ["", "deals/", "about/"] + [f"c/{k['slug']}/" for k in c.get("categories") or [] if cats.get(k["slug"])]
    base = (c.get("url") or "").rstrip("/")
    if base:
        w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{base}/{u}</loc></url>" for u in urls) + "</urlset>")
    w("robots.txt", "User-agent: *\nAllow: /\n" + (f"Sitemap: {base}/sitemap.xml\n" if base else ""))
    print(f"김박사 몰 만들기: 특가 {len(deals)} · 카테고리 {n} · 검색 {len(uniq)}개 → {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--build", metavar="OUT")
    a = ap.parse_args()
    c = cfg()
    cat = fetch(c) if a.fetch else (json.loads(CAT.read_text(encoding="utf-8")) if CAT.exists() else {})
    if a.build:
        return build(c, cat, Path(a.build))
    return 0


if __name__ == "__main__":
    sys.exit(main())
