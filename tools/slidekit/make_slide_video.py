# 음성 동기 슬라이드 영상: slides.json + TTS 시각표 → 문장 단위로 슬라이드가 바뀌고, 사이트 안내 문장 동안만 미드롤 이미지
# 사용: python3 make_slide_video.py slides.json raw.wav 출력.mp4   (효과음·배경 드론 끄기: NO_SFX=1)
#   효과음은 sfx.py가 코드로 합성한다. 화면 전환=whoosh, 훅·단서·반전·답=boom, 훅 질문 직전=riser, 미드롤·마무리=chime, 숫자 카드=tick
#   slides.json의 화면마다 "sfx": "boom|whoosh|riser|chime|tick|none"으로 직접 정할 수 있다
#   raw.wav 옆의 raw_timing.json(st_tts.py가 만든다)을 읽는다. 프레임과 확인용 contact.png는 출력 폴더의 slides_out/에 저장
import json, sys, os, asyncio, subprocess, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfx
from PIL import Image
from playwright.async_api import async_playwright
KIT = os.path.dirname(os.path.abspath(__file__))
spec_p, raw, out = [os.path.abspath(a) for a in sys.argv[1:4]]
deck = json.load(open(spec_p, encoding='utf-8')); base = os.path.dirname(spec_p)
tm = json.load(open(os.path.splitext(raw)[0] + '_timing.json', encoding='utf-8'))
P = tm['paras']; D = deck['paras']
assert len(P) == len(D), f'문단 수 불일치: 음성 {len(P)} / slides.json {len(D)}'
absp = lambda p: p if os.path.isabs(p) else os.path.join(base, p)
midroll = absp(deck['midroll'])
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
        t0 = 0.0 if (pi == 0 and si == 0) else (pt['start'] if si == 0 else s['start'])
        k = max(i for i, x in enumerate(sl) if x.get('from', 0) <= si) if any(x.get('from', 0) <= si for x in sl) else 0
        sdur = s['end'] - s['start']
        if si in ads and ad_style(pi) == 'full' and full_used + sdur <= 30.0: key = ('AD',); full_used += sdur
        elif si in ads: key = (pi, k, si, 'B')
        else: key = (pi, k, si)
        seq.append((t0, key, sl))
segs = []
for i, (t0, key, sl) in enumerate(seq):
    t1 = seq[i + 1][0] if i + 1 < len(seq) else tm['duration']
    if segs and segs[-1][1] == key: segs[-1][2] = t1
    else: segs.append([t0, key, t1, sl])

# 2) 고유 화면 렌더링
async def render():
    files = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        await pg.goto('file://' + os.path.join(KIT, 'slide.html')); await pg.wait_for_timeout(300)
        for _, key, _, sl in segs:
            if key in files: continue
            if key == ('AD',): files[key] = midroll; continue
            pi, k, si = key[:3]; ban = len(key) == 4; d = dict(sl[k])
            if d.get('bg'): d['bg'] = 'file://' + absp(d['bg'])
            f = os.path.join(wd, f'p{pi+1:02d}_s{k}_{si}{"_b" if ban else ""}.png')
            await pg.evaluate('([a,b,c,e])=>render(a,b,c,e)', [{'ticker': deck['ticker'], 'name': deck['name'], 'banner': deck.get('banner')}, d, si, ban])
            await pg.wait_for_timeout(60); await pg.screenshot(path=f); files[key] = f
        await b.close()
    return files
files = asyncio.run(render())

# 3) 확인용 콘택트 시트 (고유 화면 전부, 시간순)
order = []
for _, key, _, _ in segs:
    if files[key] not in order: order.append(files[key])
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
    for t0, key, t1, _ in segs: fo.write(f"file '{files[key]}'\nduration {t1 - t0:.3f}\n")
    fo.write(f"file '{files[segs[-1][1]]}'\n")
