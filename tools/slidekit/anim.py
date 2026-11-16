# 코드로 그린 움직이는 장면(anim) — 슬라이드 하나를 프레임 캡처 클립으로 바꾼다(운영자 11-16 "고치고 적용", 시험 결과 review/anim-test).
# slides.json 슬라이드: {"from": 0, "anim": {"tpl": "live_chart|chalk_hook", "data": {..., "beats": [문장 번호…]}}}
#   - 틀은 templates/anim/<tpl>.html. 라이브러리(GSAP 3.12.5)·손글씨 글꼴은 templates/anim/lib/에 동봉(네트워크 없이 렌더)
#   - 박자: data의 "beats"(문장 번호 목록)와 "*_beat"(문장 번호 하나)를 그 문단 raw_timing의 문장 시작 시각(장면 시작 기준 초)으로 바꿔
#     window.ANIM.t로 넘긴다. 틀은 그 시각에 사건 점·숫자를 띄운다(내레이션이 말하는 순간 화면에 뜬다)
#   - 장면 계약: window.scene = {dur, ready, seek(t), boxes()?}. seek(t) 뒤 화면이 그 시각 그대로(실시간 녹화 아님, 매번 같은 결과)
#   - 겹침 검사: 박자마다와 마지막 프레임에서 글자 상자([data-box] 요소 또는 scene.boxes())가 서로 겹치거나 화면 밖이면 실패
# 그림 명세에서: python3 anim.py fromfig <figs.json> <n>  → {"tpl","data"}(beats만 더해 slides.json에)
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

WORKERS = int(os.environ.get('ANIM_WORKERS', '0')) or max(1, min(8, os.cpu_count() or 1))
CHUNK = 45  # 일꾼 하나가 한 번에 찍는 프레임 수(긴 장면도 여러 일꾼이 나눠 찍는다)

async def _open(browser, job, errs):
    pg = await browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
    pg.on('pageerror', lambda e: errs.append(str(e)))
    deck = job.get('deck') or {}
    anim = {'data': job['data'], 't': job['t'], 'dur': job['dur'], 'ticker': deck.get('ticker', ''), 'name': deck.get('name', '')}
    await pg.add_init_script('window.ANIM = ' + json.dumps(anim, ensure_ascii=False) + ';')
    await pg.goto('file://' + os.path.join(TPL_DIR, job['tpl'] + '.html'))
    try: await pg.wait_for_function('window.scene && window.scene.ready', timeout=20000)
    except Exception: await pg.close(); raise SystemExit(f"ANIM_FAIL {job['tpl']}: 장면이 준비되지 않음 — 페이지 오류 {errs[:3]}")
    await pg.evaluate('scene.ready')
    return pg

async def _probe(browser, job):
    """겹침 검사·장면 길이·움직이는 구간(spans)을 먼저 본다."""
    errs = []; pg = await _open(browser, job, errs); dur = job['dur']
    sd = await pg.evaluate('scene.dur'); moving = min(dur, sd); probs = []
    checks = sorted({round(min(moving, b + 0.8), 3) for b in (await pg.evaluate('scene.beats || []')) if b is not None} | {moving})
    for c in checks:
        await pg.evaluate('t=>scene.seek(t)', c)
        probs += [f'{c:.1f}초 {p}' for p in await pg.evaluate(BOX_JS)]
    if sd > dur + 0.05: probs.append(f'장면({sd:.1f}초)이 슬라이드 구간({dur:.1f}초)보다 김: 끝 박자가 잘림 — beats를 앞당기거나 구간을 늘린다')
    spans = await pg.evaluate('scene.spans || null')
    await pg.close()
    probs += [f'페이지 오류: {e[:80]}' for e in errs[:3]]
    return moving, probs, spans

def _shoot_list(n, spans):
    """프레임 i를 새로 찍어야 하나: 직전 프레임 뒤로 움직임(tween)이 하나라도 걸치면 찍고, 아니면 직전 프레임을 그대로 쓴다(정지 구간은 한 장)."""
    if not spans: return [True] * n
    out = [True]
    for i in range(1, n):
        a, b = (i - 1) / FPS, i / FPS
        out.append(any(s0 < b + 1e-6 and s1 > a - 1e-6 for s0, s1 in spans))
    return out

