# 음성 동기 슬라이드 영상: slides.json + TTS 시각표 → 문장 단위로 슬라이드가 바뀌고, 사이트 안내 문장 동안만 미드롤 이미지
# 사용: python3 make_slide_video.py slides.json raw.wav 출력.mp4   (효과음·배경 드론 끄기: NO_SFX=1)
#   효과음은 sfx.py가 코드로 합성한다. 화면 전환=whoosh, 훅·단서·반전·답=boom, 훅 질문 직전=riser, 미드롤·마무리=chime, 숫자 카드=tick
#   slides.json의 화면마다 "sfx": "boom|whoosh|riser|chime|tick|none"으로 직접 정할 수 있다
#   raw.wav 옆의 raw_timing.json(st_tts.py가 만든다)을 읽는다. 프레임과 확인용 contact.png는 출력 폴더의 slides_out/에 저장
#   (11-16 확대) 움직이는 장면은 코어 수만큼 브라우저로 나눠 찍고(ANIM_WORKERS로 조절), 움직임이 없는 프레임은 다시 찍지 않는다
#   움직이는 장면(2026-11-16): 슬라이드에 "anim": {"tpl": "live_chart|chalk_hook", "data": {..., "beats": [문장 번호…]}}이 있으면
#   그 슬라이드 구간 전체를 anim.py로 프레임 캡처해 넣는다(박자 = 문장 시작 시각). segments.json 'anim'에 [시작, 움직임 끝, 구간 끝, 틀]을 남겨
#   video_check·'최장 정지' 지표가 움직이는 구간을 정지로 세지 않는다. 장면마다 slides_out/anim_*/preview.png(다섯 장)를 눈으로 확인
#   브랜드(2026-11-22 운영자 "인트로 영상을 만들어서 브랜드를 각인하고 아웃트로 영상도 넣어서 홍보장으로 활용", brand.py):
#   ① 인트로 brand/intro.mp4(2.4초, 목소리 없음)를 **영상 맨 앞(0초)**에 놓고 음성 앞에도 같은 길이를 비워 소리 로고를 넣는다
#      (운영자 2026-11-22 "인트로로 브랜드를 각인하라고 했잖아" — 훅 뒤 15초대 스팅은 인트로로 인식되지 않았다). 화면에는 회차 질문 한 줄을 작게(brand.intro_question).
#      나레이션 전체가 2.4초 밀린다 → 영상 시간축 문장 시각은 slides_out/timing_video.json, segments.json 'brand_intro' = [0, 길이]
#      (자막 yt_captions.py·설명란 챕터 brand_shift.py가 이걸 읽는다 — 챕터 첫 항목 00:00은 그대로, 나머지 +길이). 인트로 직후 첫 장면은 예전 0초 표지처럼
#      움직임 없이 컷으로 뜬다. 예전 방식(훅 뒤 스팅): deck "brand_intro_para": 문단 번호(1~끝에서 두 번째) 또는 "hook"(시작 15초 이상인 첫 문단)
#   ② outro 슬라이드 → 브랜드 엔드카드(워드마크·정체성·홍보 칸 2개, deck "outro_promo"). 끄기: NO_BRAND=1(둘 다), deck "brand_intro": false / "brand_end": false
#   광고 구분(2026-11-26 운영자 "광고는 시각적으로나 호흡으로나 딱 구분되는게 더 이목을 끌거 같아"): 문단 "kind": "ad"(영양제 중간광고 문단)이면
#   ① 그 문단 슬라이드는 광고 화면(slide.html admode: 초록 바탕·위 띠·'광고' 배지·대가성 줄, layout 'product' = 제품 조건 카드)
#   ② 문단 앞 0.8초 무음 + '광고' 표지 화면 + 알림음(sfx adin), 문단 뒤 0.6초 무음(광고 화면 유지) 뒤 본편 전환음. 길이는 deck "ad_gap_pre"·"ad_gap_post"
#   (2026-11-27 RZLV 전환 분석) 광고 문단 안 'shop' 문장도 광고 화면 유지(남색 카드 안 씀) · 표지 한 줄은 짧게(기본 '유료 광고 포함') ·
#   쿠팡 띠는 마지막 2분 안 한 번, 위험 문단("tone": "risk"·kicker 위험) 밖(segments 'strip_rule': 'last2') · 전환음 -6dB(sfx.py)
#   나레이션이 그만큼 밀린다 → timing_video.json, segments.json 'ad_gaps' = [[영상 시각, 길이]…], 'ad_kind' = [광고 시작, 끝](표지~무음 끝, ad_gap_check·video_check가 읽음)
import json, sys, os, asyncio, subprocess, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfx, anim
from PIL import Image
from playwright.async_api import async_playwright
KIT = os.path.dirname(os.path.abspath(__file__))
spec_p, raw, out = [os.path.abspath(a) for a in sys.argv[1:4]]
deck = json.load(open(spec_p, encoding='utf-8')); base = os.path.dirname(spec_p)
tm = json.load(open(os.path.splitext(raw)[0] + '_timing.json', encoding='utf-8'))
P = tm['paras']; D = deck['paras']
assert len(P) == len(D), f'문단 수 불일치: 음성 {len(P)} / slides.json {len(D)}'
absp = lambda p: p if os.path.isabs(p) else os.path.join(base, p)
import brand
BRAND = not os.environ.get('NO_BRAND')
brand_at, brand_sec = None, 0.0  # 인트로를 끼운 시각(원래 음성 기준 = 영상 기준)과 길이
if BRAND and deck.get('brand_intro', True) is not False and os.path.exists(brand.INTRO) and len(P) > 2:
    bp = deck.get('brand_intro_para') or 0  # 0(기본) = 영상 맨 앞
    if bp == 'hook': bp = next((i for i in range(1, len(P) - 1) if P[i]['start'] >= 15.0), None)
    if bp == 0 or (isinstance(bp, int) and 0 < bp < len(P) - 1):
        brand_at = 0.0 if bp == 0 else round(P[bp]['start'], 3)
        brand_q = brand.intro_question(deck, base) if bp == 0 else None  # 회차 질문 한 줄은 0초 인트로에만
        brand_fr = brand.intro_frames(os.path.join(os.path.dirname(out), 'slides_out', 'brand_intro'), brand_q)
        brand_sec = len(brand_fr) / anim.FPS
        for p_ in P[bp:]:  # 뒤 문단을 통째로 미룬다(나레이션은 그대로, 사이에 스팅)
            p_['start'] += brand_sec; p_['end'] += brand_sec
            for s_ in p_['sents']: s_['start'] += brand_sec; s_['end'] += brand_sec
        tm['duration'] += brand_sec
