# 롱폼 슬라이드로 만드는 세로 요약 쇼츠(1080×1920)
# 사용: python3 make_shorts.py shorts.json shorts_raw.wav 출력.mp4
#   shorts_raw.wav 옆의 shorts_raw_timing.json(st_tts.py가 만든다)을 읽는다. 나레이션 파일은 '한 줄 = 한 문장'으로 써서
#   줄마다 화면 하나(frames[i])가 대응한다.
# shorts.json 예:
#   {"ticker":"LHX","name":"L3해리스","hook":["첫 줄","둘째 줄"],"cta":"풀영상·무료 리포트 링크는 고정 댓글",
#    "frames":[{"img":"slides_out/p01_s0_1.png","cap":"화면 자막(숫자 표기)"}, ...]}
#   img는 롱폼 합성 때 나온 slides_out/ 의 슬라이드 PNG(1920×1080). 상대 경로는 shorts.json 기준
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'slidekit'))
import sfx  # 롱폼과 같은 배경 드론·효과음
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
NAVY, GOLD, WHITE, SUB = (14, 26, 43), (245, 184, 61), (255, 255, 255), (201, 214, 230)
FB = '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
FBD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'


def font(path, size):
    return ImageFont.truetype(path, size, index=1)  # ttc의 1번이 한국어


def fit(draw, text, path, size, maxw):
    while size > 30:
        f = font(path, size)
        if draw.textlength(text, font=f) <= maxw:
            return f
        size -= 4
    return font(path, size)


def wrap(draw, text, f, maxw):
    lines, cur = [], ''
    for w in text.split(' '):
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=f) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def frame(spec, fr, base, out):
    im = Image.new('RGB', (W, H), NAVY)
    d = ImageDraw.Draw(im)
    for y in range(H):  # 위아래로 아주 약한 그라데이션
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(14 - 6 * k), int(26 - 9 * k), int(43 - 14 * k)))
    tag = f"김박사 월드 · {spec['name']} {spec['ticker']}"
    ft = font(FBD, 40)
    d.text(((W - d.textlength(tag, font=ft)) / 2, 120), tag, font=ft, fill=GOLD)
    y = 200
    for i, line in enumerate(spec['hook'][:3]):
        f = fit(d, line, FB, 88, 1000)
        d.text(((W - d.textlength(line, font=f)) / 2, y), line, font=f, fill=WHITE if i == 0 else GOLD)
        y += int(f.size * 1.22)
    sl = Image.open(os.path.join(base, fr['img'])).convert('RGB').resize((W, 608), Image.LANCZOS)
    top = 600
    im.paste(sl, (0, top))
    d.rectangle([0, top - 4, W, top - 1], fill=GOLD)
    d.rectangle([0, top + 608, W, top + 611], fill=GOLD)
    fc = font(FB, 62)
    lines = wrap(d, fr.get('cap', ''), fc, 960)[:3]
    y = 1290
    for line in lines:
        d.text(((W - d.textlength(line, font=fc)) / 2, y), line, font=fc, fill=WHITE)
        y += 84
    cta = spec.get('cta', '풀영상·무료 리포트 링크는 고정 댓글')
    fca = fit(d, cta, FB, 52, 920)
    d.rounded_rectangle([60, 1600, W - 60, 1730], radius=28, fill=GOLD)
    d.text(((W - d.textlength(cta, font=fca)) / 2, 1665 - fca.size * 0.62), cta, font=fca, fill=NAVY)
    fd = font(FBD, 28)
    note = '과거 공시·보도를 정리한 교육용 분석 · 매수·매도 권유 아님'
    d.text(((W - d.textlength(note, font=fd)) / 2, 1790), note, font=fd, fill=SUB)
    im.save(out)


def main(spec_p, raw, out):
    spec_p, raw, out = map(os.path.abspath, (spec_p, raw, out))
    spec = json.load(open(spec_p, encoding='utf-8'))
    base = os.path.dirname(spec_p)
    tm = json.load(open(os.path.splitext(raw)[0] + '_timing.json', encoding='utf-8'))
    paras = tm['paras']
    frames = spec['frames']
    assert len(paras) == len(frames), f'줄 수 불일치: 음성 {len(paras)} / frames {len(frames)}'
    wd = os.path.join(os.path.dirname(out), 'shorts_out')
    os.makedirs(wd, exist_ok=True)
    starts = [0.0] + [p['start'] for p in paras[1:]]
    ends = starts[1:] + [tm['duration'] + 0.4]
    lst = []
    for i, fr in enumerate(frames):
        f = os.path.join(wd, f'f{i:02d}.png')
        frame(spec, fr, base, f)
        lst.append(f"file '{f}'\nduration {ends[i] - starts[i]:.3f}")
    lst.append(f"file '{os.path.join(wd, f'f{len(frames) - 1:02d}.png')}'")
    open(os.path.join(wd, 'list.txt'), 'w').write('\n'.join(lst) + '\n')
    voice, mixed = os.path.join(wd, 'voice.wav'), os.path.join(wd, 'mix.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-af',
                    'highpass=f=60,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=200,loudnorm=I=-14:TP=-1.5:LRA=11,apad=pad_dur=0.4',
                    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', voice], check=True)
    ev = [] if os.environ.get('NO_SFX') else [(0.05, 'boom')] + [(s, 'whoosh') for s in starts[1:]] + [(starts[-1], 'chime')]
    sfx.mix(voice, ev, mixed, bed_on=not os.environ.get('NO_SFX'))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', os.path.join(wd, 'list.txt'),
                    '-i', mixed, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '30',
                    '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', out], check=True)
    # 확인용 시트
    ims = [Image.open(os.path.join(wd, f'f{i:02d}.png')).resize((270, 480)) for i in range(len(frames))]
    cols = 6
    sheet = Image.new('RGB', (270 * cols, 480 * ((len(ims) + cols - 1) // cols)), NAVY)
    for i, x in enumerate(ims):
        sheet.paste(x, ((i % cols) * 270, (i // cols) * 480))
    sheet.save(os.path.join(wd, 'contact.png'))
    print(f'saved {out} | 화면 {len(frames)} | 길이 {tm["duration"]:.1f}초')


if __name__ == '__main__':
    main(*sys.argv[1:4])
