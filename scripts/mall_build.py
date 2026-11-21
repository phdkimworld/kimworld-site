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
import re
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
# 추적(2026-11-20 운영자 "몰 페이지 트래픽 다각화해서 체계적으로 추적해서 저장"): 화면 보기·쿠팡 클릭을 채널(src)·화면(pg)·칸(data-sl)별로
# 사이트 API /v1/mall 에 하루 합계로 보낸다(D1 mall_ev, 사람 정보 없음). src는 ?src=(사이트 /mall/ 입구가 넘김) > utm_source > 이 탭에서 처음 정한 값 > 리퍼러 묶음 > direct
TRACK = """<script>(function(){var A='https://api.drkimworld.com/v1/mall',P=document.body.dataset.pg||'other',q=new URLSearchParams(location.search),s;
function cl(x){return String(x||'').toLowerCase().replace(/[^a-z0-9._-]/g,'').slice(0,30)}
s=cl(q.get('src')||q.get('utm_source'));try{if(s)sessionStorage.setItem('kw_src',s);else s=sessionStorage.getItem('kw_src')||''}catch(e){}
if(!s){try{var h=document.referrer?new URL(document.referrer).hostname.replace(/^www\\./,''):'';if(h&&h!==location.hostname){s=/drkimworld\\.com$/.test(h)?'site':/google\\./.test(h)?'google':/naver\\./.test(h)?'naver':/daum\\.|kakao/.test(h)?'daum':/bing\\./.test(h)?'bing':/youtube|youtu\\.be/.test(h)?'youtube':/threads|instagram|facebook|blogspot|t\\.me/.test(h)?cl(h.split('.')[0]):'ref';try{sessionStorage.setItem('kw_src',s)}catch(e){}}}catch(e){}}
s=s||'direct';function b(o){o.src=s;o.pg=P;try{navigator.sendBeacon(A,JSON.stringify(o))}catch(e){}}
b({k:'view'});document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href^="https://link.coupang.com"]');if(!a)return;var w=a.closest('[data-sl]');b({k:'click',sl:w?w.dataset.sl:'other'})},true);})();</script>"""
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