# 광고 숨 고르기(2026-11-26): kind "ad" 문단 앞뒤로 무음. 인트로 뒤 시각(영상 기준)으로 계산하고 음성에도 같은 순서로 빈칸을 넣는다
AD_PRE, AD_POST = float(deck.get('ad_gap_pre', 0.8)), float(deck.get('ad_gap_post', 0.6))
ad_pi = next((i for i, pd in enumerate(D) if pd.get('kind') == 'ad' and 0 < i < len(P) - 1), None)
if ad_pi is not None and brand_at is not None and brand_at > P[ad_pi]['start']: ad_pi = None  # 예전 방식 인트로가 광고 뒤면 숨 고르기 생략(시각 꼬임 방지)
ad_gaps, ad_kind = [], None
if ad_pi is not None:
    for side, sec, frm in (('start', AD_PRE, ad_pi), ('end', AD_POST, ad_pi + 1)):  # 'end'는 앞 무음을 넣은 뒤 시각으로 읽는다
        if sec <= 0: continue
        at = round(P[ad_pi][side], 3); ad_gaps.append((at, sec))
        for p_ in P[frm:]:
            p_['start'] += sec; p_['end'] += sec
            for s_ in p_['sents']: s_['start'] += sec; s_['end'] += sec
        tm['duration'] += sec
    ad_kind = (ad_gaps[0][0] if AD_PRE > 0 else P[ad_pi]['start'], P[ad_pi + 1]['start'])
isag = lambda k: k[0] == 'AG'
cover_t = brand_sec if brand_at == 0.0 else 0.0  # 첫 장면(표지 역할)이 뜨는 시각: 0초 인트로면 인트로 끝
BRAND_END = BRAND and deck.get('brand_end', True) is not False
promo = brand.pick(deck) if BRAND_END else []
isbr = lambda k: k[0] == 'BR'
midroll = absp(deck['midroll'])
# 운영자 지시 2026-10-21: 미드롤에서 리포트 말고 사이트·앱 기능도 광고한다.
# deck에 'midroll_app'(사이트·앱 기능 이미지)이 있으면 마지막 전체 화면 안내(닫기)에 그 이미지를 띄운다
midroll_app = absp(deck['midroll_app']) if deck.get('midroll_app') else None
# 운영자 지시 2026-11-10: 쿠팡 상품 카드(tools/midroll/make_shop_card.py). deck 'shop' = 카드 이미지, 문단 'shop' = [문장 번호]. 그 문장 동안 전체 화면
# (미드롤 30초 상한과 따로 센다. 한 영상에 한 문장, 10초 이하 권장 — check_slides.py SHOP)
shop_img = absp(deck['shop']) if deck.get('shop') else None
isad = lambda k: k[0] == 'AD'
wd = os.path.join(os.path.dirname(out), 'slides_out'); os.makedirs(wd, exist_ok=True)

# 1) 문장마다 보여 줄 화면 결정
# 영상 제작 지침 v1 A6: 전체 화면 미드롤은 '맛보기'(두 번째 안내 문단)와 '닫기'(마지막 안내 문단)에만.
# 나머지 안내 문장은 슬라이드를 유지하고 하단 배너. 문단에 "ad_style": "full"|"banner"로 직접 정할 수 있다
ad_paras = [i for i, pd in enumerate(D) if pd.get('ad')]
def ad_style(pi):
    st = D[pi].get('ad_style')
    if st: return st
    n = ad_paras.index(pi)
    return 'full' if (n == 1 or n == len(ad_paras) - 1) else 'banner'
seq = []  # (시작 시각, 키)
full_used = 0.0  # 전체 화면 미드롤 합계가 30초를 넘게 되는 문장은 배너로 돌린다(지침 A6 합격 기준)
for pi, (pt, pd) in enumerate(zip(P, D)):
    ads = set(pd.get('ad', [])); sl = sorted(pd['slides'], key=lambda s: s.get('from', 0))
    for si, s in enumerate(pt['sents']):
        t0 = cover_t if (pi == 0 and si == 0) else (pt['start'] if si == 0 else s['start'])
        k = max(i for i, x in enumerate(sl) if x.get('from', 0) <= si) if any(x.get('from', 0) <= si for x in sl) else 0
        sdur = s['end'] - s['start']
        if BRAND_END and sl[k].get('layout') == 'outro': key = ('BR', 'end')  # 브랜드 엔드카드(나레이션 outro 문단은 그대로 위에)
        # 11-27 광고 블록 테마: kind "ad" 문단 안의 'shop' 문장은 남색 쿠팡 카드로 바꾸지 않고 광고 화면(admode) 슬라이드를 그대로 — 마지막 광고 장면·뒤 무음까지 초록
        elif shop_img and si in set(pd.get('shop', [])) and pd.get('kind') != 'ad': key = ('AD', 'shop')
        elif si in ads and ad_style(pi) == 'full' and full_used + sdur <= 30.0:
            key = ('AD', 'app' if midroll_app and pi == ad_paras[-1] else 'rep'); full_used += sdur
        elif sl[k].get('anim'): key = (pi, k, 'anim')  # 움직이는 장면: 슬라이드 전체가 한 구간(배너 안내 문장도 장면 그대로)
        elif si in ads: key = (pi, k, si, 'B')
        else: key = (pi, k, si)
        seq.append((t0, key, sl))
