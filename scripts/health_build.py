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
import re
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
import mall_track  # noqa: E402

CFG = ROOT / "health" / "health.yaml"
CAT = ROOT / "health" / "catalog.json"
RES = ROOT / "health" / "research.json"  # 건강월드 리서치 스냅숏(scripts/health_research_sync.py)
BEST = "/v2/providers/affiliate_open_api/apis/openapi/products/bestcategories/"
DISCLOSURE = "김박사 건강몰은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SITE = "https://drkimworld.com/?utm_source=health&utm_medium=web"
MALL = "https://mall.drkimworld.com/?utm_source=health"
YT = "https://www.youtube.com/channel/UCNh9LrCUc0nTPKLMWPhnviw"  # 김박사 건강월드(2026-11-24: 본 채널 @drkimworld 대신 건강 채널로)
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
    # 시청자 프로필(2026-11-24): 코드 형식·가이드 존재·금지 낱말, profile_map 은 있는 코드만
    codes = set()
    gs = {g.get("slug") for g in c.get("guides") or []}
    for pr in c.get("profiles") or []:
        code = str(pr.get("code", ""))
        if not re.fullmatch(r"[a-z]{2,8}", code) or code in codes:
            errs.append(f"프로필 코드 '{code}': 영문 소문자 2~8자, 중복 금지")
        codes.add(code)
        for s in pr.get("guides") or []:
            if s not in gs:
                errs.append(f"프로필 {code}: 없는 가이드 {s}")
        text = " ".join([str(pr.get("name", "")), str(pr.get("food", ""))] + [str(x) for x in pr.get("steps") or []]
                        + [f'{m.get("who", "")} {m.get("pick", "")}' for m in pr.get("match") or []])
        if not pr.get("match"):
            errs.append(f"프로필 {code}: match(이런 분 → 이런 조건의 제품) 없음")
        for w in banned:
            if w in text:
                errs.append(f"프로필 {code}: 금지 낱말 '{w}'")
    for k, v in (c.get("profile_map") or {}).items():
        if v not in codes:
            errs.append(f"profile_map {k}: 없는 프로필 {v}")
    for k, v in (c.get("guide_profile") or {}).items():
        if k not in gs or v not in codes:
            errs.append(f"guide_profile {k}: 가이드·프로필 확인")
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