# ---------- 화면 (2026-11-19 국내 쇼핑몰 구성으로 개편: 배너 캐러셀·카테고리 아이콘·가로 상품 줄·랭킹·정렬·하단 탭) ----------
# 쿠팡 브랜드를 흉내 내지 않는다(김박사 몰 고유 색·이름). 재촉 장치(카운트다운·남은 수량)는 넣지 않는다.
CSS = """
:root{--bg:#f4f3ef;--card:#fff;--ink:#141b24;--muted:#6b7280;--line:#e7e4dd;--accent:#f5b83d;--accent-ink:#0e1a2b;--navy:#0e1a2b;--red:#e0442f;--blue:#2563eb;--soft:#fff7e3}
@media (prefers-color-scheme:dark){:root{--bg:#0d1218;--card:#161d26;--ink:#e8eaee;--muted:#9aa3ae;--line:#26303c;--navy:#1d2a3a;--red:#ff7a66;--blue:#7aa7ff;--soft:#2a2414}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;padding-bottom:64px}
@media(min-width:900px){body{padding-bottom:0}}
a{color:inherit;text-decoration:none}.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
header{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
.top{display:flex;align-items:center;gap:12px;padding:10px 0}.logo{font-weight:900;font-size:21px;letter-spacing:-.5px;white-space:nowrap}.logo span{color:var(--accent)}
.tag{color:var(--muted);font-size:12px;display:none}@media(min-width:760px){.tag{display:inline}}
form.q{margin-left:auto;flex:1;max-width:420px;display:flex}form.q input{width:100%;padding:9px 14px;border:2px solid var(--accent);border-radius:999px;background:var(--card);color:var(--ink);font-size:14px;outline:none}
nav.cats{display:flex;gap:4px;overflow-x:auto;padding:0 0 8px;scrollbar-width:none}nav.cats::-webkit-scrollbar{display:none}
nav.cats a{flex:none;padding:6px 11px;border-radius:999px;font-size:13px;color:var(--muted)}nav.cats a.on{background:var(--navy);color:#fff;font-weight:700}
.disc{font-size:11.5px;color:var(--muted);padding:8px 0 0;margin:0}
/* 배너 캐러셀 */
.hero{position:relative;margin:12px 0 4px}.slides{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:10px;scrollbar-width:none;border-radius:16px}.slides::-webkit-scrollbar{display:none}
.slide{flex:0 0 100%;scroll-snap-align:start;border-radius:16px;padding:22px 20px;min-height:168px;display:flex;align-items:center;justify-content:space-between;gap:14px;position:relative;overflow:hidden}
@media(min-width:760px){.slide{flex-basis:calc(50% - 5px);min-height:190px}}
.slide h2{margin:0 0 6px;font-size:21px;line-height:1.25;letter-spacing:-.4px}.slide p{margin:0 0 12px;font-size:13px;opacity:.85}
.s1{background:var(--accent);color:var(--accent-ink)}.s2{background:var(--navy);color:#fff}.s3{background:#e8f0e3;color:#1d2a1d}.s4{background:#e7eefb;color:#152238}
@media (prefers-color-scheme:dark){.s3{background:#1f2a1f;color:#e3eedd}.s4{background:#1b2536;color:#dbe6f8}}
.slide .pill{display:inline-block;padding:8px 16px;border-radius:999px;background:var(--navy);color:#fff;font-weight:800;font-size:14px}.s2 .pill{background:var(--accent);color:var(--accent-ink)}
.slide .thumbs{display:flex;gap:6px;flex:none}.slide .thumbs span{width:62px;height:62px;border-radius:12px;background:#fff center/contain no-repeat;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.dots{display:flex;gap:5px;justify-content:center;margin-top:8px}.dots i{width:6px;height:6px;border-radius:9px;background:var(--line)}.dots i.on{width:16px;background:var(--accent)}
/* 카테고리 아이콘 */
.icons{display:grid;grid-template-columns:repeat(4,1fr);gap:12px 6px;margin:18px 0 6px;padding:16px 8px;background:var(--card);border-radius:16px;border:1px solid var(--line)}
@media(min-width:640px){.icons{grid-template-columns:repeat(6,1fr)}}@media(min-width:1000px){.icons{grid-template-columns:repeat(12,1fr)}}
.icons a{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:12px;text-align:center}.icons b{width:48px;height:48px;border-radius:16px;background:var(--soft);display:flex;align-items:center;justify-content:center;font-size:24px}
/* 입구 띠 */
.entry{margin:14px 0;padding:14px 16px;border-radius:14px;background:var(--soft);border:1px solid var(--accent);display:flex;gap:12px;align-items:center;justify-content:space-between}
.entry p{margin:0;font-size:13px}.entry b{display:block;font-size:15px;margin-bottom:2px}
.btn{display:inline-block;padding:10px 18px;border-radius:999px;background:var(--accent);color:var(--accent-ink);font-weight:800;white-space:nowrap;font-size:14px}
/* 섹션 */
.sec{margin:26px 0 0}.sec h2{font-size:18px;margin:0 0 10px;display:flex;align-items:baseline;gap:8px;letter-spacing:-.3px}.sec h2 small{font-size:12px;color:var(--muted);font-weight:400}.sec h2 a.more{margin-left:auto;font-size:13px;color:var(--muted);font-weight:400}
.row{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x proximity;padding-bottom:4px;scrollbar-width:thin}.row .card{flex:0 0 42%;scroll-snap-align:start}@media(min-width:640px){.row .card{flex-basis:23%}}@media(min-width:1000px){.row .card{flex-basis:16.4%}}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}@media(min-width:640px){.grid{grid-template-columns:repeat(3,1fr)}}@media(min-width:900px){.grid{grid-template-columns:repeat(4,1fr)}}@media(min-width:1100px){.grid{grid-template-columns:repeat(5,1fr)}}
.card{background:var(--card);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;border:1px solid var(--line)}
.card .im{aspect-ratio:1;background:#fff;display:flex;align-items:center;justify-content:center;position:relative}.card img{width:100%;height:100%;object-fit:contain}
.badge{position:absolute;left:6px;bottom:6px;font-size:10.5px;font-weight:800;padding:2px 7px;border-radius:6px;background:var(--blue);color:#fff}
.card .b{padding:9px 10px 11px;display:flex;flex-direction:column;gap:3px;flex:1}.card .n{font-size:13px;line-height:1.38;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.76em}
.pr{font-weight:900;font-size:16px;letter-spacing:-.3px}.pr .r{color:var(--red);margin-right:4px}.pr s{display:block;color:var(--muted);font-weight:400;font-size:11.5px}
/* 랭킹 */
.rank{display:grid;grid-template-columns:minmax(0,1fr);gap:8px}@media(min-width:760px){.rank{grid-template-columns:repeat(2,minmax(0,1fr))}}
.rank a{display:flex;align-items:center;gap:12px;min-width:0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px 8px 8px}
.rank em{font-style:normal;font-weight:900;font-size:18px;width:26px;text-align:center;color:var(--accent)}.rank a:nth-child(n+4) em{color:var(--muted)}
.rank .im{width:58px;height:58px;flex:none;border-radius:10px;background:#fff;overflow:hidden}.rank img{width:100%;height:100%;object-fit:contain}
.rank .t{flex:1;min-width:0}.rank .t div{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rank .t small{color:var(--muted);font-size:11.5px}.rank .p{font-weight:800;font-size:14px;white-space:nowrap}
/* 정렬 */
.sort{display:flex;gap:6px;margin:0 0 12px;flex-wrap:wrap}.sort button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 12px;border-radius:999px;font-size:12.5px;cursor:pointer}.sort button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
/* 하단 탭(휴대폰) */
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:20;background:var(--card);border-top:1px solid var(--line);display:grid;grid-template-columns:repeat(4,1fr);padding:6px 0 calc(6px + env(safe-area-inset-bottom))}
.tabbar a{display:flex;flex-direction:column;align-items:center;font-size:11px;color:var(--muted);gap:1px}.tabbar a b{font-size:19px;line-height:1.2}.tabbar a.on{color:var(--ink);font-weight:700}
@media(min-width:900px){.tabbar{display:none}}
footer{margin-top:40px;padding:22px 0 30px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}footer a{color:var(--ink);text-decoration:underline}
.empty{color:var(--muted);padding:30px 0;text-align:center}
"""