if ad_pi is not None and AD_PRE > 0:  # 광고 표지: 무음 0.8초 동안 '광고' 화면
    seq.insert(next(i for i, x in enumerate(seq) if x[0] >= ad_gaps[0][0] + AD_PRE - 1e-6), (ad_gaps[0][0], ('AG', 'in'), []))
if brand_at is not None:  # 인트로 구간: 0초 ~ 첫 장면(기본) 또는 훅 문단 끝 ~ 다음 문단 시작(밀린 시각)
    seq.insert(next(i for i, x in enumerate(seq) if x[0] >= brand_at + brand_sec - 1e-6), (brand_at, ('BR', 'intro'), []))
segs = []
for i, (t0, key, sl) in enumerate(seq):
    t1 = seq[i + 1][0] if i + 1 < len(seq) else tm['duration']
    if segs and segs[-1][1] == key: segs[-1][2] = t1
    else: segs.append([t0, key, t1, sl])

# 2) 고유 화면 렌더링
isanim = lambda k: not isad(k) and len(k) == 3 and k[2] == 'anim'
anim_info = {}  # key → (움직임 길이 초, 박자 초 목록, 틀)
MOTION = not os.environ.get('NO_MOTION') and deck.get('motion', True) is not False
motion_keys = set()  # 가벼운 움직임 프레임 목록을 쓰는 정지 슬라이드·전체 화면 안내
still = lambda f: f[-1] if isinstance(f, list) else f
async def render():
    files = {}
    if brand_at is not None: files[('BR', 'intro')] = brand_fr
    if ad_pi is not None and AD_PRE > 0: files[('AG', 'in')] = ad_bumper(os.path.join(wd, 'ad_bumper.png'))
    # 움직이는 장면은 먼저 모아 anim.render_many로 한꺼번에(코어 수만큼 브라우저, 정지 구간은 한 장) 찍는다
    jobs, keys = [], []
    for _, key, _, sl in segs:
        if isanim(key) and key not in keys:
            pi, k = key[:2]; spec = sl[k]['anim']
            t0 = min(a for a, kk, _, _ in segs if kk == key); dur = sum(bb - a for a, kk, bb, _ in segs if kk == key)
            tb = anim.beat_times(spec.get('data', {}), P[pi]['sents'], t0, P[pi]['start'])
            jobs.append({'tpl': spec['tpl'], 'data': spec.get('data', {}), 't': tb, 'dur': dur, 'outdir': os.path.join(wd, f'anim_p{pi+1:02d}_s{k}'), 'deck': deck, 't0': t0}); keys.append(key)
    if jobs:
        import time as _t; _s = _t.time()
        res = await anim.render_many(jobs)
        bad = [f"p{k[0]+1} s{k[1]} {j['tpl']}: " + ' / '.join(r[2][:4]) for k, j, r in zip(keys, jobs, res) if r[2]]
        if bad: sys.exit('ANIM_FAIL ' + ' | '.join(bad))
        for k, j, (fr, mv, _, _) in zip(keys, jobs, res):
            bl = j['t'].get('beats') or []
            files[k] = fr; anim_info[k] = (mv, [round(j['t0'] + x, 2) for x in bl if x is not None], j['tpl'])
        shot = sum(len(set(fr)) for fr, _, _, _ in res); tot = sum(len(fr) for fr, _, _, _ in res)
        print(f'움직이는 장면 {len(jobs)}개 · 프레임 {tot}(새로 찍음 {shot}) · 일꾼 {anim.WORKERS} · {_t.time() - _s:.0f}초', flush=True)
    # 정지 슬라이드: 가벼운 움직임(MOTION, 11-16 "최대한 애니메이션") — 슬라이드가 새로 뜨면 덩어리가 차례로 들어오고, 문장마다 새로 드러난 요소만 들어온다.
    # 0.3~0.8초 움직인 뒤 끝 상태(= 예전 정지 그림)로 남는다. 첫 장면(영상 0초, 0초 인트로면 인트로 직후)은 움직이지 않는다. 끄기: NO_MOTION=1 또는 deck "motion": false
    todo, prev = [], None
    for t0, key, _, sl in segs:
        if key in files or isad(key) or isbr(key) or isag(key):
            if isad(key) and key not in files: files[key] = {'app': midroll_app, 'shop': shop_img}.get(key[1]) or midroll
            prev = key; continue
        pi, k, si = key[:3]; first = prev is None or isad(prev) or isag(prev) or prev[:2] != (pi, k)
        if key not in [x[0] for x in todo]: todo.append((key, sl[k], first and t0 > cover_t + 0.01, MOTION and t0 > cover_t + 0.01))
        prev = key
    q = asyncio.Queue()
    for x in todo: q.put_nowait(x)
    async def worker(b):
        pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        await pg.goto('file://' + os.path.join(KIT, 'slide.html')); await pg.wait_for_timeout(300)
        while not q.empty():
            key, s, first, mo = q.get_nowait()
            pi, k, si = key[:3]; ban = len(key) == 4; d = dict(s)
            if d.get('bg'): d['bg'] = 'file://' + absp(d['bg'])
            if D[pi].get('kind') == 'ad': d['ad'] = True  # 광고 화면(admode)
            f = os.path.join(wd, f'p{pi+1:02d}_s{k}_{si}{"_b" if ban else ""}.png')
            await pg.evaluate('([a,b,c,e])=>render(a,b,c,e)', [{'ticker': deck['ticker'], 'name': deck['name'], 'banner': deck.get('banner')}, d, si, ban])
            await pg.wait_for_timeout(60)
            md = await pg.evaluate('([f,b])=>prep(f,b)', [first, ban]) if mo else 0
            if md > 0:
                fr = []
                for i in range(int(math.ceil(md * anim.FPS)) + 1):
                    await pg.evaluate('t=>motion(t)', i / anim.FPS); g = f[:-4] + f'_m{i:02d}.png'
                    await pg.screenshot(path=g); fr.append(g)
                files[key] = fr; motion_keys.add(key)
            else:
                await pg.screenshot(path=f); files[key] = f
        await pg.close()
    async with async_playwright() as p:
        if BRAND_END and any(isbr(k) and k[1] == 'end' for _, k, _, _ in segs):
            files[('BR', 'end')] = await brand.render_endcard(p, [c for _, c in promo], os.path.join(wd, 'brand_end'), gl_args=anim.GL_ARGS); motion_keys.add(('BR', 'end'))
        W = max(1, min(anim.WORKERS, 8, len(todo) or 1))
        brs = [await p.chromium.launch(args=anim.GL_ARGS) for _ in range(W)]
        await asyncio.gather(*[worker(b) for b in brs])
        for b in brs: await b.close()
    # 전체 화면 안내(미드롤·쿠팡 카드): 0.4초 동안 살짝 커지며 밝아진 뒤 끝 상태를 문장 끝까지 그대로(읽기 쉽게 정지 유지)
    if MOTION:
        for key in list(files):
            if isad(key) and isinstance(files[key], str):
                files[key] = ad_entrance(files[key], os.path.join(wd, f'ad_{key[1]}')); motion_keys.add(key)
    return files