# 효과음 위치: 화면이 바뀌는 순간마다 종류를 정한다
def sfx_events():
    ev, last_t, prev = [], -99.0, None
    for t0, key, t1, sl in segs:
        if key == ('AD',):
            if prev != ('AD',): ev.append((t0, 'chime'))
            prev = key; continue
        pi, k, si = key[:3]; d = sl[k]
        new_slide = prev is None or prev == ('AD',) or prev[:2] != (pi, k)
        kind = None
        if new_slide:
            kick = str(d.get('kicker', ''))
            if d.get('layout') == 'hero': ev.append((t0, 'riser')); kind = 'boom'
            elif d.get('layout') in ('outro', 'poll'): kind = 'chime'
            elif kick.startswith(('미스터리', '단서', '반전')) or (d.get('layout') == 'quote' and kick): kind = 'boom'
            else: kind = 'whoosh'
            if 'sfx' in d: kind = None if d['sfx'] == 'none' else d['sfx']
        elif d.get('layout') == 'stat' and any(x.get('at') == si for x in d.get('stats', [])):
            kind = 'tick'
        if kind and (kind != 'whoosh' or t0 - last_t >= 2.5) and (kind != 'tick' or t0 - last_t >= 1.5):
            ev.append((t0, kind)); last_t = t0
        prev = key
    if ev and ev[0][1] != 'boom': ev.insert(0, (0.05, 'boom'))
    return ev
voice = os.path.join(wd, 'voice.wav'); mixed = os.path.join(wd, 'mix.wav')
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', raw, '-af',
    'highpass=f=60,equalizer=f=140:t=q:w=1:g=2,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=200,loudnorm=I=-16:TP=-1.5:LRA=11',
    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', voice], check=True)
events = [] if os.environ.get('NO_SFX') else sfx_events()
sfx.mix(voice, events, mixed, bed_on=not os.environ.get('NO_SFX'))
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-i', mixed,
    '-vf', 'scale=1920:1080,fps=30,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '20', '-r', '30',
    '-af', 'alimiter=limit=0.95,apad', '-t', f'{total:.3f}', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out], check=True)
ad = [(round(a, 1), round(b, 1)) for a, k, b, _ in segs if k == ('AD',)]
# 지침 A4·A6 지표: 같은 그림이 이어지는 최장 시간(미드롤·outro 제외), 전체 화면 미드롤 합계, 배너 횟수
import hashlib
hv = {}
def hsh(f):
    if f not in hv: hv[f] = hashlib.md5(Image.open(f).convert('RGB').tobytes()).hexdigest()
    return hv[f]
static, run = [], None
for a, k, b, _ in segs:
    if k == ('AD',) or a >= outro_t0: run = None; continue
    h = hsh(files[k])
    if run and run[2] == h: run[1] = b
    else: run = [a, b, h]; static.append(run)
longest = max(static, key=lambda r: r[1] - r[0]) if static else [0, 0]
full_ad = round(sum(b - a for a, b in ad), 1); banners = len({k[0] for _, k, _, _ in segs if len(k) == 4})
json.dump({'segments': [[round(a, 2), str(k), round(b, 2)] for a, k, b, _ in segs], 'ad': ad, 'full_ad_sec': full_ad, 'banner_paras': banners,
           'longest_static': [round(longest[0], 1), round(longest[1], 1)], 'outro_sec': round(total - outro_t0, 1), 'duration': round(total, 2), 'sfx': [[round(a, 2), k] for a, k in events]}, open(os.path.join(wd, 'segments.json'), 'w'), ensure_ascii=False)
from collections import Counter
print('saved', out, '| 화면', len(order), '| 구간', len(segs), '| 미드롤 전체화면', full_ad, '초', ad, '| 배너 문단', banners,
      '| 최장 정지 %.1f초(%.0f~%.0f)' % (longest[1] - longest[0], longest[0], longest[1]), '| outro %.1f초' % (total - outro_t0), '| 효과음', dict(Counter(k for _, k in events)))