def gclean(c: dict, g: dict, items: list[dict]) -> list[dict]:
    """가이드 진열: 공통 금지어 + 그 가이드의 exclude(편에 안 맞는 상품 — 예: 오메가3의 임산부용·SDA·대량 묶음) + match,
    그리고 prefer 낱말이 든 상품을 앞으로(예: rTG·EPA·DHA 고함량). 2026-11-21 운영자 '제품도 신경써서 찾아놓고'."""
    # not_supplement(2026-11-24 운영자 "제품이 그 설명에 정확히 충족하는지 확실히"): 반려동물 간식·요거트·음료처럼 영양제가 아닌 상품은 모든 가이드에서 뺀다
    out = clean(items, (c.get("drop_words") or []) + (c.get("not_supplement") or []) + (g.get("exclude") or []), g.get("match") or [g["name"]])
    pref = [w.lower() for w in g.get("prefer") or []]
    if pref:
        out.sort(key=lambda p: -sum(w in p.get("name", "").lower() for w in pref))
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
    # HEALTH_ONLY="magnesium,vitamin-d": 진열이 빈 성분을 먼저 채울 때(손으로 실행할 때만)
    only = {x.strip() for x in os.environ.get("HEALTH_ONLY", "").split(",") if x.strip()}
    cand = sorted(pairs(c), key=lambda gk: at.get(f"{gk[0]['slug']}|{gk[1]}", ""))
    if only:  # 손 실행은 성분을 번갈아(한 성분에 몰리지 않게): 성분별 n번째 검색어끼리 묶어 차례로
        seen: dict = {}
        cand = sorted(cand, key=lambda gk: (seen.__setitem__(gk[0]["slug"], seen.get(gk[0]["slug"], -1) + 1) or seen[gk[0]["slug"]]))
    for g, k in cand:
        if only and g["slug"] not in only:
            continue
        if g["slug"] in used and not only:  # 손 실행(HEALTH_ONLY)은 빈 성분을 채우려고 같은 성분을 여러 검색어로(2026-11-24: 쿠팡 검색 API가 검색당 1개만 줌)
            continue
        out.append((g, k)); used.add(g["slug"])
        if len(out) >= int(os.environ.get("HEALTH_SEARCHES") or c.get("searches_per_run") or 2):
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
            items = clean(raw, drop + (g.get("exclude") or []), g.get("match") or [g["name"]])
            prods[g["slug"]] = merge(items, prods.get(g["slug"]) or [], today, int(c.get("keep_items") or 24), int(c.get("keep_days") or 14))
            ok += bool(items)
            print(f"{kw}: 받은 {len(raw)} · 관련 {len(items)} · 쌓인 {len(prods[g['slug']])}")
            if raw and not items:  # 관련 0이면 무엇이 왔는지 앞 3개 이름(공개 정보)만 — 2026-11-21 진열이 안 느는 원인 확인용
                print("   받은 예: " + " | ".join(str(p.get("name", ""))[:40] for p in raw[:3]))
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
/* 밝은 화면 고정: 휴대폰 다크 모드에서 크림 상자 위 밝은 글씨가 안 보이던 문제(2026-11-26) */
:root{color-scheme:light}
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
.tgs{display:flex;gap:4px;flex-wrap:wrap}.tg{font-size:11px;padding:1px 6px;border-radius:6px;background:#E8F1FF;color:#1D4ED8}.tg.lo{background:#FFF3B0;color:#7A5B00}.per{font-size:12px;color:var(--muted)}
.stick{display:none}@media(max-width:640px){.stick{display:block;position:fixed;left:12px;right:12px;bottom:12px;z-index:9;text-align:center;padding:12px;border-radius:12px;background:var(--accent);color:#fff;font-weight:700;text-decoration:none;box-shadow:0 6px 18px rgba(0,0,0,.25)}}
.btn.jump{display:inline-block;margin:4px 0 8px}
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
.adbox{margin:22px 0;min-height:1px;text-align:center}
/* ── 건강몰 디자인 v2(운영자 2026-11-24 "페이지 디자인이 조악 — 대형 채널 배워서"): 썸네일 v3·영상 슬라이드와 같은 크림·딥그린·노랑, 엠블럼, 성분 색 아이콘 ── */
:root{--bg:#F6F1E4;--card:#fff;--ink:#0F1B2D;--muted:#5B6878;--line:#E3DCCB;--accent:#0F8A5F;--accent-ink:#fff;--soft:#FFF8DC;--brand:#0F3D2E;--hl:#FFE600}
header{background:var(--brand);border-bottom:0}header .logo{color:#fff;display:flex;align-items:center;gap:8px;font-size:20px}header .logo span{color:var(--hl)}header .tag{color:#cfe3d8}
nav.gn a{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.18);color:#fff}nav.gn a.on{background:var(--hl);color:#111;border-color:var(--hl)}
.hero{position:relative;overflow:hidden;background:var(--brand);color:#fff;border-radius:22px;padding:26px 20px 24px}
.hero .kicker{color:var(--hl)}.hero h1{font-size:28px;line-height:1.3;color:#fff;letter-spacing:-.5px}.hero h1 em{font-style:normal;color:#111;background:linear-gradient(transparent 12%,var(--hl) 12%,var(--hl) 92%,transparent 92%);padding:0 4px}
.hero p{color:#d7e7de}.hero .btn{background:var(--hl);color:#111;box-shadow:4px 4px 0 #000}
.hero>*{position:relative;z-index:1}.hero .pills{position:absolute;z-index:0;right:-36px;bottom:-30px;width:170px;height:170px;opacity:.35;pointer-events:none}
.hero .pills i{position:absolute;width:96px;height:52px;border-radius:26px;background:radial-gradient(28px 14px at 35% 30%,#fff9,#fff0 70%),radial-gradient(circle at 50% 60%,#ffd54a,#e09b00 70%,#9a6200);transform:rotate(-30deg)}
.hero .pills i:nth-child(2){left:70px;top:70px;transform:rotate(20deg);background:radial-gradient(28px 14px at 35% 30%,#fff,#fff0 70%),radial-gradient(circle,#fff,#dfe6ee 75%,#b9c4d0);width:70px;height:70px;border-radius:50%}
.hero .pills i:nth-child(3){left:10px;top:110px;transform:rotate(60deg);background:linear-gradient(90deg,#5EE0A0 50%,#fff 50%)}
.trust{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.trust span{font-size:12px;font-weight:700;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.2)}
@media(min-width:720px){.hero{padding:40px 36px}.hero p{max-width:620px}.hero h1{font-size:38px}.hero .pills{right:30px;top:40px;bottom:auto;width:240px;height:240px;opacity:.95}}
h2{font-weight:900;letter-spacing:-.3px}
.gc{position:relative;padding:44px 14px 14px;border-radius:16px;border:2px solid var(--line);transition:transform .12s,box-shadow .12s}
.gc:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(15,27,45,.10)}
.gc:before{content:"";position:absolute;left:16px;top:16px;width:36px;height:20px;border-radius:10px;background:linear-gradient(90deg,var(--c,#0F8A5F) 50%,#fff 50%);border:2px solid var(--c,#0F8A5F);transform:rotate(-30deg)}
.gc b{font-size:17px;font-weight:900}
.card{border-radius:16px;border:2px solid var(--line);transition:transform .12s,box-shadow .12s}.card:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(15,27,45,.12)}
.pr{font-size:17px;font-weight:900}.tg{font-weight:700}.tg.lo{background:var(--hl);color:#111}
.btn{background:var(--brand);color:var(--hl);box-shadow:3px 3px 0 #000}
.stick{background:var(--brand)!important;color:var(--hl)!important;box-shadow:0 6px 18px rgba(0,0,0,.25)}
.fnl{border:0;background:var(--brand);color:#fff;border-radius:18px;padding:18px 18px 18px 74px;position:relative}
.fnl:before{content:"";position:absolute;left:18px;top:20px;width:42px;height:30px;border-radius:8px;background:#ff0033}
.fnl:after{content:"";position:absolute;left:34px;top:27px;border-left:13px solid #fff;border-top:8px solid transparent;border-bottom:8px solid transparent}
.fnl h3{color:#fff}.fnl p{color:#d7e7de}.fnl .btn{background:var(--hl);color:#111}
table.fn th{background:var(--soft)}h1.t{font-weight:900;letter-spacing:-.5px}
/* 시청자 프로필 상자·자가 점검·정렬(2026-11-24) */
.pf{margin:18px 0;padding:16px 16px 14px;border-radius:18px;background:#FFF8D6;border:2px solid #111;box-shadow:4px 4px 0 #111}
.pf .pk{margin:0;font-size:13px;font-weight:800;color:var(--brand)}.pf h2{margin:2px 0 8px;font-size:20px;border:0;padding:0}
.pf ol{margin:0 0 10px;padding-left:22px}.pf ol li{margin:4px 0;line-height:1.5}
.pq{background:#fff;border-radius:12px;padding:12px;margin:10px 0}.pq p{margin:8px 0 6px;font-weight:700;font-size:15px}
.pq button,.sortbar button{font:inherit;font-size:14px;padding:7px 12px;margin:0 6px 6px 0;border-radius:999px;border:1.5px solid #111;background:#fff;cursor:pointer}
.pq button.on,.sortbar button.on{background:var(--brand);color:var(--hl)}.pq .res{display:none;margin-top:8px;padding:10px;border-radius:10px;background:var(--soft);font-size:14px;line-height:1.55}
.pq .res.on{display:block}.pn{margin:8px 0 0;font-size:14px}.pn a{display:inline-block;margin:4px 6px 0 0;padding:5px 12px;border-radius:999px;background:var(--brand);color:#fff;text-decoration:none}
.pn a.cur{background:#fff;color:#111;border:1px solid #111}
/* 논문 정리(2026-11-26) */
.rbox{display:grid;grid-template-columns:1fr auto;gap:2px 10px;align-items:center;margin:16px 0;padding:14px 16px;border-radius:16px;background:var(--brand);color:#fff;text-decoration:none;box-shadow:4px 4px 0 #111}
.rbox .rk{grid-column:1;font-size:12px;font-weight:800;color:var(--hl)}.rbox b{grid-column:1;font-size:17px}.rbox .rn{grid-column:1;font-size:13px;color:#d7e7de}
.rbox .rg{grid-column:2;grid-row:1/4;font-weight:900;color:#111;background:var(--hl);border-radius:999px;padding:8px 14px;white-space:nowrap}
.rbox.go{background:#fff;color:var(--ink);border:2px solid #111}.rbox.go .rk{color:var(--accent)}
.rnote{font-size:13px;color:var(--muted);background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.rtoc{background:#fff;border:2px solid var(--line);border-radius:14px;padding:12px 16px;margin:14px 0}.rtoc ol{margin:6px 0 0;padding-left:20px}.rtoc li{margin:4px 0}.rtoc a{text-decoration:none;color:var(--accent);font-weight:700}
.re{background:#fff;border:2px solid var(--line);border-radius:18px;padding:16px;margin:16px 0;scroll-margin-top:110px}
.re h2{margin:4px 0 10px;font-size:20px}.ra{margin:0;font-size:12px;color:var(--muted)}.ra span{display:inline-block;margin-right:8px;padding:2px 8px;border-radius:999px;background:var(--hl);color:#111;font-weight:800}
.rans{margin:0 0 8px;line-height:1.65}.rans b,.rkey b{display:inline-block;margin-right:6px;padding:1px 8px;border-radius:6px;background:var(--brand);color:var(--hl);font-size:12px}
.rkey{margin:0 0 10px;font-size:14px;color:var(--muted)}
.rvs{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.rv{display:block;width:180px;text-decoration:none;font-size:13px;font-weight:700}.rv img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;display:block;background:#ddd}.rv.sh{width:110px}.rv.sh img{aspect-ratio:9/16}
.rp summary{cursor:pointer;font-weight:800;color:var(--accent);padding:6px 0}.tw{overflow-x:auto}.rp table{font-size:13px;min-width:560px}.rp a{color:var(--accent)}
.ri{background:#fff;border:2px solid var(--line);border-radius:16px;padding:6px 16px 12px;margin:12px 0}.ri h2 a{text-decoration:none}.ri ul{margin:0;padding-left:20px}.ri li{margin:5px 0}.ri li a{color:var(--ink)}.pnext{margin:18px 0;padding:14px 16px;border-radius:14px;background:var(--soft);font-weight:700}
.pnext a{color:var(--brand)}table.pm{width:100%;border-collapse:collapse;margin:6px 0 4px;background:#fff;border-radius:12px;overflow:hidden;font-size:14px}
table.pm th{background:var(--brand);color:var(--hl);text-align:left;padding:8px 10px}table.pm td{padding:8px 10px;border-top:1px solid #eee;vertical-align:top}table.pm td:first-child{width:40%}table.pm td:last-child{font-weight:700}.sortbar{margin:4px 0 10px}.card.hide{display:none}
/* ── 건강몰 디자인 v4 '뒷면 표기'(2026-11-27 운영자 "새 단장" + Anthropic frontend-design 점검):
   v3(크림·명조·테라코타)는 AI 생성 화면의 대표 패턴이라 폐기. 이 몰의 주제 = 영양제 뒷면 '영양·기능정보' 표 →
   흰 종이·검정 굵은 괘선·숫자 중심 표기·한 가지 포인트색(식약처 인증 느낌의 진녹색)만. 한 서체(Pretendard/시스템 고딕)로 굵기 대비.
   카드 둥글림·부드러운 그림자·호버 들썩임·제목 한 단어 색칠 걷어냄. 기억할 한 요소 = 첫 화면의 '표기 상자'. ── */
:root{--bg:#FFFFFF;--card:#FFFFFF;--ink:#141414;--muted:#55575A;--line:#141414;--accent:#00704A;--accent-ink:#fff;--soft:#F2F4F1;--brand:#141414;--hl:#00704A}
body{background:var(--bg);font-family:"Pretendard",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;font-feature-settings:"tnum"}
h1,h2,h3{font-family:inherit;font-weight:900;letter-spacing:-.6px}
header{background:#fff;border-bottom:3px solid var(--ink)}header .logo{color:var(--ink)}header .logo span{color:var(--ink)}header .tag{color:var(--muted)}
nav.gn a{background:#fff;border:1px solid var(--ink);border-radius:2px;color:var(--ink)}nav.gn a.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.disc{border-bottom:1px solid #d9d9d9}
.hero{background:#fff;color:var(--ink);border:3px solid var(--ink);border-radius:0;box-shadow:none;padding:0}
.hero>*{padding-left:18px;padding-right:18px}.hero .kicker{margin:0;padding-top:10px;padding-bottom:8px;border-bottom:8px solid var(--ink);color:var(--ink);font-size:13px;letter-spacing:0}
.hero h1{color:var(--ink);font-size:30px;line-height:1.25;padding-top:14px;padding-bottom:10px;border-bottom:1px solid var(--ink);margin:0}.hero h1 em{color:inherit;background:none;padding:0}
.hero p{color:var(--ink);padding-top:10px;padding-bottom:12px;border-bottom:4px solid var(--ink);margin:0}
.hero .btn{margin:14px 18px 6px;background:var(--accent);color:#fff;box-shadow:none;border-radius:4px}
.hero .trust{margin:0;padding-top:6px;padding-bottom:14px}.trust span{background:#fff;color:var(--ink);border:1px solid var(--ink);border-radius:2px;font-weight:700}
.hero .pills{display:none}
@media(min-width:720px){.hero h1{font-size:44px}.hero{padding:0}.hero p{max-width:none}}
.kicker{color:var(--accent)}
.gc{background:#fff;border:0;border-top:6px solid var(--ink);border-radius:0;box-shadow:none;padding:12px 2px 14px;transition:none}
.gc:hover,.card:hover{transform:none;box-shadow:none}.gc:hover b{color:var(--accent)}
.gc:before{display:none}.gc b{font-size:18px;font-weight:900;color:var(--ink)}.gc small{color:var(--muted)}
.gl{gap:14px 16px}
.card{background:#fff;border:1px solid var(--ink);border-radius:0}.card .im{border-bottom:1px solid var(--ink)}
.pr{color:var(--ink)}.tg{background:#fff;color:var(--ink);border:1px solid var(--ink);border-radius:2px}.tg.lo{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn{background:var(--accent);color:#fff;box-shadow:none;border-radius:4px}
.stick{background:var(--accent)!important;color:#fff!important;border-radius:6px!important}
.fnl{background:#fff;color:var(--ink);border:3px solid var(--ink);border-radius:0;padding:16px 16px 16px 16px}.fnl:before,.fnl:after{display:none}.fnl h3{color:var(--ink)}.fnl p{color:var(--muted)}.fnl .btn{background:var(--accent);color:#fff}
.box,.rnote,.rtoc,.re,.ri,.pq{background:#fff;border:1px solid var(--ink);border-radius:0}
table.fn{border:3px solid var(--ink);border-radius:0}table.fn th{background:#fff;color:var(--ink);border-bottom:4px solid var(--ink)}table.fn td{border-bottom:1px solid var(--ink)}
.pf{background:#fff;border:3px solid var(--ink);border-radius:0;box-shadow:none}.pf .pk{color:var(--accent)}
.pq button,.sortbar button{border:1px solid var(--ink);border-radius:2px;background:#fff}.pq button.on,.sortbar button.on{background:var(--ink);color:#fff}
.pq .res{background:var(--soft);border-radius:0}.pn a{background:var(--ink);border-radius:2px}.pn a.cur{background:#fff;color:var(--ink);border:1px solid var(--ink)}
.rbox{background:#fff;color:var(--ink);border:3px solid var(--ink);border-radius:0;box-shadow:none}.rbox .rk{color:var(--accent)}.rbox .rn{color:var(--muted)}.rbox .rg{background:var(--accent);color:#fff;border-radius:4px}
.rbox.go{border-width:1px}.rans b,.rkey b{background:var(--ink);color:#fff;border-radius:2px}.ra span{background:#fff;color:var(--ink);border:1px solid var(--ink);border-radius:2px}
table.pm{border:2px solid var(--ink);border-radius:0}table.pm th{background:var(--ink);color:#fff}
h2.sec{border-top:3px solid var(--ink)}footer{border-top:3px solid var(--ink)}
a:focus-visible,button:focus-visible{outline:3px solid var(--accent);outline-offset:2px}

"""

EMBLEM = '''<svg width="{px}" height="{px}" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><circle cx="100" cy="100" r="96" fill="#141414"/><g transform="rotate(-35 86 88)"><rect x="52" y="70" width="68" height="36" rx="18" fill="#FFFFFF"/><rect x="86" y="70" width="34" height="36" rx="18" fill="#00704A"/><rect x="86" y="70" width="14" height="36" fill="#00704A"/></g><circle cx="86" cy="88" r="46" fill="none" stroke="#00704A" stroke-width="12"/><line x1="120" y1="122" x2="152" y2="154" stroke="#00704A" stroke-width="16" stroke-linecap="round"/></svg>'''
GCOL = {"omega3": "#0b5cad", "lutein": "#e85d04", "milk-thistle": "#6d28d9", "coq10": "#c1121f", "saw-palmetto": "#4d7c0f", "red-ginseng": "#7f1d1d", "probiotics": "#0096c7", "magnesium": "#3d4f8f", "vitamin-d": "#ff9f0a", "vitamin-c": "#ff7a00"}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


UNIT = re.compile(r'(\d{2,4})\s*(캡슐|소프트젤|정|포|알|스틱|개입|T|tab)', re.I)


def unit_price(p: dict) -> int | None:
    """상품명에 적힌 개수(예: '180캡슐', '60정, 1개')로 1알(1포)당 값 — 참고값. 묶음(곽·박스·세트·N개)이 섞여 개수가 애매하면 None
    (틀린 값을 보이느니 안 보인다, 2026-11-22 판매 강화)"""
    n = p.get("name", ""); m = UNIT.findall(n)
    if len(m) != 1 or not p.get("price"):
        return None
    if re.search(r'곽|박스|세트|개월|[x×]\s*\d', n) or any(int(k) > 1 for k in re.findall(r'(\d+)\s*개(?!입|월)', n)):
        return None
    cnt = int(m[0][0])
    return round(p["price"] / cnt) if cnt >= 10 else None


def card(p: dict, low: bool = False) -> str:
    price = f'<div class="pr">{p["price"]:,}원</div>' if p.get("price") else ""
    u = unit_price(p)
    per = f'<div class="per">1{"포" if "포" in p.get("name", "") or "스틱" in p.get("name", "") else "알"}당 약 {u:,}원</div>' if u else ""
    tags = ("".join([('<span class="tg">로켓배송</span>' if p.get("rocket") else ""), ('<span class="tg lo">1알당 가장 낮음</span>' if low else "")]))
    img = f'<img src="{esc(p["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if p.get("image") else ""
    return (f'<a class="card" data-per="{u or 0}" data-rk="{1 if p.get("rocket") else 0}" href="{esc(p["url"])}" rel="sponsored nofollow noopener" target="_blank">'
            f'<div class="im">{img}</div><div class="b">{("<div class=tgs>" + tags + "</div>") if tags else ""}<div class="n">{esc(p["name"])}</div>{price}{per}<div class="go">쿠팡에서 보기 ›</div></div></a>')


def cards(items: list[dict]) -> str:
    us = [(unit_price(p), i) for i, p in enumerate(items)]
    ok = [x for x in us if x[0]]
    low = min(ok)[1] if len(ok) >= 3 else -1
    return "".join(card(p, i == low) for i, p in enumerate(items))


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
    if cat.get("has_research"):
        nav.append(f'<a href="{up}research/" class="{"on" if on == "research" else ""}">논문 정리</a>')
    nav += [f'<a href="{up}guide/{g["slug"]}/" class="{"on" if on == g["slug"] else ""}">{esc(g["name"])}</a>' for g in c.get("guides") or []]
    if cat.get("best_shown"):
        nav.append(f'<a href="{up}best/" class="{"on" if on == "best" else ""}">건강식품 베스트</a>')
    v = c.get("verification") or {}
    meta = "".join(f'<meta name="{n}" content="{esc(v[k])}">' for k, n in (("google", "google-site-verification"), ("naver", "naver-site-verification"), ("bing", "msvalidate.01")) if v.get(k))
    ad = c.get("adsense") or {}
    adsense_head = (f'<meta name="google-adsense-account" content="{esc(ad["client"])}"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={esc(ad["client"])}" crossorigin="anonymous"></script>'
                    if ad.get("client") and not noindex else "")
    robots = '<meta name="robots" content="noindex,follow">' if noindex else '<meta name="robots" content="index,follow,max-image-preview:large">'
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in (ld or []))
    upd = esc(cat.get("updated") or "")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">{robots}<link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{esc(c['name'])}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canon)}"><meta property="og:locale" content="ko_KR">
<meta name="color-scheme" content="light only"><meta name="theme-color" content="#FFFFFF">{meta}
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23141414'/%3E%3Ctext x='32' y='44' font-size='32' text-anchor='middle' font-family='sans-serif' font-weight='800' fill='%23fff'%3E건%3C/text%3E%3C/svg%3E">
<style>{CSS}</style>{lds}{adsense_head}</head><body>
<header><div class="wrap"><div class="top"><a class="logo" href="{up}">{EMBLEM.format(px=30)}김박사 <span>건강몰</span></a><span class="tag">{esc(c['tagline'])}</span></div>
<nav class="gn" aria-label="메뉴">{''.join(nav)}</nav></div></header>
<main class="wrap"><p class="disc">{esc(DISCLOSURE)}</p>
{body}</main>
<footer><div class="wrap"><p>{esc(DISCLOSURE)} 성분 가이드는 식약처가 인정한 기능성 문구와 공개된 섭취 시 주의사항을 옮겨 정리한 일반 정보이며, 의학적 진단·상담을 대신하지 않습니다. 질환이 있거나 의약품을 복용 중이라면 의사·약사와 먼저 상담하세요.
상품 목록은 쿠팡 검색·베스트 결과를 자동으로 가져온 것으로 추천·보증이 아니며, 건강기능식품 여부·함량·가격은 쿠팡 상품 페이지의 표시사항이 기준입니다{f" · 상품 갱신 {upd}(한국 시각)" if upd else ""}.</p>
<p><a href="{SITE}">김박사 월드</a> · <a href="{MALL}">김박사 몰(장보기)</a> · <a href="{YT}">유튜브 김박사 건강월드</a> · <a href="{up}about/">김박사 건강몰 소개</a></p></div></footer>{mall_track.snippet("health", [x["code"] for x in c.get("profiles") or []], c.get("profile_map") or {})}{PF_JS}</body></html>"""


def ad_slot(c: dict) -> str:
    """애드센스 인아티클 한 개(번호가 있을 때) → 없으면 애드핏 단위(번호가 있을 때) → 없으면 빈칸. 쿠팡 상품 줄과 붙지 않는 자리(주의사항 뒤)."""
    ad = c.get("adsense") or {}
    if ad.get("client") and ad.get("slot_in_article"):
        return (f'<div class="adbox"><ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" '
                f'data-ad-client="{esc(ad["client"])}" data-ad-slot="{esc(ad["slot_in_article"])}"></ins><script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>')
    if c.get("adfit_unit"):
        return (f'<div class="adbox"><ins class="kakao_ad_area" style="display:none;" data-ad-unit="{esc(c["adfit_unit"])}" data-ad-width="320" data-ad-height="100"></ins>'
                '<script async src="//t1.daumcdn.net/kas/static/ba.min.js"></script></div>')
    return ""


def gname(c: dict, slug: str) -> str:
    return next((g["name"] for g in c.get("guides") or [] if g["slug"] == slug), slug)


def profile_box(c: dict, g: dict) -> str:
    """시청자 프로필 상자(운영자 2026-11-24). 이 가이드를 쓰는 프로필마다 하나씩 만들고, 화면이 <html data-pf> 에 맞는 것만 보인다
    (영상 프로필이 없으면 성분 기본 프로필). 확인 순서 3단계 → 1분 자가 점검(약·음식·고르는 기준 → 정렬·거르기) → 같은 관심의 다음 가이드.
    상품 링크와 떨어진 위쪽 자리, 질병 효능 문장 없음(banned 검사)."""
    dflt = (c.get("guide_profile") or {}).get(g["slug"])
    out = []
    for pr in c.get("profiles") or []:
        if g["slug"] not in pr.get("guides", []) and pr["code"] != dflt:
            continue
        code = pr["code"]
        steps = "".join(f"<li>{esc(x)}</li>" for x in pr.get("steps") or [])
        nxt = "".join(f'<a class="{"cur" if s == g["slug"] else ""}" href="../{s}/" onclick="hmEv&&hmEv(\'pf-next\')">{esc(gname(c, s))}</a>' for s in pr.get("guides") or [])
        q = (f'<div class="pq" data-food="{esc(pr.get("food", "음식"))}"><p>1분 자가 점검 ① 지금 드시는 약이 있나요?</p><button data-q="1" data-a="y">예</button><button data-q="1" data-a="n">아니요</button>'
             f'<p>② {esc(pr.get("food", "음식"))}을(를) 자주 드시나요?</p><button data-q="2" data-a="y">예</button><button data-q="2" data-a="n">아니요</button>'
             '<p>③ 고를 때 가장 중요한 것은?</p><button data-q="3" data-a="dose">기준에 맞는 함량</button><button data-q="3" data-a="unit">1알당 값</button><button data-q="3" data-a="fast">빠른 배송</button>'
             '<div class="res"></div></div>')
        attr = ' data-def="1"' if code == dflt else " hidden"
        # 수요-공급 연결(운영자 2026-11-24 "어떤 조건·상황의 사람에게 어떤 조건·특성의 제품이 연결되는지"): 이런 분 → 고를 조건
        others = [o["name"] for o in c.get("guides") or [] if o["slug"] != g["slug"]]
        mine = lambda m: g["name"] in m["who"] + m["pick"] or not any(n in m["who"] + m["pick"] for n in others)  # 다른 성분만 말하는 줄은 그 가이드로(2026-11-26)
        mrows = "".join(f'<tr><td>{esc(m["who"])}</td><td>{esc(m["pick"])}</td></tr>' for m in pr.get("match") or [] if mine(m))
        mt = (f'<table class="pm"><thead><tr><th>이런 분이라면</th><th>이런 조건의 제품</th></tr></thead><tbody>{mrows}</tbody></table>') if mrows else ""
        out.append(f'<section class="pf" data-pf="{code}"{attr}><p class="pk" data-n="{esc(pr["name"])}">{esc(pr["name"])}에 관심 있다면</p>'
                   f'<h2>이 순서로 확인하세요</h2><ol>{steps}</ol>{mt}{q}<nav class="pn">같은 관심의 가이드 {nxt}</nav></section>')
    return "".join(out)


def profile_next(c: dict, g: dict) -> str:
    """진열 아래 '같은 관심의 다음 가이드' 한 줄(체류 늘리기). 프로필마다 하나, 화면이 맞는 것만 보인다."""
    dflt = (c.get("guide_profile") or {}).get(g["slug"])
    out = []
    for pr in c.get("profiles") or []:
        gs = pr.get("guides") or []
        if g["slug"] not in gs and pr["code"] != dflt:
            continue
        rest = [s for s in gs if s != g["slug"]]
        if not rest:
            continue
        i = (gs.index(g["slug"]) + 1) % len(gs) if g["slug"] in gs else 0
        nx = gs[i] if gs[i] != g["slug"] else rest[0]
        attr = ' data-def="1"' if pr["code"] == dflt else " hidden"
        out.append(f'<p class="pnext" data-pf="{pr["code"]}"{attr}>{esc(pr["name"])}, 다음으로 볼 것: '
                   f'<a href="../{nx}/" onclick="hmEv&&hmEv(\'pf-next2\')">{esc(gname(c, nx))} 고르는 법 ›</a></p>')
    return "".join(out)


PF_JS = r"""<script>(function(){try{var pf=document.documentElement.getAttribute('data-pf')||'-',E=window.hmEv||function(){};
var bx=document.querySelectorAll('[data-pf]:not(html)'),has=0;bx.forEach(function(b){if(b.getAttribute('data-pf')===pf)has=1});
if(has)bx.forEach(function(b){b.hidden=b.getAttribute('data-pf')!==pf;if(!b.hidden&&b.classList.contains('pf')){var k=b.querySelector('.pk');if(k)k.textContent='영상에서 오셨네요 · '+k.getAttribute('data-n')}});
var grid=document.querySelector('#items ~ .grid'),cards=grid?[].slice.call(grid.children):[];
function sortBy(m){if(!grid)return;cards.forEach(function(c){c.classList.toggle('hide',m==='fast'&&c.getAttribute('data-rk')!=='1')});
var l=cards.slice();if(m==='unit')l.sort(function(a,b){var x=+a.getAttribute('data-per')||1e9,y=+b.getAttribute('data-per')||1e9;return x-y});
l.forEach(function(c){grid.appendChild(c)});document.querySelectorAll('.sortbar button').forEach(function(b){b.classList.toggle('on',b.getAttribute('data-m')===m)})}
document.querySelectorAll('.sortbar button').forEach(function(b){b.addEventListener('click',function(){var m=b.getAttribute('data-m');sortBy(m);E('sort-'+m)})});
document.querySelectorAll('.pq').forEach(function(q){var A={},r=q.querySelector('.res'),food=q.getAttribute('data-food');
q.querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){var n=b.getAttribute('data-q'),a=b.getAttribute('data-a');A[n]=a;
q.querySelectorAll('button[data-q="'+n+'"]').forEach(function(x){x.classList.toggle('on',x===b)});E('q'+n+'-'+a);
var t=[];if(A[1]==='y')t.push('드시는 약이 있다면 <a href="#cautions">섭취 시 주의사항</a>을 먼저 보고 의사·약사와 상담하세요.');
if(A[2]==='y')t.push(food+'(으)로 들어오는 양이 있으니, 함께 생각해 1일 섭취량 기준 범위 안에서 고르세요.');if(A[2]==='n')t.push('음식으로 들어오는 양이 적다면, 먼저 식단을 늘려 보고 보충은 1일 섭취량 기준 범위 안인지 확인하세요.');
if(A[3]){sortBy(A[3]==='dose'?'base':A[3]);t.push(A[3]==='dose'?'<a href="#fn">식약처 기준 표</a>의 1일 섭취량과 상품 표시사항의 함량을 비교하세요.':A[3]==='unit'?'아래 제품을 1알당 값이 낮은 순으로 바꿔 두었습니다.':'아래 제품을 로켓배송만 남겨 두었습니다.');
t.push('<a class="btn" href="#items">제품 비교 보기 ↓</a>')}
if(A[1]&&A[2]&&A[3]&&!q.dataset.done){q.dataset.done=1;E('quiz-done')}r.innerHTML=t.join('<br>');r.classList.toggle('on',t.length>0)})})});
}catch(e){}})();</script>"""


def guide_body(c: dict, cat: dict, g: dict, res: dict | None = None) -> tuple[str, str]:
    others = '<h2>다른 성분 가이드</h2><nav class="chips">' + "".join(
        f'<a href="../{o["slug"]}/">{esc(o["name"])}</a>' for o in c.get("guides") or [] if o["slug"] != g["slug"]) + "</nav>"
    rows = "".join(f"<tr><td>{esc(f['text'])}</td><td>{esc(f['dose'])}</td></tr>" for f in g["functions"])
    items = gclean(c, g, (cat.get("products") or {}).get(g["slug"]) or [])
    prods = (f'<h2 id="items">쿠팡 검색 결과: {esc(g["keyword"])}<span class="ad">광고</span></h2>'
             f'<p class="note">쿠팡 검색 결과를 자동으로 보여 줍니다. 추천·보증이 아니며, 건강기능식품 여부·기능성·함량은 상품 페이지의 표시사항에서 위 기준과 비교해 확인하세요.</p>'
             f'<p class="note">1알(1포)당 값은 상품명에 적힌 개수로 나눈 참고값입니다. 하루 몇 알인지는 제품마다 다르니 표시사항을 확인하세요.</p>'
             '<div class="sortbar"><button data-m="base" class="on">기본 순</button><button data-m="unit">1알당 값 낮은 순</button><button data-m="fast">로켓배송만</button></div>'
             f'<div class="grid" data-sub="g-{g["slug"]}">{cards(items[:20])}</div>') if items else '<p class="empty">상품 목록을 준비하고 있습니다.</p>'
    body = f"""<p class="crumb"><a href="../../">홈</a> › <a href="../">성분 가이드</a> › {esc(g['name'])}</p>
<h1 class="t">{esc(g['name'])} 고르는 법: 식약처 기능성·하루 섭취량·주의사항</h1>
<p><a class="btn jump" href="#items">기준과 제품 비교 바로 보기 ↓</a></p>
<p class="lead">{esc(g['intro'])}</p>
{research_box(c, g, (res or {}).get(g["slug"]) or [])}
{profile_box(c, g)}
<h2 id="fn">식약처가 인정한 기능성 <small>{esc(g['aka'])}</small></h2>
<table class="fn"><thead><tr><th>기능성 내용(인정 문구)</th><th>1일 섭취량 기준</th></tr></thead><tbody>{rows}</tbody></table>
<p class="note">기능성 문구는 그 기능성 원료를 기준 섭취량만큼 넣어 인정받은 '건강기능식품'에만 표시할 수 있습니다. 같은 성분 이름이어도 일반식품에는 이 기능성이 없습니다.</p>
<h2 id="cautions">섭취 시 주의사항</h2><div class="box"><ul class="ck">{"".join(f"<li>{esc(x)}</li>" for x in g['cautions'])}</ul></div>
{ad_slot(c)}
<h2>고를 때 확인할 것</h2><ul class="ck">{"".join(f"<li>{esc(x)}</li>" for x in g['choose'])}</ul>
{funnel(c, "guide-" + g["slug"], "guide")}
{prods}
{profile_next(c, g)}
{others}
<a class="stick" href="#items">제품 비교 보기</a>
<h2>출처</h2><ul class="src">{"".join(f'<li><a href="{esc(s["url"])}" rel="nofollow noopener" target="_blank">{esc(s["title"])}</a></li>' for s in g['sources'])}</ul>
<p class="note">내용 확인일 {esc(g['verified'])}. 기준은 바뀔 수 있으니 제품 표시사항과 식품안전나라에서 함께 확인하세요.</p>"""
    desc = f"{g['name']}({g['aka']}) 식약처 인정 기능성 문구, 1일 섭취량 기준, 섭취 시 주의사항과 고를 때 확인할 것을 한 페이지에 정리했습니다."
    return body, desc


# ---------- 논문 정리(2026-11-26 운영자 "제품 별로 그동안 쌓인 리서치들이 잘 연결되서 고객에게 백분 도움 되는 구조") ----------
# 질병 결과는 '그 연구에서 이렇게 나왔다'로만, 상품 진열·쿠팡 링크가 없는 별도 페이지(/research/)에 둔다.
# 가이드에서는 중립 문구 상자 하나로만 연결한다(질병 문장을 상품 옆에 두지 않음, HEALTH_CHANNEL 2장).
RES_FIX = (("결핍 치료에", "결핍 보충에"), ("가짜약보다", "가짜약과 비교해"))


def rfix(t: str) -> str:
    for a, b in RES_FIX:
        t = t.replace(a, b)
    return t


def load_research(path: Path = RES, today: str | None = None) -> dict:
    """{성분: [편…]} — 공개일이 지난 편만, 최신 순. 편마다 papers(그 편 논문 카드) 붙임."""
    if not path.exists():
        return {}
    r = json.loads(path.read_text(encoding="utf-8"))
    today = today or dt.datetime.now(KST).date().isoformat()
    pp = {}
    for x in r.get("papers") or []:
        for e in x.get("episodes") or []:
            pp.setdefault(e, []).append(x)
    out: dict = {}
    for e in r.get("episodes") or []:
        if (e.get("date") or "9999") > today:
            continue
        out.setdefault(e["ingredient"], []).append({**e, "papers": pp.get(e["slug"], [])})
    for v in out.values():
        v.sort(key=lambda e: e["date"], reverse=True)
    return out


def research_box(c: dict, g: dict, eps: list) -> str:
    """가이드 위쪽 상자: 질문 수·논문 수·영상 수 + 연구 정리 링크(질병 문장 없이)."""
    if not eps:
        return ""
    n_p = len({x["study"] for e in eps for x in e["papers"]})
    n_v = sum(bool(e["long"]) + bool(e["short"]) for e in eps)
    return (f'<a class="rbox" href="../../research/{g["slug"]}/" onclick="hmEv&&hmEv(\'research-box\')"><span class="rk">논문으로 따져 봤습니다</span>'
            f'<b>{esc(g["name"])} 연구 정리</b><span class="rn">질문 {len(eps)}개 · 논문 {n_p}편 · 영상 {n_v}편</span><span class="rg">보기 ›</span></a>')


def ep_html(e: dict) -> str:
    vids = []
    if e["long"]:
        vids.append(f'<a class="rv" href="https://youtu.be/{esc(e["long"])}" target="_blank" rel="noopener" onclick="hmEv&&hmEv(\'research-yt\')"><img loading="lazy" src="https://i.ytimg.com/vi/{esc(e["long"])}/mqdefault.jpg" alt=""><span>영상(롱폼)</span></a>')
    if e["short"]:
        vids.append(f'<a class="rv sh" href="https://youtube.com/shorts/{esc(e["short"])}" target="_blank" rel="noopener" onclick="hmEv&&hmEv(\'research-yt\')"><img loading="lazy" src="https://i.ytimg.com/vi/{esc(e["short"])}/mqdefault.jpg" alt=""><span>쇼츠 1분</span></a>')
    rows = "".join(
        f'<tr><td>{(f"<a href={chr(34)}https://pubmed.ncbi.nlm.nih.gov/{esc(x[chr(112)+chr(109)+chr(105)+chr(100)])}/{chr(34)} target=_blank rel={chr(34)}nofollow noopener{chr(34)}>" + esc(x["study"]) + "</a>") if x["pmid"] else esc(x["study"])}</td>'
        f'<td>{esc(rfix(x["population"]))}</td><td>{"<br>".join(esc(rfix(t)) for t in x["results"])}</td></tr>' for x in e["papers"])
    tbl = (f'<details class="rp"><summary>근거 논문 {len(e["papers"])}편 보기</summary><div class="tw"><table class="fn"><thead><tr><th>연구</th><th>대상</th><th>결과</th></tr></thead><tbody>{rows}</tbody></table></div></details>') if rows else ""
    return (f'<article class="re" id="{esc(e["slug"])}"><p class="ra"><span>{esc(e["angle"].split("(")[0].split("·")[0])}</span>{esc(e["date"])}</p>'
            f'<h2>{esc(rfix(e["question"]))}</h2><p class="rans"><b>정리</b> {esc(rfix(e["answer"]))}</p>'
            f'<p class="rkey"><b>핵심 숫자</b> {esc(rfix(e["key"]))}</p>{"<div class=rvs>" + "".join(vids) + "</div>" if vids else ""}{tbl}</article>')


RES_NOTE = ("연구 결과를 정리한 일반 정보입니다. 특정 제품의 효능·효과를 뜻하지 않으며, 진단과 진료를 대신하지 않습니다. "
            "숫자는 PubMed 초록에서 확인한 값이고, 관찰 연구·하위 분석은 그렇게 적었습니다. 드시는 약이 있거나 수치·증상이 있다면 의사·약사와 먼저 상담하세요.")


def research_pages(c: dict, cat: dict, res: dict, base: str, org: dict, w, lastmod: dict) -> None:
    guides = [g for g in c.get("guides") or [] if res.get(g["slug"])]
    if not guides:
        return
    idx = []
    for g in guides:
        eps = res[g["slug"]]
        qs = "".join(f'<li><a href="{g["slug"]}/#{esc(e["slug"])}">{esc(rfix(e["question"]))}</a></li>' for e in eps)
        idx.append(f'<section class="ri"><h2><a href="{g["slug"]}/">{esc(g["name"])}</a><small>질문 {len(eps)}개</small></h2><ul>{qs}</ul></section>')
    w("research/index.html", page(c, cat, f"영양제 논문 정리 — 성분별로 따져 본 질문 | {c['name']}",
                                 f'<p class="crumb"><a href="../">홈</a> › 논문 정리</p><h1 class="t">영양제, 논문으로 따져 봤습니다</h1>'
                                 f'<p class="lead">김박사 건강월드 영상마다 확인한 대형 임상·메타분석을 성분별로 모았습니다. 질문을 누르면 결론·핵심 숫자·근거 논문·영상을 한 번에 볼 수 있어요.</p>'
                                 f'<p class="rnote">{esc(RES_NOTE)}</p>' + "".join(idx),
                                 "research/", "오메가3·비타민D·루테인·밀크씨슬 등 영양제마다 대형 임상·메타분석이 어떤 결론을 냈는지 성분별로 정리했습니다.", "research"))
    lastmod["research/"] = max(e["date"] for v in res.values() for e in v)
    for g in guides:
        eps = res[g["slug"]]
        pth = f"research/{g['slug']}/"
        toc = "".join(f'<li><a href="#{esc(e["slug"])}">{esc(rfix(e["question"]))}</a></li>' for e in eps)
        body = (f'<p class="crumb"><a href="../../">홈</a> › <a href="../">논문 정리</a> › {esc(g["name"])}</p>'
                f'<h1 class="t">{esc(g["name"])}, 논문으로 따져 본 질문 {len(eps)}개</h1>'
                f'<p class="rnote">{esc(RES_NOTE)}</p><nav class="rtoc"><b>이 페이지의 질문</b><ol>{toc}</ol></nav>'
                + "".join(ep_html(e) for e in eps)
                + f'<a class="rbox go" href="../../guide/{g["slug"]}/" onclick="hmEv&&hmEv(\'research-guide\')"><span class="rk">고를 때</span><b>{esc(g["name"])} 식약처 인정 기능성·하루 섭취량·주의사항</b><span class="rg">가이드 보기 ›</span></a>'
                + '<h2>다른 성분 논문 정리</h2><nav class="chips">' + "".join(f'<a href="../{o["slug"]}/">{esc(o["name"])}</a>' for o in guides if o["slug"] != g["slug"]) + "</nav>")
        desc = f"{g['name']}: " + " · ".join(rfix(e["question"]) for e in eps[:4])
        ld = [{"@context": "https://schema.org", "@type": "Article", "headline": f"{g['name']}, 논문으로 따져 본 질문 {len(eps)}개", "description": desc[:300],
               "inLanguage": "ko-KR", "dateModified": eps[0]["date"], "author": org, "publisher": org, "mainEntityOfPage": base + "/" + pth}]
        w(pth + "index.html", page(c, cat, f"{g['name']} 논문 정리 — {eps[0]['question'][:40]} | {c['name']}", body, pth, desc[:160], "research", ld=ld))
        lastmod[pth] = eps[0]["date"]


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
    res = load_research(today=today)
    cat = {**cat, "has_research": bool(res)}
    org = {"@type": "Organization", "name": "김박사 월드", "url": "https://drkimworld.com/"}
    gl = '<div class="gl">' + "".join(
        f'<a class="gc" style="--c:{GCOL.get(g["slug"], "#0F8A5F")}" href="{{up}}guide/{g["slug"]}/"><b>{esc(g["name"])}</b><small>{esc(g["aka"])}</small><p>{esc(g["functions"][0]["text"])}</p></a>' for g in guides) + "</div>"
    # 홈
    best = clean(cat.get("best") or [], c.get("drop_words") or [], [m for g in guides for m in g.get("match") or []])
    cat = {**cat, "best_shown": bool(best)}
    prods = cat.get("products") or {}
    chips = '<nav class="chips" aria-label="성분">' + "".join(f'<a href="#{g["slug"]}">{esc(g["name"])}</a>' for g in guides if prods.get(g["slug"])) + "</nav>"
    home = ['<section class="hero"><div class="pills" aria-hidden="true"><i></i><i></i><i></i></div><p class="kicker">김박사 건강몰</p><h1>영양제, 사기 전에<br><em>확인할 것만</em> 모았습니다</h1>'
            '<p>성분마다 식약처가 인정한 기능성 문구, 하루 섭취량 기준, 섭취 시 주의사항을 먼저 정리했습니다. 확인한 다음 쿠팡에서 비교해 보세요.</p>'
            '<a class="btn" href="guide/">성분 가이드 보기</a><div class="trust"><span>식약처 인정 문구 그대로</span><span>PubMed 논문 근거</span><span>1알당 값 비교</span></div></section>',
            '<h2>성분 가이드<small>기능성·섭취량·주의사항</small></h2>' + gl.replace("{up}", ""), funnel(c, "home")]
    if res:
        nq = sum(len(v) for v in res.values())
        home.append('<a class="rbox" href="research/" onclick="hmEv&&hmEv(\'research-home\')"><span class="rk">논문으로 따져 봤습니다</span>'
                    f'<b>영양제 논문 정리</b><span class="rn">성분 {len(res)}개 · 질문 {nq}개 · 대형 임상·메타분석</span><span class="rg">보기 ›</span></a>')
    rows = []
    for g in guides:
        items = gclean(c, g, prods.get(g["slug"]) or [])
        if items:
            rows.append(f'<section class="row" id="{g["slug"]}"><h2>{esc(g["name"])}<span class="ad">광고</span><a class="more" href="guide/{g["slug"]}/">고르는 법 먼저 보기 ›</a></h2>'
                        f'<div class="grid" data-sub="h-{g["slug"]}">{"".join(card(p) for p in items[:5])}</div></section>')
    if rows:
        home.append('<h2 class="sec">성분별 쿠팡 상품<small>쿠팡 검색 결과 · 추천·보증 아님</small></h2>' + chips + "".join(rows))
    if best:
        home.append(f'<h2>헬스·건강식품 베스트<span class="ad">광고</span><small>쿠팡 카테고리 베스트</small></h2><div class="grid" data-sub="best">{"".join(card(p) for p in best[:10])}</div><p><a href="best/">전체 보기 ›</a></p>')
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
        body, desc = guide_body(c, cat, g, res)
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
    research_pages(c, cat, res, base, org, w, lastmod)
    # 베스트(상품만 있는 페이지 — 검색 색인 제외)
    if best:
        w("best/index.html", page(c, cat, f"헬스·건강식품 베스트 | {c['name']}", f'<h1 class="t">헬스·건강식품 베스트<span class="ad">광고</span></h1><p class="lead">쿠팡 헬스/건강식품 카테고리 베스트를 자동으로 가져옵니다. 추천·보증이 아닙니다.</p><div class="grid" data-sub="best">{"".join(card(p) for p in best)}</div>',
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
    ad = c.get("adsense") or {}
    if ad.get("client", "").startswith("ca-pub-"):
        # 하위 도메인 ads.txt(IAB 허용). 본 도메인 ads.txt는 사이트 빌드가 만든다
        w("ads.txt", f"google.com, {ad['client'][3:]}, DIRECT, f08c47fec0942fa0\n")
    if c.get("indexnow_key"):
        w(f"{c['indexnow_key']}.txt", c["indexnow_key"])
    # /best/ 는 막지 않는다(막으면 noindex를 못 읽음). 페이지의 noindex로 색인에서 뺀다
    daum = ((c.get("verification") or {}).get("daum") or "").strip()  # 다음 웹마스터도구 PIN 인증 줄(공개값)
    w("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n" + (f"\n#DaumWebMasterTool:{daum}\n" if daum else ""))
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