def ad_bumper(path):
    # 광고 표지(2026-11-26): 본편 남색과 다른 초록 바탕, 가운데 큰 '광고' 배지 + 한 줄. 무음 0.8초 동안 보인다
    from PIL import ImageDraw, ImageFont
    FD = '/usr/share/fonts/opentype/noto/'
    f1 = ImageFont.truetype(FD + 'NotoSansCJK-Black.ttc', 150, index=1); f2 = ImageFont.truetype(FD + 'NotoSansCJK-Bold.ttc', 46, index=1)
    im = Image.new('RGB', (1920, 1080), (11, 45, 35)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1920, 16], fill=(61, 220, 151)); d.rectangle([0, 1064, 1920, 1080], fill=(61, 220, 151))
    t = '광고'; tw = d.textlength(t, font=f1); bw, bh = tw + 120, 230; x0, y0 = (1920 - bw) / 2, 330
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=36, fill=(61, 220, 151))
    d.text(((1920 - tw) / 2, y0 + 20), t, font=f1, fill=(6, 37, 26))
    # 11-27: 제목은 '광고' 배지 + 짧은 한 줄(18자 이하)만. '잠깐, 영양제 이야기' 같은 말 걸기 문구는 쓰지 않는다(구분은 화면·무음·알림음이 한다)
    sub = str(deck.get('ad_bumper_text') or '유료 광고 포함')
    if len(sub) > 18 or '잠깐' in sub: sub = '유료 광고 포함'
    d.text(((1920 - d.textlength(sub, font=f2)) / 2, y0 + bh + 60), sub, font=f2, fill=(212, 242, 228))
    im.save(path); return path
