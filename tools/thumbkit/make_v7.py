# 썸네일 V7 '원리판'(2026-11-24 운영자 "썸네일이나 각 페이지 디자인이 너무 조악한 거 같아. 대형채널들 찾아서 좀 배워").
# 근거: 미디어 저장소 review/design_study.md — 한국·해외 대형 경제 채널 11곳의 채널 평균 대비 1.6~9.9배 영상 30편을 우리 최근 10편과 비교.
# 원리(줄인 것): ① 주인공 하나를 크게(얼굴 대신 사업 물건 + 실제 주가선) ② 큰 글자 덩어리 3개 이하(이름표·질문·숫자)
#  ③ 글자색 둘(흰색 + 숫자색 하나), 테두리 상자 대신 짙은 그림자·바닥 어둡게 ④ 바탕은 검정이 아니라 밝은 남색(평균 밝기 2배)
#  ⑤ 숫자는 화면 높이 20% 이상, 주가선 끝에 붙여 '무슨 숫자인지' 그림으로 ⑥ 브랜드는 오른쪽 위 작게(브랜드 인트로와 같은 금색·글꼴)
#  ⑦ 오른쪽 아래(재생 시간 자리) 비움.
# 사용: python3 make_v7.py spec.json <출력 폴더>   → a.html·b.html·bg.html(+ --png 이면 a.png·b.png·bg.png)
#  spec 예: {"name":"아이렌","ticker":"IREN","biz_chip":"AI 데이터센터","biz_desc":"AI 데이터센터 회사: 서버 랙 + GPU",
#            "biz_svg":"<g>...</g>" 또는 "biz_from":"옛 a.html(안의 <g id=\"biz\"> 묶음을 가져옴)",
#            "question":"따라 사도 될까?","number":"+23.9%","label":"하루","dir":"up|down|flat",
#            "closes":[오래된→최근 종가 20~40개(사건이 보이는 구간)], "hi_last":1, "hue":"#0f766e",
#            "event_svg":{"a":"<g ...>", "b":"<g ...>"}(선택: 이번 사건 물건, 1280×720 좌표)}
# 기존 검사(thumb_biz_check·thumb_name_check·thumb_overflow_check)를 그대로 통과하도록 class·id 이름을 지킨다.
import json, os, re, sys, html as H

BRAND_GOLD, BRAND_NAVY, BRAND_TEXT = "#F5B83D", "#0B1524", "#E6EDF5"   # slidekit/brand/intro.html과 같은 색
DIR_COLOR = {"up": "#3BE38B", "down": "#FF5A5F", "flat": BRAND_GOLD}

def biz_group(spec):
    if spec.get("biz_svg"):
        inner = spec["biz_svg"]
    else:
        src = open(spec["biz_from"], encoding="utf-8").read()
        i = src.index('<g id="biz"'); depth, j = 0, i
        while True:
            o, c = src.find("<g", j), src.find("</g>", j)
            if o != -1 and o < c: depth += 1; j = o + 2
            else:
                depth -= 1; j = c + 4
                if depth == 0: break
        g = src[i:j]
        inner = re.sub(r'^<g id="biz"[^>]*>', "", g)[:-4]
    return inner

def chart_path(closes, x0, y0, w, h):
    lo, hi = min(closes), max(closes); rng = (hi - lo) or 1
    n = len(closes) - 1
    pts = [(x0 + w * i / n, y0 + h - h * (v - lo) / rng) for i, v in enumerate(closes)]
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    return d, pts

CSS = """
html,body{margin:0;width:1280px;height:720px;overflow:hidden;background:%(bg0)s;font-family:"Noto Sans CJK KR",sans-serif;word-break:keep-all}
.t{position:absolute;font-weight:900;line-height:1;white-space:nowrap;letter-spacing:-.04em;
   text-shadow:0 0 2px #000,0 4px 0 rgba(0,0,0,.55),0 8px 26px rgba(0,0,0,.85)}
.namebar{position:absolute;display:flex;align-items:center;gap:16px;white-space:nowrap}
.name-tag{font-weight:900;font-size:76px;line-height:1;color:#fff;letter-spacing:-.04em;text-shadow:0 4px 0 rgba(0,0,0,.5),0 8px 22px rgba(0,0,0,.8)}
.ticker-tag{font-weight:900;font-size:60px;line-height:1;padding:8px 16px 10px;border-radius:12px;color:%(navy)s;background:%(gold)s;letter-spacing:.02em}
.biz-chip{position:absolute;font-weight:800;font-size:40px;line-height:1;color:%(navy)s;background:%(text)s;padding:9px 18px 11px;border-radius:10px;white-space:nowrap}
.brand{position:absolute;right:34px;top:30px;display:flex;align-items:center;gap:10px;font-weight:900;font-size:34px;color:%(gold)s;letter-spacing:-.03em;
   text-shadow:0 3px 12px rgba(0,0,0,.8)}
.brand i{display:block;width:14px;height:14px;border-radius:50%%;background:%(gold)s;box-shadow:22px -8px 0 -2px %(gold)s}
"""

