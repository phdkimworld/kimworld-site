# 썸네일 V8 '캐릭터판'(2026-11-28 운영자 승인 틀, 11-28 이후 새 회차부터. 이미 공개한 영상 썸네일은 바꾸지 않는다).
# 근거: 미디어 저장소 skill/runbooks/taste.md 15절(같은 글꼴·같은 위치·같은 남색 바탕, 종목별 강조색 하나만) + 13절(그라데이션 글자 금지, 글자색 3 이하,
#       크기 위계 1.25배 이상, 느낌표 금지). 시안 그림: 미디어 review/brand/thumb_layout_mock.jpg.
# 틀(1280×720, 위치 고정 — taste.md 15절 표와 같은 숫자):
#  ① 왼쪽 위 인용 한 줄 "…"(22자 이하, 34px 500, 연회색)     ② 오른쪽 위 브랜드(V7과 같은 자리)
#  ③ 왼쪽 약 60% 장면: 주가선(40,170,300×240) + 사업 그림(400,86,400×380)  — V7과 같은 biz_svg/biz_from·closes
#  ④ 오른쪽 약 40% 캐릭터(assets/drkim_character.png): 높이 634px(88%), 바닥 맞춤, left 866(11-28 운영자가 준 수채화 그림, 오른쪽 넘침은 잘림) — 글자 상자와 겹치지 않음(렌더 때 확인)
#  ⑤ 왼쪽 아래 글자 상자(32,456,828×236 → 오른쪽 끝 860 < 880, 재생 시간 자리 비움), 강조색 테두리 5px
#     1줄 = 종목명 + 핵심 숫자(84px 900, 강조색) / 2줄 = 질문(84px 900, 흰색). 티커 칩은 상자 위 테두리에 걸친다.
# 강조색: spec.accent가 없으면 thumb_history.json에서 그 종목 '첫 회차'의 accent(없으면 palette 이름의 첫 색 낱말)를 쓰고,
#         기록이 없으면 FALLBACK 목록에서 티커로 고른다. 결과는 출력 폴더 meta.json에 남기니 회차 기록(thumb_history)에 "accent"로 적는다.
# 사용: python3 make_v8.py spec.json <출력 폴더> [--png] [--history <thumb_history.json>]
#  spec 예: {"name":"리졸브 AI","ticker":"RZLV","quote":"대출 만기까지 34일 남았습니다","number":"0.88달러","question":"더 내려갈까?",
#            "biz_chip":"쇼핑 AI","biz_desc":"쇼핑 검색 소프트웨어","biz_svg":"<g>…</g>"(또는 "biz_from"),"closes":[…],"hi_last":5,"dir":"down",
#            "alt":{"question":"…"}(선택: b.html은 문구·숫자만 바꾼 같은 틀)}
# 출력: a.html·bg.html(글자·캐릭터 없는 장면, 영상 hero용)·(alt 있으면 b.html)·char.png·meta.json, --png면 a.png·a.jpg 등
# 기존 검사(thumb_biz_check·thumb_name_check·thumb_overflow_check·thumb_taste_check)의 class·id 이름을 지킨다.
import json, os, re, sys, math, shutil, hashlib, html as H

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from make_v7 import biz_group, chart_path, BRAND_GOLD, BRAND_NAVY, BRAND_TEXT, DIR_COLOR  # noqa: E402

CHAR_PNG = os.path.join(KIT, "assets", "drkim_character.png")
# 고정 위치(바꾸면 taste.md 15절 표와 thumb_taste_check THUMB_V8_POS도 같이 바꾼다)
POS = dict(quote=(40, 34), box=(32, 456, 828, 236), line1=(28, 26), line2=(28, 128), tick=(56, 430),
           brand=(34, 30), chart=(40, 170, 300, 240), biz=(400, 86, 400, 380), chip=(40, 96), char_h=634, char_left=866)
QUOTE_MAX = 22
# palette 이름 낱말 → 어두운 상자 위에서 읽히는 밝은 강조색(바탕 낱말 navy·black 등은 건너뜀)
WORD_HEX = {"crimson": "#FF4D5E", "red": "#FF5A5F", "pink": "#FF6FB1", "magenta": "#FF4FD8", "violet": "#B69CFF", "purple": "#B69CFF",
            "orange": "#FF9F1C", "amber": "#FFC233", "gold": "#F5B83D", "yellow": "#FFE14A", "lime": "#B6FF3D", "green": "#3BE38B",
            "emerald": "#34D399", "teal": "#2DD4BF", "cyan": "#3EE8FF", "sky": "#5CC8FF", "ice": "#9FDCFF", "blue": "#5B9BFF",
            "electricblue": "#4D9FFF", "cobalt": "#6D8CFF", "steel": "#A9C1DA", "copper": "#E8925A", "mint": "#7CF5C8"}
