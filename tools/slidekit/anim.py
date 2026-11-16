# 코드로 그린 움직이는 장면(anim) — 슬라이드 하나를 프레임 캡처 클립으로 바꾼다(운영자 11-16 "고치고 적용", 시험 결과 review/anim-test).
# slides.json 슬라이드: {"from": 0, "anim": {"tpl": "live_chart|chalk_hook", "data": {..., "beats": [문장 번호…]}}}
#   - 틀은 templates/anim/<tpl>.html. 라이브러리(GSAP 3.12.5)·손글씨 글꼴은 templates/anim/lib/에 동봉(네트워크 없이 렌더)
#   - 박자: data의 "beats"(문장 번호 목록)와 "*_beat"(문장 번호 하나)를 그 문단 raw_timing의 문장 시작 시각(장면 시작 기준 초)으로 바꿔
#     window.ANIM.t로 넘긴다. 틀은 그 시각에 사건 점·숫자를 띄운다(내레이션이 말하는 순간 화면에 뜬다)
#   - 장면 계약: window.scene = {dur, ready, seek(t), boxes()?}. seek(t) 뒤 화면이 그 시각 그대로(실시간 녹화 아님, 매번 같은 결과)
#   - 겹침 검사: 박자마다와 마지막 프레임에서 글자 상자([data-box] 요소 또는 scene.boxes())가 서로 겹치거나 화면 밖이면 실패
# 단독 미리보기: python3 anim.py preview <tpl> <data.json> <출력 폴더> [--dur 초] [--beats 1.5,3,4.5]
#   → 출력 폴더에 preview.png(0·25·50·75·100% 다섯 장)와 ANIM_OK/ANIM_FAIL 한 줄
import os, sys, json, asyncio
KIT = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(KIT, 'templates', 'anim')
FPS = 30
GL_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
TPLS = sorted(f[:-5] for f in os.listdir(TPL_DIR) if f.endswith('.html')) if os.path.isdir(TPL_DIR) else []

def beat_keys(data):
    return [k for k in data if k == 'beats' or k.endswith('_beat')]

def beat_times(data, sents, t0, para_start=None):
    """문장 번호 → 장면 시작(t0) 기준 초. 0번 문장은 문단 시작 시각(make_slide_video와 같은 기준)."""
    st = lambda i: (para_start if (i == 0 and para_start is not None) else sents[i]['start']) - t0
    out = {}
    for k in beat_keys(data):
        v = data[k]
        out[k] = [None if i is None else round(max(0.0, st(i)), 3) for i in v] if isinstance(v, list) else (None if v is None else round(max(0.0, st(v)), 3))
    return out

BOX_JS = """() => {
  const vis = e => { for (let x = e; x && x.nodeType === 1; x = x.parentNode) { const s = getComputedStyle(x); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity < 0.05) return false } return true };
  let bx, fr = (window.scene.frame || [0, 0, 1920, 1080]);
  if (window.scene.boxes) bx = window.scene.boxes().map((b, i) => ({...b, name: 'box' + i}));
  else bx = [...document.querySelectorAll('[data-box]')].filter(e => (e.textContent || '').trim() && vis(e)).map(e => { const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, h: r.height, name: (e.textContent || '').trim().slice(0, 20)} });
  const bad = [];
  bx.forEach(b => { if (b.x < fr[0] - 1 || b.y < fr[1] - 1 || b.x + b.w > fr[2] + 1 || b.y + b.h > fr[3] + 1) bad.push('화면 밖: ' + b.name) });
  for (let i = 0; i < bx.length; i++) for (let j = i + 1; j < bx.length; j++) { const a = bx[i], b = bx[j];
    const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (ox > 4 && oy > 4) bad.push('겹침: ' + a.name + ' ↔ ' + b.name) }
  return bad }"""

async def render(browser, tpl, data, t, dur, outdir, deck=None, preview_only=False):
    """프레임 PNG 목록, 움직이는 길이(초), 문제 목록을 돌려준다. dur = 슬라이드 구간 길이."""
    assert tpl in TPLS, f'anim 틀 없음: {tpl} (있는 틀: {TPLS})'
    os.makedirs(outdir, exist_ok=True)
    pg = await browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    anim = {'data': data, 't': t, 'dur': dur, 'ticker': (deck or {}).get('ticker', ''), 'name': (deck or {}).get('name', '')}
    await pg.add_init_script('window.ANIM = ' + json.dumps(anim, ensure_ascii=False) + ';')
    await pg.goto('file://' + os.path.join(TPL_DIR, tpl + '.html'))
    await pg.wait_for_function('window.scene && window.scene.ready', timeout=20000); await pg.evaluate('scene.ready')
    sd = await pg.evaluate('scene.dur'); moving = min(dur, sd)
    n = max(1, round(moving * FPS)); probs = []
    checks = sorted({round(min(moving, b + 0.8), 3) for b in (await pg.evaluate('scene.beats || []')) if b is not None} | {moving})
    for c in checks:
        await pg.evaluate('t=>scene.seek(t)', c)
        probs += [f'{c:.1f}초 {p}' for p in await pg.evaluate(BOX_JS)]
    if sd > dur + 0.05: probs.append(f'장면({sd:.1f}초)이 슬라이드 구간({dur:.1f}초)보다 김: 끝 박자가 잘림 — beats를 앞당기거나 구간을 늘린다')
    idx = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1}); frames = []
    for i in (idx if preview_only else range(n)):
        await pg.evaluate('t=>scene.seek(t)', i / FPS)
        f = os.path.join(outdir, f'f{i:05d}.png'); await pg.screenshot(path=f); frames.append(f)
    await pg.close()
    probs += [f'페이지 오류: {e[:80]}' for e in errs[:3]]
    prev = [frames[idx.index(i)] if preview_only else frames[i] for i in idx]
    contact(prev, os.path.join(outdir, 'preview.png'))
    return frames, round(n / FPS, 3), probs, prev

def contact(files, out):
    from PIL import Image
    tw, th = 480, 270; sheet = Image.new('RGB', (tw * len(files), th), '#000')
    for i, f in enumerate(files): sheet.paste(Image.open(f).convert('RGB').resize((tw, th)), (i * tw, 0))
    sheet.save(out)

def main():
    import argparse
    from playwright.async_api import async_playwright
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['preview']); ap.add_argument('tpl'); ap.add_argument('data'); ap.add_argument('out')
    ap.add_argument('--dur', type=float, default=12.0); ap.add_argument('--beats', default=''); ap.add_argument('--ticker', default=''); ap.add_argument('--name', default='')
    a = ap.parse_args(); data = json.load(open(a.data, encoding='utf-8'))
    t = {'beats': [float(x) for x in a.beats.split(',') if x]} if a.beats else {}
    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(args=GL_ARGS)
            r = await render(b, a.tpl, data, t, a.dur, a.out, {'ticker': a.ticker, 'name': a.name}, preview_only=True)
            await b.close(); return r
    _, moving, probs, _ = asyncio.run(go())
    for p in probs: print('  ✗', p)
    print(('ANIM_FAIL' if probs else 'ANIM_OK'), a.tpl, f'움직임 {moving:.1f}초', os.path.join(a.out, 'preview.png'))
    sys.exit(1 if probs else 0)

if __name__ == '__main__': main()