def page(spec, layout, with_text=True):
    hue = spec.get("hue", "#1d4ed8")
    col = DIR_COLOR.get(spec.get("dir", "flat"), BRAND_GOLD)
    css = CSS % dict(bg0=BRAND_NAVY, navy=BRAND_NAVY, gold=BRAND_GOLD, text=BRAND_TEXT)
    biz_desc = H.escape(spec.get("biz_desc") or spec["biz_chip"])
    # 바탕: 검정 대신 밝은 남색 + 주인공 뒤 조명(평균 밝기 목표 70 이상, 대형 채널 중앙값 87·우리 옛 판 47)
    if layout == "a":   # 아래 띠형: 위 60% 그림(주가선 + 사업 물건) / 아래 40% 글자 두 줄
        biz_box = (720, 120, 540, 330); chart_box = (40, 170, 580, 240); spot = ("78%", "40%")
    else:               # 옆 기둥형: 왼쪽 글자 / 오른쪽 사업 물건 크게
        biz_box = (690, 110, 570, 520); chart_box = (40, 590, 600, 90); spot = ("74%", "48%")
    svg = [f'<svg width="1280" height="720" style="position:absolute;left:0;top:0"><defs>'
           f'<linearGradient id="base" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#34557f"/><stop offset=".6" stop-color="#22406a"/><stop offset="1" stop-color="#132a48"/></linearGradient>'
           f'<radialGradient id="spot" cx="{spot[0]}" cy="{spot[1]}" r="58%"><stop offset="0" stop-color="{hue}" stop-opacity="1"/><stop offset=".55" stop-color="{hue}" stop-opacity=".42"/><stop offset="1" stop-color="{hue}" stop-opacity="0"/></radialGradient>'
           f'<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C9D6E6" stop-opacity=".22"/><stop offset="1" stop-color="#C9D6E6" stop-opacity="0"/></linearGradient>'
           f'<linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".62"/></linearGradient>'
           f'<linearGradient id="leftdark" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000" stop-opacity=".55"/><stop offset="1" stop-color="#000" stop-opacity="0"/></linearGradient>'
           f'<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
           f'</defs><rect width="1280" height="720" fill="url(#base)"/><rect width="1280" height="720" fill="url(#spot)"/>']
    bx, by, bw, bh = biz_box
    svg.append(f'<svg x="{bx}" y="{by}" width="{bw}" height="{bh}" id="bizwrap" overflow="visible">'
               f'<g id="biz" data-biz="{biz_desc}">{biz_group(spec)}</g></svg>')
    if with_text and spec.get("event_svg"):              # 이번 회차 사건 물건(서류·도장 등, 1280×720 좌표 그대로). V5 '사업 그림에 사건을 얹는다'
        ev = spec["event_svg"]
        svg.append(ev.get(layout, ev.get("a", "")) if isinstance(ev, dict) else ev)
    closes = (spec.get("closes") or []) if with_text else []
    if len(closes) >= 10 and layout == "a":           # 옆 기둥형은 사업 물건 하나가 주인공(주가선 없음)
        cx, cy, cw, ch = chart_box
        d, pts = chart_path(closes, cx, cy, cw, ch)
        k = max(1, int(spec.get("hi_last", 1)))           # 사건 구간(끝 k거래일)만 숫자색, 나머지는 옅은 회색: '무슨 숫자인지'를 선이 말하게
        hd = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts[-k - 1:])
        ex, ey = pts[-1]
        sw = 8 if layout == "a" else 6
        svg.append(f'<path d="{d} L{ex:.1f} {cy+ch} L{cx} {cy+ch} Z" fill="url(#area)"/>'
                   f'<path d="{d}" fill="none" stroke="#C9D6E6" stroke-opacity=".75" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>'
                   f'<path d="{hd}" fill="none" stroke="{col}" stroke-width="{sw+6}" stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>'
                   f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{15 if layout=="a" else 11}" fill="#fff" stroke="{col}" stroke-width="7"/>')
        if spec.get("dir") in ("up", "down"):            # 방향 화살표 하나(대형 채널 공통 장치): 사건 구간 방향으로 90px 더 뻗음
            px, py = pts[-2]; import math
            a = math.atan2(ey - py, ex - px)
            if spec["dir"] == "up": a = min(a, -0.6)
            else: a = max(a, 0.6)
            tx, ty = ex + 95 * math.cos(a), ey + 95 * math.sin(a)
            hx1, hy1 = tx - 38 * math.cos(a - .55), ty - 38 * math.sin(a - .55)
            hx2, hy2 = tx - 38 * math.cos(a + .55), ty - 38 * math.sin(a + .55)
            svg.append(f'<path d="M{ex:.1f} {ey:.1f} L{tx:.1f} {ty:.1f}" stroke="{col}" stroke-width="14" stroke-linecap="round" filter="url(#glow)"/>'
                       f'<path d="M{hx1:.1f} {hy1:.1f} L{tx:.1f} {ty:.1f} L{hx2:.1f} {hy2:.1f} Z" fill="{col}" stroke="{col}" stroke-width="6" stroke-linejoin="round"/>')
    if layout == "a":
        svg.append('<rect x="0" y="380" width="1280" height="340" fill="url(#floor)"/>')
    else:
        svg.append('<rect x="0" y="0" width="760" height="720" fill="url(#leftdark)"/><rect x="0" y="470" width="1280" height="250" fill="url(#floor)"/>')
    svg.append('</svg>')
    out = [f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>', "".join(svg)]
    if with_text:
        nm, tk = H.escape(spec["name"]), H.escape(spec["ticker"])
        q, num, lab = H.escape(spec["question"]), H.escape(spec["number"]), H.escape(spec.get("label", ""))
        out.append(f'<div class="namebar" id="nb" style="left:40px;top:30px"><span class="name-tag">{nm}</span><span class="ticker-tag">{tk}</span></div>')
        out.append('<div class="brand" id="brand"><i></i>김박사 월드</div>')
        if layout == "a":
            out.append(f'<div class="biz-chip" style="left:{bx+bw-330}px;top:{by-6}px">{H.escape(spec["biz_chip"])}</div>')
            out.append(f'<div class="t fit" data-max="1200" style="left:40px;top:446px;font-size:100px;color:#fff">{q}</div>')
            out.append(f'<div class="t fit" data-max="980" style="left:36px;top:560px;font-size:150px;color:{col}">{num}'
                       + (f'<span style="font-size:66px;color:#fff;margin-left:22px;letter-spacing:-.03em">{lab}</span>' if lab else '') + '</div>')
        else:
            out.append(f'<div class="biz-chip" style="left:{bx+bw-300}px;top:{by+18}px">{H.escape(spec["biz_chip"])}</div>')
            out.append(f'<div class="t fit" data-max="630" style="left:40px;top:150px;font-size:104px;color:#fff">{q}</div>')
            if lab: out.append(f'<div class="t fit" data-max="600" style="left:44px;top:290px;font-size:64px;color:{BRAND_TEXT}">{lab}</div>')
            out.append(f'<div class="t fit" data-max="620" style="left:32px;top:{372 if lab else 320}px;font-size:184px;color:{col}">{num}</div>')
    # 맞춤: 사업 그림을 상자에 맞게 키우고, 글자가 정한 폭을 넘으면 줄인다(검사 기준 아래로는 줄이지 않음 — 넘치면 overflow 검사가 잡음)
    out.append("""<script>
(function(){const g=document.getElementById('biz'),w=document.getElementById('bizwrap');const b=g.getBBox();
const W=+w.getAttribute('width'),Hh=+w.getAttribute('height');const s=Math.min(W/b.width,Hh/b.height);
g.setAttribute('transform',`translate(${(W-b.width*s)/2-b.x*s},${(Hh-b.height*s)/2-b.y*s}) scale(${s})`);
document.querySelectorAll('.fit').forEach(e=>{const m=+e.dataset.max;let f=parseFloat(getComputedStyle(e).fontSize);
 while(e.getBoundingClientRect().width>m&&f>60){f-=2;e.style.fontSize=f+'px';e.querySelectorAll('span').forEach(s=>s.style.fontSize=(f*.44)+'px')}});
const nb=document.getElementById('nb'),br=document.getElementById('brand');
if(nb&&br&&nb.getBoundingClientRect().right>br.getBoundingClientRect().left-24)br.style.display='none';})();
</script></body></html>""")
    return "".join(out)

def render(paths):
    import asyncio
    from playwright.async_api import async_playwright
    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1280, "height": 720})
            for h in paths:
                await pg.goto("file://" + os.path.abspath(h)); await pg.wait_for_timeout(500)
                await pg.screenshot(path=h[:-5] + ".png")
            await b.close()
    asyncio.run(go())

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    files = []
    for n, lay, txt in (("a", spec.get("main", "a"), True), ("b", "b" if spec.get("main", "a") == "a" else "a", True), ("bg", spec.get("main", "a"), False)):
        p = os.path.join(out, n + ".html"); open(p, "w", encoding="utf-8").write(page(spec, lay, txt)); files.append(p)
    if "--png" in sys.argv: render(files)
    print("V7_OK", out)