REL = 'rel="sponsored nofollow noopener" target="_blank"'


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def price_html(p: dict) -> str:
    if not p.get("price"):
        return ""
    rate = f'<span class="r">{p["rate"]}%</span>' if p.get("rate") else ""
    orig = f'<s>{p["orig"]:,}원</s>' if p.get("orig") else ""
    return f'<div class="pr">{orig}{rate}{p["price"]:,}원</div>'


def card(p: dict) -> str:
    img = f'<img src="{esc(p["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if p.get("image") else ""
    badge = '<span class="badge">로켓배송</span>' if p.get("rocket") else ""
    return (f'<a class="card" href="{esc(p["url"])}" {REL} data-p="{int(p.get("price") or 0)}" data-r="{int(p.get("rate") or 0)}">'
            f'<div class="im">{img}{badge}</div><div class="b"><div class="n">{esc(p["name"])}</div>{price_html(p)}</div></a>')


def page(c: dict, cat: dict, title: str, body: str, on: str = "", desc: str = "", depth: int = 0) -> str:
    up = "../" * depth
    nav = [f'<a href="{up}" class="{"on" if on == "home" else ""}">홈</a>', f'<a href="{up}deals/" class="{"on" if on == "deals" else ""}">오늘의 특가</a>']
    nav += [f'<a href="{up}c/{k["slug"]}/" class="{"on" if on == k["slug"] else ""}">{esc(k["name"])}</a>' for k in c.get("categories") or [] if (cat.get("cats") or {}).get(k["slug"])]
    tabs = [("home", "", "🏠", "홈"), ("deals", "deals/", "🔥", "특가"), ("cats", "categories/", "☰", "카테고리"), ("search", "search/", "🔍", "검색")]
    tabbar = "".join(f'<a href="{up}{h}" class="{"on" if on == k else ""}"><b>{i}</b>{n}</a>' for k, h, i, n in tabs)
    upd = esc(cat.get("updated") or "")
    pg = on if on in ("home", "deals", "search", "cats", "about") else (f"c-{on}" if on else "other")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title><meta name="description" content="{esc(desc or c['tagline'])}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc or c['tagline'])}"><meta name="theme-color" content="#f5b83d">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23f5b83d'/%3E%3Ctext x='32' y='44' font-size='34' text-anchor='middle' font-family='sans-serif' font-weight='800' fill='%230e1a2b'%3E몰%3C/text%3E%3C/svg%3E">