async def render_many(jobs, workers=None, preview_only=False):
    """여러 장면을 브라우저 여러 개(코어 수)로 나눠 찍는다. jobs: [{tpl, data, t, dur, outdir, deck}]
    → [(프레임 경로 목록(정지 구간은 같은 경로 반복), 움직임 길이 초, 문제 목록, 미리보기 다섯 장)]"""
    from playwright.async_api import async_playwright
    for j in jobs:
        assert j['tpl'] in TPLS, f"anim 틀 없음: {j['tpl']} (있는 틀: {TPLS})"
        os.makedirs(j['outdir'], exist_ok=True)
    W = max(1, min(workers or WORKERS, 8))
    async with async_playwright() as p:
        brs = await asyncio.gather(*[p.chromium.launch(args=GL_ARGS) for _ in range(W)])
        info = [None] * len(jobs)
        async def probe_worker(k):
            for ji in range(k, len(jobs), W): info[ji] = await _probe(brs[k], jobs[ji])
        await asyncio.gather(*[probe_worker(k) for k in range(W)])
        plan, tasks = [], []
        for ji, (moving, probs, spans) in enumerate(info):
            n = max(1, round(moving * FPS)); idx = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1})
            shoot = [i in idx for i in range(n)] if preview_only else _shoot_list(n, spans)
            if preview_only: shoot = [i in idx for i in range(n)]
            plan.append((n, idx, shoot))
            todo = [i for i in range(n) if shoot[i]]
            for c in range(0, len(todo), CHUNK): tasks.append((ji, todo[c:c + CHUNK]))
        q = asyncio.Queue()
        for t in tasks: q.put_nowait(t)
        page_errs = [[] for _ in jobs]
        async def shoot_worker(k):
            while not q.empty():
                ji, frames = q.get_nowait(); job = jobs[ji]
                pg = await _open(brs[k], job, page_errs[ji])
                for i in frames:
                    await pg.evaluate('t=>scene.seek(t)', i / FPS)
                    await pg.screenshot(path=os.path.join(job['outdir'], f'f{i:05d}.png'))
                await pg.close()
        await asyncio.gather(*[shoot_worker(k) for k in range(W)])
        await asyncio.gather(*[b.close() for b in brs])
    out = []
    for ji, job in enumerate(jobs):
        n, idx, shoot = plan[ji]; moving, probs, spans = info[ji]
        if preview_only: frames = [os.path.join(job['outdir'], f'f{i:05d}.png') for i in idx]; prev = frames
        else:
            frames, last = [], None
            for i in range(n):
                if shoot[i]: last = os.path.join(job['outdir'], f'f{i:05d}.png')
                frames.append(last)
            prev = [frames[i] for i in idx]
        contact(prev, os.path.join(job['outdir'], 'preview.png'))
        out.append((frames, round(n / FPS, 3), probs + [f'페이지 오류: {e[:80]}' for e in page_errs[ji][:2]], prev))
    return out

async def render(browser, tpl, data, t, dur, outdir, deck=None, preview_only=False):
    """(옛 호출 호환) 장면 하나. browser 인자는 쓰지 않는다(render_many가 자기 브라우저를 띄움)."""
    return (await render_many([{'tpl': tpl, 'data': data, 't': t, 'dur': dur, 'outdir': outdir, 'deck': deck}], preview_only=preview_only))[0]

# 리포트 그림 명세(figkit figs.json)의 그림 하나 → anim data. 같은 숫자를 영상과 리포트가 함께 쓴다(지어낸 숫자 방지, 토큰 절약)
#   figkit 유형 → 틀: compare→compare_bars, relative→relative_lines, record→record_bars, scenarios→scenario_bars, trend→trend_line, price_events→live_chart
FIG2TPL = {'compare': 'compare_bars', 'relative': 'relative_lines', 'record': 'record_bars', 'scenarios': 'scenario_bars', 'trend': 'trend_line', 'price_events': 'live_chart'}
def _figkit():
    import importlib.util
    for c in [os.environ.get('FIGKIT', ''), '/home/user/kimworld-media/tools/figkit/make.py', os.path.join(KIT, '..', '..', '..', 'kimworld-media', 'tools', 'figkit', 'make.py')]:
        if c and os.path.exists(c):
            sp = importlib.util.spec_from_file_location('figkit_make', c); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
    raise SystemExit('figkit(make.py)을 찾지 못함: FIGKIT=<경로>')