BASE_WORDS = {"navy", "black", "white", "dark", "night", "charcoal", "gray", "grey", "steel", "ice", "deep", "midnight"}
FALLBACK = ["#B6FF3D", "#3EE8FF", "#FFC233", "#FF6FB1", "#5CC8FF", "#FF9F1C", "#2DD4BF", "#B69CFF"]
HISTORY_CANDIDATES = [os.environ.get("KW_THUMB_HISTORY", ""), os.path.join(KIT, "..", "..", "..", "kimworld-media", "thumb_history.json"),
                      "/home/user/kimworld-media/thumb_history.json", "/home/claude/kimworld-media/thumb_history.json"]

def palette_accent(pal):
    words = [w for w in re.split(r"[-_\s/]+", (pal or "").lower()) if w in WORD_HEX]
    for w in words:
        if w not in BASE_WORDS: return WORD_HEX[w]
    return WORD_HEX[words[0]] if words else None

def ticker_accent(ticker, history=None):
    """같은 종목은 첫 회차 색(taste.md 15절). (색, 근거) 반환."""
    t = ticker.lower()
    path = next((p for p in ([history] if history else HISTORY_CANDIDATES) if p and os.path.exists(p)), None)
    if path:
        runs = json.load(open(path, encoding="utf-8")).get("runs", [])
        mine = [r for r in runs if str(r.get("t") or r.get("ticker") or "").lower() == t]
        if mine:
            first = mine[0]                               # 파일 순서 = 기록 순서(가장 먼저 적힌 회차)
            if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(first.get("accent", ""))): return first["accent"], f"history:{first.get('date')}:accent"
            c = palette_accent(first.get("palette"))
            if c: return c, f"history:{first.get('date')}:palette={first.get('palette')}"
    i = int(hashlib.md5(t.encode()).hexdigest(), 16) % len(FALLBACK)
    return FALLBACK[i], "fallback"

CSS = """
html,body{margin:0;width:1280px;height:720px;overflow:hidden;background:%(navy)s;font-family:"Noto Sans CJK KR",sans-serif;word-break:keep-all}
.t{position:absolute;font-weight:900;line-height:1.1;white-space:nowrap;letter-spacing:-.03em}
.q{font-weight:500;letter-spacing:-.01em;text-shadow:0 2px 8px rgba(0,0,0,.6)}
.box{position:absolute;box-sizing:border-box;border:5px solid %(acc)s;border-radius:18px;background:rgba(4,8,16,.9);box-shadow:0 10px 30px rgba(0,0,0,.55)}
.box .t{position:absolute}
.ticker-tag{position:absolute;font-weight:900;font-size:40px;line-height:1;padding:7px 14px 9px;border-radius:10px;color:%(navy)s;background:%(acc)s;letter-spacing:.02em}
.biz-chip{position:absolute;font-weight:800;font-size:26px;line-height:1;color:%(navy)s;background:%(text)s;padding:7px 14px 9px;border-radius:8px;white-space:nowrap}
.brand{position:absolute;right:%(br)dpx;top:%(bt)dpx;display:flex;align-items:center;gap:10px;font-weight:900;font-size:34px;color:%(gold)s;letter-spacing:-.03em;
   text-shadow:0 3px 12px rgba(0,0,0,.8)}
.brand i{display:block;width:14px;height:14px;border-radius:50%%;background:%(gold)s;box-shadow:22px -8px 0 -2px %(gold)s}
#char{position:absolute;bottom:0;left:%(cl)dpx;height:%(ch)dpx}
"""