<style>{CSS}</style></head><body data-pg="{pg}">
<header><div class="wrap"><div class="top"><a class="logo" href="{up}">김박사 <span>몰</span></a><span class="tag">{esc(c['tagline'])}</span>
<form class="q" action="{up}search/" role="search"><input name="q" type="search" placeholder="오늘 뭐 사시나요?" aria-label="상품 찾기"></form></div>
<nav class="cats" aria-label="카테고리">{''.join(nav)}</nav></div></header>
<main class="wrap"><p class="disc">{esc(DISCLOSURE)} 가격·재고·배송은 쿠팡 상품 페이지가 기준입니다.</p>
{body}</main>
<footer><div class="wrap"><p>{esc(DISCLOSURE)} 진열은 쿠팡의 오늘의 특가·카테고리 베스트에서 자동으로 가져오며 추천·보증이 아닙니다. 가격·재고·사양은 쿠팡 상품 페이지에서 확인하세요{f" · 마지막 갱신 {upd}(한국 시각)" if upd else ""}.</p>
<p>미국 주식 미스터리 무료 리포트 <a href="{SITE}">김박사 월드</a> · <a href="{YT}">유튜브 김박사 월드</a> · <a href="{up}about/">김박사 몰 소개</a></p></div></footer>
<nav class="tabbar" aria-label="바로가기">{tabbar}</nav>{TRACK}</body></html>"""


def entry(cat: dict, depth: int = 0) -> str:
    go = (cat.get("entry") or {}).get("go")
    if not go:
        return ""
    return (f'<section class="entry" data-sl="entry"><p><b>쿠팡 장보기는 이 문으로</b>들어간 뒤 24시간 안에 무엇을 사시든 같은 가격에 김박사 월드 운영에 도움이 됩니다.</p>'
            f'<a class="btn" href="{esc(go)}" {REL}>쿠팡 들어가기</a></section>')


def hero(c: dict, cat: dict) -> str:
    go = (cat.get("entry") or {}).get("go")
    deals, cats = cat.get("deals") or [], cat.get("cats") or {}
    th = lambda items: '<div class="thumbs">' + "".join(f'<span style="background-image:url({esc(p["image"])})"></span>' for p in items[:3] if p.get("image")) + "</div>"
    by = {k["slug"]: k for k in c.get("categories") or []}
    sl = []
    if go:
        sl.append(f'<a class="slide s1" href="{esc(go)}" {REL}><div><h2>쿠팡 장보기,<br>김박사 몰 입구로</h2><p>같은 가격 · 채널 운영에 작은 도움</p><span class="pill">쿠팡 들어가기</span></div></a>')
    if deals:
        sl.append(f'<a class="slide s2" href="deals/"><div><h2>오늘의 특가<br>{len(deals)}개</h2><p>매일 아침 새로 바뀝니다</p><span class="pill">특가 보기</span></div>{th(deals)}</a>')
    for slug, title, sub, cls in (("food", "이번 주 장보기<br>식품 베스트", "생활용품·주방까지 한 번에", "s3"), ("digital", "차트 보는 분의<br>가전·디지털", "모니터·주변기기 베스트", "s4")):
        if cats.get(slug) and slug in by:
            sl.append(f'<a class="slide {cls}" href="c/{slug}/"><div><h2>{title}</h2><p>{sub}</p><span class="pill">보러 가기</span></div>{th(cats[slug])}</a>')
    if not sl:
        return ""
    dots = "".join(f'<i class="{"on" if i == 0 else ""}"></i>' for i in range(len(sl)))
    js = """<script>(function(){var s=document.querySelector('.slides'),d=document.querySelectorAll('.dots i');if(!s)return;
function idx(){return Math.round(s.scrollLeft/(s.firstElementChild.offsetWidth+10))}
s.addEventListener('scroll',function(){var i=idx();d.forEach(function(x,j){x.classList.toggle('on',j===i)})},{passive:true});
var t=setInterval(function(){if(document.hidden)return;var n=idx()+1;if(n*(s.firstElementChild.offsetWidth+10)>=s.scrollWidth-5)n=0;s.scrollTo({left:n*(s.firstElementChild.offsetWidth+10),behavior:'smooth'})},5000);
s.addEventListener('pointerdown',function(){clearInterval(t)},{once:true});})();</script>"""
    return f'<section class="hero" data-sl="hero" aria-label="기획전"><div class="slides">{"".join(sl)}</div><div class="dots">{dots}</div></section>{js}'


def icons(c: dict, cat: dict, up: str = "") -> str:
    cats = cat.get("cats") or {}
    items = [f'<a href="{up}deals/"><b>🔥</b>오늘의 특가</a>'] + [f'<a href="{up}c/{k["slug"]}/"><b>{k.get("icon", "🛒")}</b>{esc(k["name"])}</a>' for k in c.get("categories") or [] if cats.get(k["slug"])]
    return f'<nav class="icons" aria-label="카테고리">{"".join(items)}</nav>'


def ranking(c: dict, cat: dict) -> str:
    """카테고리 베스트 1위들을 번갈아 모은 10개(쿠팡 베스트 순위 그대로 — 우리가 매긴 순위가 아님)."""
    cats = cat.get("cats") or {}
    order = [k for k in c.get("categories") or [] if cats.get(k["slug"])]
    picks, i = [], 0
    while len(picks) < 10 and order and i < 30:
        for k in order:
            if i < len(cats[k["slug"]]) and len(picks) < 10:
                picks.append((k, cats[k["slug"]][i]))
        i += 1
    if not picks:
        return ""
    rows = "".join(f'<a href="{esc(p["url"])}" {REL}><em>{n}</em><div class="im">' + (f'<img src="{esc(p["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if p.get("image") else "")
                   + f'</div><div class="t"><div>{esc(p["name"])}</div><small>{esc(k["name"])} 베스트 {cats[k["slug"]].index(p) + 1}위</small></div><div class="p">{p["price"]:,}원</div></a>' if p.get("price") else "" for n, (k, p) in enumerate(picks, 1))
    return f'<section class="sec" data-sl="rank"><h2>카테고리 베스트 모아보기 <small>쿠팡 카테고리 베스트 순위</small></h2><div class="rank">{rows}</div></section>'


SORT_JS = """<div class="sort" role="group" aria-label="정렬"><button class="on" data-s="0">추천순</button><button data-s="p">낮은 가격순</button><button data-s="P">높은 가격순</button><button data-s="r">할인율순</button></div>"""
SORT_RUN = """<script>(function(){var g=document.querySelector('.grid'),b=document.querySelectorAll('.sort button');if(!g)return;var o=[].slice.call(g.children);
b.forEach(function(x){x.onclick=function(){b.forEach(function(y){y.classList.remove('on')});x.classList.add('on');var s=x.dataset.s,a=o.slice();
if(s==='p')a.sort(function(m,n){return(+m.dataset.p||9e9)-(+n.dataset.p||9e9)});if(s==='P')a.sort(function(m,n){return(+n.dataset.p)-(+m.dataset.p)});if(s==='r')a.sort(function(m,n){return(+n.dataset.r)-(+m.dataset.r)});
a.forEach(function(e){g.appendChild(e)})}})})();</script>"""


def build(c: dict, cat: dict, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    cats = cat.get("cats") or {}
    deals = cat.get("deals") or []
    w = lambda rel, s: ((out / rel).parent.mkdir(parents=True, exist_ok=True), (out / rel).write_text(s, encoding="utf-8"))
    # 홈: 배너 → 카테고리 아이콘 → 입구 띠 → 오늘의 특가(가로) → 카테고리 베스트 모아보기(랭킹) → 카테고리별 가로 줄
    b = [hero(c, cat), icons(c, cat), entry(cat)]
    if deals:
        b.append(f'<section class="sec" data-sl="deals"><h2>🔥 오늘의 특가 <small>매일 아침 바뀜</small><a class="more" href="deals/">전체 {len(deals)}개 ›</a></h2><div class="row">' + "".join(card(p) for p in deals[:14]) + "</div></section>")
    b.append(ranking(c, cat))
    for grp in ("장보기", "취향"):
        for k in [k for k in c.get("categories") or [] if k.get("group") == grp and cats.get(k["slug"])]:
            b.append(f'<section class="sec" data-sl="row-{k["slug"]}"><h2>{k.get("icon", "")} {esc(k["name"])} <small>베스트</small><a class="more" href="c/{k["slug"]}/">더보기 ›</a></h2><div class="row">' + "".join(card(p) for p in cats[k["slug"]][:12]) + "</div></section>")
    if not deals and not cats:
        b.append('<p class="empty">진열을 준비하고 있습니다. 위 입구로 쿠팡에 들어가실 수 있습니다.</p>')
    w("index.html", page(c, cat, f"{c['name']} — {c['tagline']}", "".join(b), "home", "오늘의 특가와 식품·생활·주방·가전·스포츠·도서 베스트를 매일 모아 둔 김박사 월드 시청자 장보기 입구."))
    # 특가
    w("deals/index.html", page(c, cat, f"오늘의 특가 | {c['name']}", entry(cat, 1) + f'<section class="sec" data-sl="grid"><h2>🔥 오늘의 특가 <small>{len(deals)}개 · 매일 아침 바뀜</small></h2>{SORT_JS}<div class="grid">' + "".join(card(p) for p in deals) + "</div></section>" + SORT_RUN, "deals", depth=1))
    # 카테고리 모음
    w("categories/index.html", page(c, cat, f"카테고리 | {c['name']}", icons(c, cat, "../") + entry(cat, 1), "cats", depth=1))
    # 카테고리
    n = 0
    for k in c.get("categories") or []:
        items = cats.get(k["slug"]) or []
        if not items:
            continue
        w(f"c/{k['slug']}/index.html", page(c, cat, f"{k['name']} 베스트 | {c['name']}", entry(cat, 2) + f'<section class="sec" data-sl="grid"><h2>{k.get("icon", "")} {esc(k["name"])} 베스트 <small>쿠팡 카테고리 베스트 {len(items)}</small></h2>{SORT_JS}<div class="grid">' + "".join(card(p) for p in items) + "</div></section>" + SORT_RUN, k["slug"], f"쿠팡 {k['name']} 베스트 상품 모음.", depth=2))
        n += 1
    # 검색(브라우저 안) — 진열 전체를 작은 JSON으로
    idx = [{"n": p["name"], "u": p["url"], "i": p.get("image", ""), "p": p.get("price", 0), "r": p.get("rate", 0), "o": p.get("orig", 0), "k": bool(p.get("rocket"))}
           for p in deals + [p for v in cats.values() for p in v]]
    seen, uniq = set(), []
    for x in idx:
        if x["n"] not in seen:
            seen.add(x["n"]); uniq.append(x)
    w("catalog.json", json.dumps(uniq, ensure_ascii=False, separators=(",", ":")))
    js = """<div id="res" class="grid"></div><p id="none" class="empty" hidden>찾는 상품이 진열에 없습니다. 위 입구로 쿠팡에 들어가 검색해 보세요.</p>
