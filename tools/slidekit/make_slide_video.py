# 음성 동기 슬라이드 영상: slides.json + TTS 시각표 → 문장 단위로 슬라이드가 바뀌고, 사이트 안내 문장 동안만 미드롤 이미지
# 사용: python3 make_slide_video.py slides.json raw.wav 출력.mp4
#   raw.wav 옆의 raw_timing.json(st_tts.py가 만든다)을 읽는다. 프레임과 확인용 contact.png는 출력 폴더의 slides_out/에 저장
import json, sys, os, asyncio, subprocess, math
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
seq = []  # (시작 시각, 키)
for pi, (pt, pd) in enumerate(zip(P, D)):
    ads = set(pd.get('ad', [])); sl = sorted(pd['slides'], key=lambda s: s.get('from', 0))
    for si, s in enumerate(pt['sents']):
        t0 = 0.0 if (pi == 0 and si == 0) else (pt['start'] if si == 0 else s['start'])
        if si in ads: key = ('AD',)
        else:
            k = max(i for i, x in enumerate(sl) if x.get('from', 0) <= si) if any(x.get('from', 0) <= si for x in sl) else 0
            key = (pi, k, si)
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
            pi, k, si = key; d = dict(sl[k])
            if d.get('bg'): d['bg'] = 'file://' + absp(d['bg'])
            f = os.path.join(wd, f'p{pi+1:02d}_s{k}_{si}.png')
            await pg.evaluate('([a,b,c])=>render(a,b,c)', [{'ticker': deck['ticker'], 'name': deck['name']}, d, si])
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
lst = os.path.join(wd, 'list.txt')
with open(lst, 'w') as fo:
    for t0, key, t1, _ in segs: fo.write(f"file '{files[key]}'\nduration {t1 - t0:.3f}\n")
    fo.write(f"file '{files[segs[-1][1]]}'\n")
aud = os.path.splitext(out)[0] + '_voice.m4a'
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', raw, '-af',
    'highpass=f=60,equalizer=f=140:t=q:w=1:g=2,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=200,loudnorm=I=-16:TP=-1.5:LRA=11',
    '-ar', '44100', '-ac', '2', '-c:a', 'aac', '-b:a', '192k', aud], check=True)
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-i', aud,
    '-vf', 'scale=1920:1080,fps=15,format=yuv420p', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '20',
    '-c:a', 'copy', '-shortest', '-movflags', '+faststart', out], check=True)
ad = [(round(a, 1), round(b, 1)) for a, k, b, _ in segs if k == ('AD',)]
json.dump({'segments': [[round(a, 2), str(k), round(b, 2)] for a, k, b, _ in segs], 'ad': ad}, open(os.path.join(wd, 'segments.json'), 'w'), ensure_ascii=False)
print('saved', out, '| 화면', len(order), '| 구간', len(segs), '| 미드롤 구간', ad)