def page(spec, acc, with_text=True):
    col = DIR_COLOR.get(spec.get("dir", "flat"), BRAND_GOLD)
    css = CSS % dict(navy=BRAND_NAVY, gold=BRAND_GOLD, text=BRAND_TEXT, acc=acc, br=POS["brand"][0], bt=POS["brand"][1],
                     cl=POS["char_left"], ch=POS["char_h"])
    biz_desc = H.escape(spec.get("biz_desc") or spec["biz_chip"])
    svg = ['<svg width="1280" height="720" style="position:absolute;left:0;top:0"><defs>'
           '<linearGradient id="base" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2c4a72"/><stop offset=".6" stop-color="#1d3860"/><stop offset="1" stop-color="#112540"/></linearGradient>'
           '<radialGradient id="lamp" cx="80%" cy="45%" r="45%"><stop offset="0" stop-color="#C9D6E6" stop-opacity=".28"/><stop offset="1" stop-color="#C9D6E6" stop-opacity="0"/></radialGradient>'
           '<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C9D6E6" stop-opacity=".22"/><stop offset="1" stop-color="#C9D6E6" stop-opacity="0"/></linearGradient>'
           '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
           '</defs><rect width="1280" height="720" fill="url(#base)"/><rect width="1280" height="720" fill="url(#lamp)"/>']
    bx, by, bw, bh = POS["biz"]
    svg.append(f'<svg x="{bx}" y="{by}" width="{bw}" height="{bh}" id="bizwrap" overflow="visible">'
               f'<g id="biz" data-biz="{biz_desc}">{biz_group(spec)}</g></svg>')
    closes = spec.get("closes") or []
    if len(closes) >= 10:
        cx, cy, cw, ch = POS["chart"]
        d, pts = chart_path(closes, cx, cy, cw, ch)
        k = max(1, int(spec.get("hi_last", 1)))
        hd = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts[-k - 1:])
        ex, ey = pts[-1]
        svg.append(f'<path d="{d} L{ex:.1f} {cy+ch} L{cx} {cy+ch} Z" fill="url(#area)"/>'
                   f'<path d="{d}" fill="none" stroke="#C9D6E6" stroke-opacity=".75" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>'
                   f'<path d="{hd}" fill="none" stroke="{col}" stroke-width="12" stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>'
                   f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="13" fill="#fff" stroke="{col}" stroke-width="6"/>')
        if spec.get("dir") in ("up", "down"):
            px, py = pts[-2]; a = math.atan2(ey - py, ex - px)
            a = min(a, -0.6) if spec["dir"] == "up" else max(a, 0.6)
            tx, ty = ex + 70 * math.cos(a), ey + 70 * math.sin(a)
            h1 = (tx - 30 * math.cos(a - .55), ty - 30 * math.sin(a - .55)); h2 = (tx - 30 * math.cos(a + .55), ty - 30 * math.sin(a + .55))
            svg.append(f'<path d="M{ex:.1f} {ey:.1f} L{tx:.1f} {ty:.1f}" stroke="{col}" stroke-width="11" stroke-linecap="round" filter="url(#glow)"/>'
                       f'<path d="M{h1[0]:.1f} {h1[1]:.1f} L{tx:.1f} {ty:.1f} L{h2[0]:.1f} {h2[1]:.1f} Z" fill="{col}" stroke="{col}" stroke-width="5" stroke-linejoin="round"/>')
    svg.append('</svg>')
    out = [f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body data-layout="v8">', "".join(svg)]
    if with_text:
        out.append('<img id="char" src="char.png" alt="">')
        q = spec["quote"].strip().strip('"“”')
        nm, tk = H.escape(spec["name"]), H.escape(spec["ticker"])
        qx, qy = POS["quote"]; x, y, w, h = POS["box"]; l1, l2 = POS["line1"], POS["line2"]
        out.append(f'<div class="t q fit" data-max="720" style="left:{qx}px;top:{qy}px;font-size:34px;color:#D5DEE8">"{H.escape(q)}"</div>')
        out.append('<div class="brand" id="brand"><i></i>김박사 월드</div>')
        out.append(f'<div class="biz-chip" style="left:{POS["chip"][0]}px;top:{POS["chip"][1]}px">{H.escape(spec["biz_chip"])}</div>')
        out.append(f'<div class="box" id="tbox" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">')
        out.append(f'<div class="t fit" data-max="{w-2*l1[0]-10}" style="left:{l1[0]}px;top:{l1[1]}px;font-size:84px;color:{acc}">'
                   f'<span class="name-tag">{nm}</span> {H.escape(spec["number"])}</div>')
        out.append(f'<div class="t fit" data-max="{w-2*l2[0]-10}" style="left:{l2[0]}px;top:{l2[1]}px;font-size:84px;color:#fff">{H.escape(spec["question"])}</div>')
        out.append('</div>')
        out.append(f'<div class="ticker-tag" style="left:{POS["tick"][0]}px;top:{POS["tick"][1]}px">{tk}</div>')
    out.append("""<script>
(function(){const g=document.getElementById('biz'),w=document.getElementById('bizwrap');const b=g.getBBox();
const W=+w.getAttribute('width'),Hh=+w.getAttribute('height');const s=Math.min(W/b.width,Hh/b.height);
g.setAttribute('transform',`translate(${(W-b.width*s)/2-b.x*s},${(Hh-b.height*s)/2-b.y*s}) scale(${s})`);
document.querySelectorAll('.fit').forEach(e=>{const m=+e.dataset.max;let f=parseFloat(getComputedStyle(e).fontSize);const lo=e.classList.contains('q')?26:56;
 while(e.getBoundingClientRect().width>m&&f>lo){f-=2;e.style.fontSize=f+'px'}});})();
</script></body></html>""")
    return "".join(out)

def check_spec(spec):
    errs = []
    q = spec.get("quote", "").strip().strip('"“”')
    if not q: errs.append("quote 없음")
    if len(q) > QUOTE_MAX: errs.append(f"quote {len(q)}자 > {QUOTE_MAX}자")
    for k in ("name", "ticker", "number", "question", "biz_chip"):
        if not spec.get(k): errs.append(f"{k} 없음")
    if any(c in "".join(str(spec.get(k, "")) for k in ("quote", "number", "question", "name")) for c in "!！"): errs.append("느낌표 금지(taste 13절)")
    return errs

def char_overlap(out_dir):
    """캐릭터(불투명 픽셀)가 글자 상자·티커 칩·인용·브랜드와 겹치는지 — 렌더 없이 위치·알파로 계산."""
    from PIL import Image
    import numpy as np
    im = Image.open(os.path.join(out_dir, "char.png")).convert("RGBA")
    hh = POS["char_h"]; ww = round(im.width * hh / im.height)
    A = np.asarray(im.resize((ww, hh)))[..., 3]
    top = 720 - hh; L = POS["char_left"]
    x, y, w, h = POS["box"]
    rects = {"box": (x, y - 30, x + w, y + h)}                 # 티커 칩(상자 위 30px)까지
    bad = []
    for n, (x0, y0, x1, y1) in rects.items():
        sx0, sx1 = max(x0 - L, 0), min(x1 - L, ww); sy0, sy1 = max(y0 - top, 0), min(y1 - top, hh)
        if sx1 > sx0 and sy1 > sy0 and (A[sy0:sy1, sx0:sx1] > 24).any():
            ys, xs = np.where(A[sy0:sy1, sx0:sx1] > 24); bad.append(f"{n}: 캐릭터가 x≤{x1} 안으로 {int(x1 - (xs.min() + sx0 + L))}px 들어옴")
    return bad

def render(paths):
    import asyncio
    from playwright.async_api import async_playwright
    from PIL import Image
    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1280, "height": 720})
            for h in paths:
                await pg.goto("file://" + os.path.abspath(h)); await pg.wait_for_timeout(500)
                await pg.screenshot(path=h[:-5] + ".png")
            await b.close()
    asyncio.run(go())
    for h in paths:
        Image.open(h[:-5] + ".png").convert("RGB").save(h[:-5] + ".jpg", quality=92)

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
    hist = sys.argv[sys.argv.index("--history") + 1] if "--history" in sys.argv else spec.get("history")
    errs = check_spec(spec)
    if errs: print("V8_SPEC_FAIL", "; ".join(errs)); sys.exit(1)
    acc, why = (spec["accent"], "spec") if spec.get("accent") else ticker_accent(spec["ticker"], hist)
    os.makedirs(out, exist_ok=True)
    shutil.copy(CHAR_PNG, os.path.join(out, "char.png"))
    files = []
    variants = [("a", spec, True), ("bg", spec, False)]
    if spec.get("alt"): variants.insert(1, ("b", {**spec, **spec["alt"]}, True))
    for n, sp, txt in variants:
        p = os.path.join(out, n + ".html"); open(p, "w", encoding="utf-8").write(page(sp, acc, txt)); files.append(p)
    ov = char_overlap(out)
    if ov: print("V8_CHAR_OVERLAP", "; ".join(ov)); sys.exit(1)
    json.dump({"layout": "v8", "ticker": spec["ticker"], "accent": acc, "accent_from": why}, open(os.path.join(out, "meta.json"), "w"), ensure_ascii=False)
    if "--png" in sys.argv: render(files)
    print("V8_OK", out, "accent", acc, why)