def _md(s): return '%d.%d' % (int(s[5:7]), int(s[8:10])) if len(s) >= 10 and s[4] == '-' else s
def fig_to_anim(figs_path, n):
    doc = json.load(open(figs_path, encoding='utf-8')); base = os.path.dirname(os.path.abspath(figs_path))
    fig = next(f for f in doc['figs'] if f.get('n') == n); t = fig['type']; tpl = FIG2TPL[t]
    src = ' · '.join(x for x in [fig.get('source', doc.get('source')), ('기준 ' + fig.get('asof', doc.get('asof', ''))) if fig.get('asof', doc.get('asof')) else ''] if x)
    out = {'title': ' '.join(fig['title']) if isinstance(fig.get('title'), list) else fig.get('title', ''), 'source': src}
    for k in ('sub', 'note', 'unit', 'decimals'):
        if k in fig: out[k] = fig[k]
    if t in ('compare', 'record', 'trend'): out['items'] = fig['items']
    if t == 'trend' and fig.get('ref'): out['ref'] = fig['ref']
    if t == 'scenarios': out['items'] = fig['items']; out['decision'] = fig.get('decision', '')
    if t in ('relative', 'price_events'):
        fk = _figkit()
    if t == 'relative':
        ser = []
        for s in fig['series']:
            rows = [(dd, v) for dd, v in fk.load_series(s['data'], base) if fig['base'] <= dd <= fig.get('to', '9999')]
            ser.append({'name': s['name'], 'points': [[_md(dd), v] for dd, v in rows], **({'hi': True} if s.get('hi') or not ser else {})})
        out['series'] = ser; out['base_label'] = _md(fig['base']) + ' = 100'
    if t == 'price_events':
        rows = dict(fk.load_series(fig['series'], base)); pts = []
        for e in fig['events'][:8]:
            lab = e['label']; lab = lab.split(' ', 1)[1] if lab.split(' ', 1)[0].replace('.', '').isdigit() and ' ' in lab else lab
            pts.append([_md(e['date']), rows[e['date']], lab])
        out['points'] = pts; out['unit'] = fig.get('unit', '달러'); out.pop('decimals', None)
        if fig.get('ref'): out['base'] = {'value': fig['ref']['v'], 'label': fig['ref'].get('label', '')}
    return tpl, out

def contact(files, out):
    from PIL import Image
    tw, th = 480, 270; sheet = Image.new('RGB', (tw * len(files), th), '#000')
    for i, f in enumerate(files): sheet.paste(Image.open(f).convert('RGB').resize((tw, th)), (i * tw, 0))
    sheet.save(out)

def main():
    import argparse
    if sys.argv[1:2] == ['fromfig']:  # python3 anim.py fromfig <figs.json> <n> → {"tpl", "data"} JSON(slides.json 'anim' 자리에 그대로, beats만 더한다)
        tpl, data = fig_to_anim(sys.argv[2], int(sys.argv[3])); print(json.dumps({'tpl': tpl, 'data': data}, ensure_ascii=False)); return
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['preview']); ap.add_argument('tpl'); ap.add_argument('data'); ap.add_argument('out')
    ap.add_argument('--dur', type=float, default=12.0); ap.add_argument('--beats', default=''); ap.add_argument('--ticker', default=''); ap.add_argument('--name', default='')
    a = ap.parse_args(); data = json.load(open(a.data, encoding='utf-8'))
    t = {'beats': [float(x) for x in a.beats.split(',') if x]} if a.beats else {}
    async def go():
        return await render(None, a.tpl, data, t, a.dur, a.out, {'ticker': a.ticker, 'name': a.name}, preview_only=True)
    _, moving, probs, _ = asyncio.run(go())
    for p in probs: print('  ✗', p)
    print(('ANIM_FAIL' if probs else 'ANIM_OK'), a.tpl, f'움직임 {moving:.1f}초', os.path.join(a.out, 'preview.png'))
    sys.exit(1 if probs else 0)

if __name__ == '__main__': main()