def ad_entrance(src, outdir, sec=0.4):
    os.makedirs(outdir, exist_ok=True)
    im = Image.open(src).convert('RGB').resize((1920, 1080)); n = int(sec * anim.FPS); fr = []
    for i in range(n + 1):
        x = 1 - (1 - i / n) ** 3; f = os.path.join(outdir, f'a{i:02d}.png')
        if i == n: im.save(f)
        else:
            sc = 0.94 + 0.06 * x; w, h = int(1920 * sc), int(1080 * sc)
            bg = Image.new('RGB', (1920, 1080), (11, 21, 36)); sm = im.resize((w, h), Image.BILINEAR)
            bg.paste(Image.blend(Image.new('RGB', (w, h), (11, 21, 36)), sm, 0.7 + 0.3 * x), ((1920 - w) // 2, (1080 - h) // 2)); bg.save(f)
        fr.append(f)
    return fr
files = asyncio.run(render())

# 3) 확인용 콘택트 시트 (고유 화면 전부, 시간순)
order = []
for _, key, _, _ in segs:
    fl = files[key]
    if key in motion_keys: fl = fl[-1]  # 가벼운 움직임은 끝 화면만 시트에
    for f in ([fl[i] for i in sorted({0, len(fl) // 4, len(fl) // 2, 3 * len(fl) // 4, len(fl) - 1})] if isinstance(fl, list) else [fl]):
        if f not in order: order.append(f)
cols = 6; tw, th = 320, 180; rows = math.ceil(len(order) / cols)
sheet = Image.new('RGB', (cols * tw, rows * th), '#000')
for i, f in enumerate(order): sheet.paste(Image.open(f).convert('RGB').resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
sheet.save(os.path.join(wd, 'contact.png'))

# 4) 합성: 화면 목록(길이 포함) + 보정한 음성
# 지침 A10: outro(마지막 문단)는 20초 이상이어야 엔드 스크린을 붙일 수 있다. 짧으면 마지막 화면을 늘린다
outro_t0 = P[-1]['start']; pad = max(0.0, 20.0 - (tm['duration'] - outro_t0))
if pad: segs[-1][2] += pad
total = tm['duration'] + pad
lst = os.path.join(wd, 'list.txt')
with open(lst, 'w') as fo:
    for t0, key, t1, _ in segs:
        fl = files[key]
        if isinstance(fl, list):  # 움직이는 장면: 프레임마다 1/30초(같은 그림이 이어지면 한 줄로 합침), 남는 시간은 마지막 프레임
            runs = []
            for f in fl[:-1]:
                if runs and runs[-1][0] == f: runs[-1][1] += 1
                else: runs.append([f, 1])
            for f, c in runs: fo.write(f"file '{f}'\nduration {c / anim.FPS:.6f}\n")
            fo.write(f"file '{fl[-1]}'\nduration {max(1 / anim.FPS, (t1 - t0) - (len(fl) - 1) / anim.FPS):.6f}\n")
        else: fo.write(f"file '{fl}'\nduration {t1 - t0:.3f}\n")
    fo.write(f"file '{still(files[segs[-1][1]])}'\n")
# 효과음 위치: 화면이 바뀌는 순간마다 종류를 정한다
def sfx_events():
    ev, last_t, prev = [], -99.0, None
    for t0, key, t1, sl in segs:
        if isbr(key):  # 인트로 = 소리 로고(2.4초, 나레이션 없음), 엔드카드 = 예전 outro처럼 종소리
            ev.append((t0, 'logo' if key[1] == 'intro' else 'chime')); last_t = t0 + (brand_sec if key[1] == 'intro' else 0)
            prev = key; continue
        if isag(key):  # 광고 표지: 짧은 두 음 알림(본편 효과음과 다른 소리)
            ev.append((t0, 'adin')); last_t = t0; prev = key; continue
        if isad(key):
            if prev is None or not (isad(prev) or isag(prev)): ev.append((t0, 'chime'))
            prev = key; continue
        if ad_kind and abs(t0 - ad_kind[1]) < 0.01:  # 광고 끝 무음 뒤 본편 복귀: 전환음을 반드시
            ev.append((t0, 'whoosh')); last_t = t0; prev = key; continue
        pi, k, si = key[:3]; d = sl[k]
        new_slide = prev is None or isad(prev) or isag(prev) or prev[:2] != (pi, k)
        after_intro = cover_t > 0 and abs(t0 - cover_t) < 0.01  # 0초 인트로 직후 첫 장면: 예전 0초처럼 boom, 상승음 없음(소리 로고와 겹침)
        if isanim(key):  # 장면 시작은 화면 전환 소리, 박자(사건 점·숫자)마다 딸깍
            kind = d.get('sfx', 'boom' if d['anim']['tpl'] == 'chalk_hook' or after_intro else 'whoosh')
            if kind != 'none': ev.append((t0, kind)); last_t = t0
            for bt in anim_info[key][1]:
                if bt - last_t >= 1.2 and bt < t1: ev.append((bt, 'tick')); last_t = bt
            prev = key; continue
        kind = None
        if new_slide:
            kick = str(d.get('kicker', ''))
            if after_intro: kind = 'boom'
            elif d.get('layout') == 'hero': ev.append((t0, 'riser')); kind = 'boom'
            elif d.get('layout') in ('outro', 'poll'): kind = 'chime'
            elif kick.startswith(('미스터리', '단서', '반전')) or (d.get('layout') == 'quote' and kick): kind = 'boom'
            else: kind = 'whoosh'
            if 'sfx' in d: kind = None if d['sfx'] == 'none' else d['sfx']
        elif d.get('layout') == 'stat' and any(x.get('at') == si for x in d.get('stats', [])):
            kind = 'tick'
        if kind and (kind != 'whoosh' or t0 - last_t >= 2.5) and (kind != 'tick' or t0 - last_t >= 1.5):
            ev.append((t0, kind)); last_t = t0
        prev = key
    if ev and ev[0][1] not in ('boom', 'logo'): ev.insert(0, (0.05, 'boom'))  # 0초 인트로면 소리 로고가 첫 소리
    return ev
# 4.5) 쿠팡 짧은 띠(운영자 지시 2026-11-11 "짧게 여러번", 11-22 UX 한도로 축소): deck 'shop_strip' = 띠 문구(28자 이하). 영상 1/3·2/3 지점 근처에 6초씩 0~2번,
# 화면 아래(자막·재생바 위, y 860~944)에 얇은 띠를 겹친다. 첫 30초(훅)·브랜드 스팅·outro(엔드카드)를 피하고, 광고(사이트 안내·카드·중간광고 문단)와는 앞뒤 60초를 띄운다
STRIP_SEC = 6.0
STRIP_LAST = 120.0  # 11-27: 띠는 영상 마지막 2분 안(outro 앞)에만
RISK_KICK = ('위험', '리스크', '악재')
def risk_windows():
    out = []
    for pi, pd in enumerate(D):
        if pd.get('tone') in ('risk', 'negative') or any(any(w in str(x.get('kicker', '')) for w in RISK_KICK) for x in pd.get('slides', [])):
            out.append((P[pi]['start'] - 1.0, P[pi]['end'] + 1.0))
    return out
# 4.4) 구독 버튼 띠(운영자 지시 2026-11-17 "1 3만 수행" — 구독 전환 시험): 문단 'sub' = [문장 번호] 한 문장 동안 화면 아래(y 860)에 '구독' 띠.
# 문구는 deck 'sub_text'(없으면 기본). 쿠팡 띠는 이 구간을 피한다. check_slides.py SUB가 영상 전체 1문장·'구독'이 들어간 문장인지 본다
sub_win = [(round(P[pi]['sents'][k]['start'], 2), round(P[pi]['sents'][k]['end'] + 0.6, 2)) for pi, pd in enumerate(D) for k in pd.get('sub', []) if k < len(P[pi]['sents'])]
# 4.6) 이어 보기 띠(운영자 지시 2026-11-18 "종목 간 교차 링크 필수"): 문단 'next' = [문장 번호] 그 문장 동안 '이어 보기' 띠.
# 문구는 deck 'next_text'(예: '실스크(LAES) 편 · 설명란 링크'). 구독 띠와 겹치면 안 된다(check_slides NEXTSUB)
next_win = [(round(P[pi]['sents'][k]['start'], 2), round(P[pi]['sents'][k]['end'] + 0.6, 2)) for pi, pd in enumerate(D) for k in pd.get('next', []) if k < len(P[pi]['sents'])]
AD_GAP = 60.0   # 광고 사이 최소 간격(초) — 미디어 tools/ad_gap_check.py 규칙 3과 같은 값
def strip_windows():
    # 2026-11-22 "광고 꽉꽉" UX 한도(미디어 review/ads_max_slidekit_todo.md): 띠는 다른 광고와 60초 이상 떨어뜨리고,
    # 광고 화면 합계 상한 = min(영상 길이 12%, 75초). 자리가 없으면 띠를 뺀다(0~2개). '카드 직전' 띠는 없앴다(카드가 중간광고 문단 안이라 광고가 붙음)
    if not deck.get('shop_strip'): return []
    # 광고 구간: 사이트 안내(전체·배너)·카드 + 영양제 중간광고 문단 전체(문단 'shop'이 있는 문단)
    adw = [(a, b) for a, k, b, _ in segs if isad(k) or len(k) == 4]
    for pi, pd in enumerate(D):
        if pd.get('shop'):
            adw.append((P[pi]['start'], P[pi]['sents'][-1]['end']))
    if ad_kind: adw.append(ad_kind)
    busy = [(a - AD_GAP, b + AD_GAP) for a, b in adw] \
         + [(a, b) for a, k, b, _ in segs if isanim(k)] \
         + [(a - 2.0, b + 2.0) for a, k, b, _ in segs if isbr(k)] \
         + [(0, 30.0), (outro_t0, total)] + sub_win + next_win  # 움직이는 장면·브랜드 스팅·엔드카드(outro)·구독/이어 보기 띠 위에도 얹지 않는다
    free = lambda t: all(t + STRIP_SEC <= a - 0.5 or t >= b + 0.5 for a, b in busy)
    cuts = sorted({round(a, 2) for a, _, _, _ in segs})
    # 11-27: 띠는 마지막 2분(health_midroll 9절 1번)에만, 한 번. 예전 1/3·2/3 목표가 11:22 영상 08:06(위험 이야기 근처)에 띠를 띄웠다.
    #   위험·나쁜 소식 문단(문단 "tone": "risk"|"negative" 또는 슬라이드 kicker '위험·리스크·악재') 위에는 얹지 않는다
    lo = max(30.0, total - STRIP_LAST)
    busy += risk_windows()
    targets = [lo + 0.5]
    union = []  # 겹치는 광고(중간광고 문단 안의 카드 등)는 한 번만 센다 — ad_gap_check.py 합계와 같은 방식
    for a, b in sorted(adw):
        if union and a <= union[-1][1] + 0.5: union[-1][1] = max(union[-1][1], b)
        else: union.append([a, b])
    cap = min(total * 0.12, 75.0) - sum(b - a for a, b in union)   # 광고 화면 합계 상한에서 남은 초
    wins = []
    for tg in targets:
        if cap < STRIP_SEC: break
        cand = [c for c in cuts if lo <= c <= outro_t0 - STRIP_SEC] + [tg]
        cand.sort(key=lambda c: abs(c - tg) + (0 if c in cuts else 8))  # 슬라이드 전환 지점 우선
        for c in cand:
            if c >= lo and free(c) and all(abs(c - w) >= AD_GAP + STRIP_SEC for w in wins):
                wins.append(round(c, 2)); cap -= STRIP_SEC; break
    return sorted(wins)
def make_strip(text, path):
    from PIL import ImageDraw, ImageFont
    S = 2; FD = '/usr/share/fonts/opentype/noto/'
    f1 = ImageFont.truetype(FD + 'NotoSansCJK-Black.ttc', 34 * S, index=1); f2 = ImageFont.truetype(FD + 'NotoSansCJK-Bold.ttc', 36 * S, index=1)
    im = Image.new('RGBA', (1920 * S, 84 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    # 2026-11-26 광고 구분: 띠 꼬리표는 '광고', 본편 금색과 다른 초록 칩·초록 바탕(본편 화면과 한눈에 갈림)
    tag = '광고'; tw = d.textlength(tag, font=f1); bw = d.textlength(text, font=f2)
    w = int(24 * S + tw + 28 * S + bw + 36 * S); x0 = (1920 * S - w) // 2
    d.rounded_rectangle([x0, 0, x0 + w, 84 * S], radius=42 * S, fill=(11, 45, 35, 240), outline=(61, 220, 151, 255), width=3 * S)
    d.rounded_rectangle([x0 + 12 * S, 12 * S, x0 + 12 * S + tw + 28 * S, 72 * S], radius=30 * S, fill=(61, 220, 151, 255))
    d.text((x0 + 26 * S, 14 * S), tag, font=f1, fill=(6, 37, 26, 255))
    d.text((x0 + 12 * S + tw + 44 * S, 13 * S), text, font=f2, fill=(255, 255, 255, 255))
    im.resize((1920, 84), Image.LANCZOS).save(path)
def make_sub(text, path):
    from PIL import ImageDraw, ImageFont
    S = 2; FD = '/usr/share/fonts/opentype/noto/'
    f1 = ImageFont.truetype(FD + 'NotoSansCJK-Black.ttc', 36 * S, index=1); f2 = ImageFont.truetype(FD + 'NotoSansCJK-Bold.ttc', 34 * S, index=1)
    im = Image.new('RGBA', (1920 * S, 84 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    tag = '구독'; tw = d.textlength(tag, font=f1); bw = d.textlength(text, font=f2)
    w = int(12 * S + 34 * S + tw + 30 * S + 22 * S + bw + 36 * S); x0 = (1920 * S - w) // 2
    d.rounded_rectangle([x0, 0, x0 + w, 84 * S], radius=42 * S, fill=(255, 255, 255, 240))
    bx1 = x0 + 12 * S + 34 * S + tw + 30 * S
    d.rounded_rectangle([x0 + 12 * S, 12 * S, bx1, 72 * S], radius=30 * S, fill=(204, 0, 0, 255))
    d.polygon([(x0 + 30 * S, 28 * S), (x0 + 30 * S, 56 * S), (x0 + 52 * S, 42 * S)], fill=(255, 255, 255, 255))  # 재생 삼각형
    d.text((x0 + 60 * S, 13 * S), tag, font=f1, fill=(255, 255, 255, 255))
    d.text((bx1 + 22 * S, 14 * S), text, font=f2, fill=(15, 15, 15, 255))
    im.resize((1920, 84), Image.LANCZOS).save(path)
def make_next(text, path):
    from PIL import ImageDraw, ImageFont
    S = 2; FD = '/usr/share/fonts/opentype/noto/'
    f1 = ImageFont.truetype(FD + 'NotoSansCJK-Black.ttc', 34 * S, index=1); f2 = ImageFont.truetype(FD + 'NotoSansCJK-Bold.ttc', 34 * S, index=1)
    im = Image.new('RGBA', (1920 * S, 84 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    tag = '이어 보기'; tw = d.textlength(tag, font=f1); bw = d.textlength(text, font=f2)
    w = int(24 * S + tw + 28 * S + bw + 36 * S); x0 = (1920 * S - w) // 2
    d.rounded_rectangle([x0, 0, x0 + w, 84 * S], radius=42 * S, fill=(12, 20, 38, 238), outline=(94, 200, 255, 255), width=3 * S)
    d.rounded_rectangle([x0 + 12 * S, 12 * S, x0 + 12 * S + tw + 28 * S, 72 * S], radius=30 * S, fill=(94, 200, 255, 255))
    d.text((x0 + 26 * S, 14 * S), tag, font=f1, fill=(12, 20, 38, 255))
    d.text((x0 + 12 * S + tw + 44 * S, 14 * S), text, font=f2, fill=(255, 255, 255, 255))
    im.resize((1920, 84), Image.LANCZOS).save(path)
strip_at = strip_windows(); strip_png = os.path.join(wd, 'shop_strip.png')
if strip_at: make_strip(deck['shop_strip'], strip_png)
sub_png = os.path.join(wd, 'sub_strip.png')
if sub_win: make_sub(str(deck.get('sub_text') or '주가가 이상하게 움직인 미국 종목을 추적합니다'), sub_png)
voice = os.path.join(wd, 'voice.wav'); mixed = os.path.join(wd, 'mix.wav')
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', raw, '-af',
    'highpass=f=60,equalizer=f=140:t=q:w=1:g=2,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=200,loudnorm=I=-16:TP=-1.5:LRA=11',
    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', voice], check=True)
if brand_at is not None or ad_gaps:  # 음성에도 인트로 길이만큼 빈칸(소리 로고 자리)·광고 앞뒤 무음 — 뒤 나레이션이 화면과 같이 밀린다
    import numpy as np
    va = sfx.read_wav(voice)
    for at_, sec_ in ([(brand_at, brand_sec)] if brand_at is not None else []) + ad_gaps:  # 앞에서부터(뒤 시각은 앞 빈칸이 들어간 뒤 기준)
        i0 = int(round(at_ * sfx.SR)); va = np.concatenate([va[:i0], np.zeros((int(round(sec_ * sfx.SR)), 2), np.float32), va[i0:]])
    sfx.write_wav(voice, va)
    json.dump(tm, open(os.path.join(wd, 'timing_video.json'), 'w'), ensure_ascii=False)
elif os.path.exists(os.path.join(wd, 'timing_video.json')): os.remove(os.path.join(wd, 'timing_video.json'))
events = [] if os.environ.get('NO_SFX') else sfx_events()
sfx.mix(voice, events, mixed, bed_on=not os.environ.get('NO_SFX'), duck=([(brand_at, brand_at + brand_sec)] if brand_at is not None else []) + [(a, a + s_) for a, s_ in ad_gaps] or None)  # 광고 앞뒤 무음 동안 배경 드론도 낮춘다(숨 고르기가 들리게)
# 화면 아래 띠(쿠팡·구독): 있는 것만 차례로 겹친다
layers = [(strip_png, [(t, t + STRIP_SEC) for t in strip_at])] if strip_at else []
if sub_win: layers.append((sub_png, sub_win))
next_png = os.path.join(wd, 'next_strip.png')
if next_win and deck.get('next_text'): make_next(str(deck['next_text']), next_png); layers.append((next_png, next_win))
if layers:
    fc, last = '[0:v]scale=1920:1080,fps=30[b0]', 'b0'
    for i, (_, wins) in enumerate(layers):
        en = '+'.join(f'between(t,{a:.2f},{b:.2f})' for a, b in wins)
        fc += f";[{i + 2}:v]format=rgba[s{i}];[{last}][s{i}]overlay=0:860:enable='{en}'[b{i + 1}]"; last = f'b{i + 1}'
    fc += f';[{last}]format=yuv420p[v]'
    ov = sum((['-i', pth] for pth, _ in layers), []) + ['-filter_complex', fc, '-map', '[v]', '-map', '1:a']
else: ov = ['-vf', 'scale=1920:1080,fps=30,format=yuv420p']
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-i', mixed] + ov + ['-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '20', '-r', '30',
    '-af', 'alimiter=limit=0.95,apad', '-t', f'{total:.3f}', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out], check=True)
ad = [(round(a, 1), round(b, 1)) for a, k, b, _ in segs if isad(k) and k[1] != 'shop']
shop_sec = round(sum(b - a for a, k, b, _ in segs if isad(k) and k[1] == 'shop'), 1)
# 지침 A4·A6 지표: 같은 그림이 이어지는 최장 시간(미드롤·outro 제외), 전체 화면 미드롤 합계, 배너 횟수
import hashlib
hv = {}
def hsh(f):
    if f not in hv: hv[f] = hashlib.md5(Image.open(f).convert('RGB').tobytes()).hexdigest()
    return hv[f]
static, run = [], None
for a, k, b, _ in segs:
    if isad(k) or isbr(k) or isag(k) or a >= outro_t0: run = None; continue
    if isanim(k):  # 움직이는 동안은 정지가 아니다. 움직임이 끝난 뒤 마지막 프레임 유지 구간만 센다
        h = hsh(still(files[k])); run = [min(b, a + anim_info[k][0]), b, h]; static.append(run); continue
    h = hsh(still(files[k]))
    if run and run[2] == h: run[1] = b
    else: run = [a, b, h]; static.append(run)
longest = max(static, key=lambda r: r[1] - r[0]) if static else [0, 0]
full_ad = round(sum(b - a for a, b in ad), 1); banners = len({k[0] for _, k, _, _ in segs if len(k) == 4})
json.dump({'segments': [[round(a, 2), str(k), round(b, 2)] for a, k, b, _ in segs], 'ad': ad, 'full_ad_sec': full_ad, 'banner_paras': banners, 'shop_sec': shop_sec, 'shop_strip_at': strip_at, 'strip_rule': 'last2', 'sub_at': sub_win, 'next_at': next_win,
           'longest_static': [round(longest[0], 1), round(longest[1], 1)],
           'anim': [[round(a, 2), round(min(b, a + anim_info[k][0]), 2), round(b, 2), anim_info[k][2], anim_info[k][1]] for a, k, b, _ in segs if isanim(k)], 'motion': len(motion_keys), 'brand_intro': [brand_at, round(brand_sec, 3)] if brand_at is not None else None, 'brand_end': [k for k, _ in promo] if BRAND_END else None, 'ad_gaps': [[round(a, 2), s] for a, s in ad_gaps], 'ad_kind': [round(ad_kind[0], 2), round(ad_kind[1], 2)] if ad_kind else None, 'outro_sec': round(total - outro_t0, 1), 'duration': round(total, 2), 'sfx': [[round(a, 2), k] for a, k in events]}, open(os.path.join(wd, 'segments.json'), 'w'), ensure_ascii=False)
from collections import Counter
print('saved', out, '| 화면', len(order), '| 구간', len(segs), '| 미드롤 전체화면', full_ad, '초', ad, '| 배너 문단', banners, '| 쿠팡 카드', shop_sec, '초', '| 쿠팡 띠', strip_at, '| 구독 띠', sub_win, '| 이어 보기 띠', next_win, '| 움직이는 장면', [f'{a:.0f}~{min(b, a + anim_info[k][0]):.0f}초 {anim_info[k][2]}' for a, k, b, _ in segs if isanim(k)],
      '| 가벼운 움직임 %d화면' % len(motion_keys), '| 브랜드 인트로 %s' % (f'{brand_at:.1f}초 +{brand_sec:.1f}초' if brand_at is not None else '없음'), '| 엔드카드 %s' % ([k for k, _ in promo] if BRAND_END else '없음'), '| 최장 정지 %.1f초(%.0f~%.0f)' % (longest[1] - longest[0], longest[0], longest[1]), '| 광고 숨 고르기 %s' % (f'{ad_kind[0]:.1f}~{ad_kind[1]:.1f}초 무음 {[s for _, s in ad_gaps]}' if ad_kind else '없음'), '| outro %.1f초' % (total - outro_t0), '| 효과음', dict(Counter(k for _, k in events)))