<script>(function(){var q=new URLSearchParams(location.search).get('q')||'';var f=document.querySelector('form.q input');if(f)f.value=q;
var h=document.getElementById('hq');h.textContent=q?'“'+q+'” 찾기':'상품 찾기';
fetch('../catalog.json').then(function(r){return r.json()}).then(function(a){var t=q.trim().toLowerCase().split(/\\s+/).filter(Boolean);
var m=a.filter(function(x){var n=x.n.toLowerCase();return t.length&&t.every(function(w){return n.indexOf(w)>=0})});
var e=function(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
document.getElementById('res').innerHTML=m.slice(0,60).map(function(x){return '<a class="card" href="'+e(x.u)+'" rel="sponsored nofollow noopener" target="_blank"><div class="im">'+(x.i?'<img src="'+e(x.i)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'')+(x.k?'<span class="badge">로켓배송</span>':'')+'</div><div class="b"><div class="n">'+e(x.n)+'</div>'+(x.p?'<div class="pr">'+(x.r?'<span class="r">'+x.r+'%</span>':'')+x.p.toLocaleString()+'원</div>':'')+'</div></a>'}).join('');
document.getElementById('none').hidden=m.length>0;});})();</script>"""
    w("search/index.html", page(c, cat, f"상품 찾기 | {c['name']}", entry(cat, 1) + '<section class="sec" data-sl="search"><h2 id="hq">상품 찾기</h2>' + js + "</section>", "search", depth=1))
    w("about/index.html", page(c, cat, f"김박사 몰 소개 | {c['name']}", f"""<section class="sec"><h2>김박사 몰은</h2>
<p>미국 주식 미스터리 리포트와 영상을 무료로 만드는 <a href="{SITE}">김박사 월드</a>가 운영하는 쿠팡 파트너스 장보기 입구입니다.
쿠팡에 들어가실 때 이곳의 링크를 거치시면, 같은 가격으로 사시는 물건의 일부가 수수료로 채널 운영에 쓰입니다.</p>
<p>진열은 쿠팡이 공개하는 오늘의 특가와 카테고리 베스트를 매일 자동으로 가져옵니다. 순위도 쿠팡 카테고리 베스트 순위 그대로입니다. 김박사 월드가 상품을 직접 써 보고 고른 것이 아니며, 효능·품질을 보증하지 않습니다.
가격·재고·배송·교환·환불은 모두 쿠팡에서 처리됩니다.</p><p>{esc(DISCLOSURE)}</p></section>""", "about", depth=1))
    urls = ["", "deals/", "categories/", "about/"] + [f"c/{k['slug']}/" for k in c.get("categories") or [] if cats.get(k["slug"])]
    base = (c.get("url") or "").rstrip("/")
    if base:
        w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{base}/{u}</loc></url>" for u in urls) + "</urlset>")
    # IndexNow 키 파일(2026-11-20 몰 검색 유입): 사이트와 같은 공개 키. mall.yml 이 배포 뒤 몰 주소를 빙·네이버에 알린다
    try:
        key = str(((yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8")) or {}).get("seo") or {}).get("indexnow_key") or "")
    except Exception:
        key = ""
    if re.fullmatch(r"[0-9a-f]{8,128}", key):
        w(f"{key}.txt", key)
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
