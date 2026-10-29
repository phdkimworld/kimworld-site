# 세로 전용 요약 쇼츠(1080×1920, 30fps) — 「김박사 월드 쇼츠 제작 개선 지침」(2026-10-14) 구현
# 사용: python3 make_shorts.py shorts.json shorts_raw.wav 출력.mp4
#   shorts_raw.wav 옆의 shorts_raw_timing.json(st_tts.py가 만든다)을 읽는다. 나레이션은 '한 줄 = 한 문장 = 한 장면'.
#   문장 사이 무음은 0.15초로 잘라 다시 붙이고(지침: 0.2초 이하), 첫 목소리는 0.05초, 마지막 단어 뒤 0.4초에 끝낸다.
# 화면 영역(세로 1920 기준): 0~154 비움 / 154~288 진행 바·단서 표시·채널 / 288~1056 핵심(장면 요소, 천천히 줌인)
#   / 1056~1250 자막(어절 단위, 한 줄 12자, 최대 2줄) / 1270 면책(처음 2초·마지막 3초만) / 1344~1920 비움(쇼츠 UI 자리).
#   오른쪽 15%(x>918)는 높이 45%(y>864) 아래에서 비운다. 모든 글자 40px 이상.
# shorts.json 예:
#  {"ticker":"LQDA","name":"리퀴디아","cta":"판결문 해석은 고정 댓글",
#   "scenes":[{"progress":"","title":"","em":"57","subtitle":"하루 -57%","els":[
#      {"kind":"chart","pts":[50,62,70,71,30],"draw":[0,0.35],"y":40,"h":420,"labels":{"-1":"$30"}},
#      {"kind":"num","text":"-57%","sub":"하루","at":0.35,"y":480,"color":"red","anim":"pop","sfx":"boom"},
#      {"kind":"doc","text":"판결문 한 장","at":0.75,"until":0.95}]}, ...]}
#  요소 공통: at(장면 안 시작 비율 0~1), until(사라지는 비율), y(핵심 영역 안 0~768), x(가운데 기준, 기본 540)
#  kind: chart(pts, draw[시작,끝], labels{인덱스:글}, level, level_label) / num(text, from, to, fmt, sub, size, color, anim pop|count|slide_l|slide_r)
#        text(text, size, color, anim, box) / stamp(text, color) / bars(vals, labels, values, draw) / doc(text) / q(text)
#        poll(q, opts[2~4개, 각 10자 이하], opt_at[비율들], foot, foot_at) — Threads 투표 같은 카드(운영자 지시 2026-10-16 '숏폼에도 마지막에 폴').
#          마지막 두 장면 안에 꼭 하나(없으면 렌더를 멈춘다). 정답 표시·비율·특정 보기 강조 금지(숨긴 답 규칙).
#  sfx: boom(드롭·히트) / tick(숫자). 영상 전체 3~5개만 쓴다(지침).
#  group: "A"|"B" 필수(실험 조). 첫 장면 at 0 요소는 애니메이션 없이 최종 크기(0초 프레임 = 표지, 독립 검토 2026-10-17).
import json, os, subprocess, sys, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'slidekit'))
import sfx
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
CORE_Y, CORE_H = 288, 768
SUB_Y, NOTE_Y = 1080, 1272
BG = (12, 20, 34)
COL = {'red': (255, 77, 77), 'green': (57, 217, 138), 'yellow': (245, 184, 61), 'white': (255, 255, 255), 'sub': (176, 190, 208)}
FB = '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
FBD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
_fc = {}


def font(path, size):
    k = (path, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, int(size), index=1)
    return _fc[k]


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def text_img(text, f, color, stroke=0):
    d = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=stroke)
    im = Image.new('RGBA', (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=f, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))
    return im


def fit_size(text, path, size, maxw):
    d = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    while size > 40 and d.textlength(text, font=font(path, size)) > maxw:
        size -= 4
    return max(size, 40)


def draw_el(core, el, p, dur):
    """p: 장면 진행 비율. 요소가 보이면 core(RGBA 1080×768)에 그린다."""
    at, until = el.get('at', 0.0), el.get('until', 9)
    if p < at or p >= until:
        return
    lt = (p - at) * dur  # 등장 뒤 지난 초
    k = el['kind']; cx = el.get('x', 540); y = el.get('y', 300)
    col = COL.get(el.get('color', 'white'), COL['white'])
    d = ImageDraw.Draw(core)
    if k == 'chart':
        pts = el['pts']; x0, x1 = el.get('x0', 110), el.get('x1', 900); h = el.get('h', 400)
        lo, hi = min(pts + [el.get('level', min(pts))]), max(pts)
        f0, f1 = el.get('draw', [at, at + 0.3])
        prog = ease((p - f0) / max(f1 - f0, 1e-3)) * (len(pts) - 1)
        xy = [(x0 + (x1 - x0) * i / (len(pts) - 1), y + h - (v - lo) / (hi - lo or 1) * h) for i, v in enumerate(pts)]
        peak = pts.index(hi)
        if 'level' in el and p >= f1:
            ly = y + h - (el['level'] - lo) / (hi - lo or 1) * h
            for xx in range(x0, x1, 36):
                d.line([(xx, ly), (xx + 18, ly)], fill=COL['yellow'], width=5)
            if el.get('level_label'):
                d.text((x0, ly - 62), el['level_label'], font=font(FBD, 48), fill=COL['yellow'])
        n = int(prog)
        for i in range(min(n, len(xy) - 1) + 1):
            if i >= len(xy) - 1:
                break
            a, b = xy[i], xy[i + 1]
            fr = 1.0 if i < n else prog - n
            if fr <= 0:
                break
            e = (a[0] + (b[0] - a[0]) * fr, a[1] + (b[1] - a[1]) * fr)
            d.line([a, e], fill=COL['green'] if i < peak else COL['red'], width=14, joint='curve')
        for key, lab in el.get('labels', {}).items():
            i = int(key) % len(pts)
            if prog >= i - 0.01:
                px, py = xy[i]; d.ellipse([px - 12, py - 12, px + 12, py + 12], fill=COL['white'])
                f = font(FB, 52); tw = d.textlength(lab, font=f)
                d.text((min(max(px - tw / 2, 20), 1060 - tw), py - 80 if py > y + 70 else py + 24), lab, font=f, fill=COL['white'])
    elif k in ('num', 'text'):
        if k == 'num' and 'from' in el:
            v = el['from'] + (el['to'] - el['from']) * ease(lt / 0.7)
            s = el.get('fmt', '{:.0f}').format(v)
        else:
            s = el['text']
        size = el.get('size', 190 if k == 'num' else 76)
        f = font(FB if k == 'num' else FBD, fit_size(s, FB if k == 'num' else FBD, size, el.get('maxw', 860)))
        im = text_img(s, f, col)
        anim = el.get('anim', 'pop'); sc, dx = 1.0, 0
        if anim == 'pop':
            sc = 0.7 + 0.3 * ease(lt / 0.22)
        elif anim == 'slide_l':
            dx = -700 * (1 - ease(lt / 0.3))
        elif anim == 'slide_r':
            dx = 700 * (1 - ease(lt / 0.3))
        if el.get('box'):
            bw, bh = int(im.width * sc) + 40, int(im.height * sc) + 24
            d.rounded_rectangle([cx + dx - bw / 2, y - 12, cx + dx + bw / 2, y - 12 + bh], radius=18, fill=(245, 184, 61, 70), outline=COL['yellow'], width=5)
        if sc != 1.0:
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
        core.alpha_composite(im, (int(cx + dx - im.width / 2), int(y)))
        if el.get('sub'):
            sf = font(FBD, 48); sim = text_img(el['sub'], sf, COL['sub'])
            core.alpha_composite(sim, (int(cx + dx - sim.width / 2), int(y + im.height + 6)))
    elif k == 'stamp':
        sc = 1.0 if el.get('anim') == 'none' else 1.0 + 0.8 * (1 - ease(lt / 0.18))
        f = font(FB, el.get('size', 120)); tim = text_img(el['text'], f, col)
        box = Image.new('RGBA', (tim.width + 60, tim.height + 40), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle([3, 3, box.width - 4, box.height - 4], radius=16, outline=col, width=10)
        box.alpha_composite(tim, (30, 20))
        box = box.rotate(-8, expand=True, resample=Image.BICUBIC)
        box = box.resize((int(box.width * sc), int(box.height * sc)), Image.BILINEAR)
        core.alpha_composite(box, (int(cx - box.width / 2), int(y - (box.height - box.height / sc) / 2)))
    elif k == 'bars':
        vals = el['vals']; n = len(vals); f0, f1 = el.get('draw', [at, at + 0.4])
        bw = 150; gap = (760 - n * bw) / max(n - 1, 1); h = el.get('h', 380); mx = max(vals)
        for i, v in enumerate(vals):
            g = ease(((p - f0) / max(f1 - f0, 1e-3)) * n - i)
            if g <= 0:
                continue
            x = 160 + i * (bw + gap); bh = h * v / mx * g
            c = COL.get(el.get('colors', ['green'] * n)[i], COL['green'])
            d.rounded_rectangle([x, y + h - bh, x + bw, y + h], radius=10, fill=c)
            lf = font(FBD, 42); lab = el['labels'][i]; d.text((x + bw / 2 - d.textlength(lab, font=lf) / 2, y + h + 12), lab, font=lf, fill=COL['sub'])
            if g > 0.9 and el.get('values'):
                vf = font(FB, 48); vs = el['values'][i]; d.text((x + bw / 2 - d.textlength(vs, font=vf) / 2, y + h - bh - 64), vs, font=vf, fill=COL['white'])
    elif k == 'doc':
        sc = 0.9 + 0.1 * ease(lt / 0.15); w, h = int(420 * sc), int(500 * sc)
        x, yy = cx - w / 2, y
        d.rounded_rectangle([x, yy, x + w, yy + h], radius=14, fill=(240, 243, 247))
        for i in range(7):
            ly = yy + 60 + i * 58; d.rectangle([x + 40, ly, x + w - 40 - (i % 3) * 50, ly + 18], fill=(150, 162, 178))
        d.rectangle([x + 34, yy + 60 + 3 * 58 - 8, x + w - 34, yy + 60 + 3 * 58 + 26], outline=COL['red'], width=6)
        if el.get('text'):
            f = font(FBD, 56); d.text((cx - d.textlength(el['text'], font=f) / 2, yy + h + 20), el['text'], font=f, fill=COL['white'])
    elif k == 'poll':  # 가운데 x 60~900(오른쪽 버튼 자리 피함), 핵심 영역 y 0~620
        x0, x1 = 60, 900
        d.rounded_rectangle([x0, y, x1, y + 590], radius=34, fill=(22, 37, 59, 245), outline=(34, 56, 90, 255), width=3)
        d.ellipse([x0 + 40, y + 42, x0 + 64, y + 66], fill=COL['yellow']); d.text((x0 + 80, y + 28), el.get('head', '투표'), font=font(FB, 44), fill=COL['yellow'])
        qf = font(FB, fit_size(el['q'], FB, 64, x1 - x0 - 80)); d.text((x0 + 40, y + 96), el['q'], font=qf, fill=COL['white'])
        ats = el.get('opt_at', [0.15 + 0.2 * i for i in range(len(el['opts']))]); nums = '①②③④'
        for i, o in enumerate(el['opts']):
            if p < ats[i]:
                continue
            g = ease((p - ats[i]) * dur / 0.2); oy = y + 190 + i * 104; ox = x0 + 40 - 40 * (1 - g)
            d.rounded_rectangle([ox, oy, x1 - 40, oy + 86], radius=43, fill=(52, 78, 116, 255), outline=(90, 120, 160, 255), width=4)
            d.text((ox + 30, oy + 6), nums[i], font=font(FB, 54), fill=COL['sub'])
            d.text((ox + 110, oy + 4), o, font=font(FB, fit_size(o, FB, 56, x1 - ox - 190)), fill=COL['white'])
        if p >= el.get('foot_at', 0.8):
            ff = font(FB, 46); ft = el.get('foot', '댓글에 번호 하나만'); d.text(((x0 + x1) / 2 - d.textlength(ft, font=ff) / 2, y + 515), ft, font=ff, fill=COL['yellow'])
    elif k == 'q':
        sc = 0.6 + 0.4 * ease(lt / 0.25)
        im = text_img('?', font(FB, 300), COL['yellow']); im = im.resize((int(im.width * sc), int(im.height * sc)))
        core.alpha_composite(im, (int(cx - im.width / 2), int(y)))


def chunks(text, maxc=12):
    """자막: 어절 단위로 한 줄 12자 이하, 두 줄씩 묶는다."""
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if len(t.replace(' ', '')) <= maxc or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return [lines[i:i + 2] for i in range(0, len(lines), 2)]


def sub_img(lines, em):
    d = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    size = min(fit_size(l, FB, 68, 820) for l in lines); f = font(FB, max(size, 64) if size >= 64 else size)
    im = Image.new('RGBA', (W, 200), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
    for li, line in enumerate(lines):  # 가운데 x=470: 오른쪽 15%(x>918) 버튼 자리를 피한다
        tw = d.textlength(line, font=f); x = 470 - tw / 2; yy = li * 92
        if em and em in line:  # 핵심 단어 하나만 노랑
            a, b = line.split(em, 1)
            for seg, c in ((a, COL['white']), (em, COL['yellow']), (b, COL['white'])):
                dd.text((x, yy), seg, font=f, fill=c, stroke_width=6, stroke_fill=(0, 0, 0)); x += d.textlength(seg, font=f)
        else:
            dd.text((x, yy), line, font=f, fill=COL['white'], stroke_width=6, stroke_fill=(0, 0, 0))
    return im


def read_wav(p):
    with wave.open(p) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    a = a.reshape(-1, ch).mean(1)
    return a, sr


def main(spec_p, raw, out):
    spec_p, raw, out = map(os.path.abspath, (spec_p, raw, out))
    spec = json.load(open(spec_p, encoding='utf-8'))
    tm = json.load(open(os.path.splitext(raw)[0] + '_timing.json', encoding='utf-8'))
    sents = [s for p in tm['paras'] for s in p['sents']]
    scenes = spec['scenes']
    assert spec.get('group') in ('A', 'B'), 'GROUP: shorts.json에 "group":"A"|"B"(그 회차 실험 조)를 적는다 — 독립 검토 2026-10-17'
    # 0초 프레임이 표지다(조회는 첫 프레임부터): 첫 장면에서 0초에 뜨는 요소는 확대·튀어나오기 없이 최종 크기로 그린다
    for el in scenes[0]['els']:
        if el.get('at', 0.0) == 0.0 and el['kind'] in ('num', 'text', 'stamp'):
            el['anim'] = 'none'
    assert len(sents) == len(scenes), f'문장 {len(sents)} / 장면 {len(scenes)} 수가 다르다(한 줄 = 한 문장 = 한 장면)'
    polls = [el for sc in scenes[-2:] for el in sc['els'] if el['kind'] == 'poll']
    assert polls, 'POLL: 마지막 두 장면 안에 poll 요소(Threads 같은 투표 카드)가 없다 — 운영자 지시 2026-10-16'
    for el in polls:
        assert 2 <= len(el['opts']) <= 4 and all(len(o) <= 10 for o in el['opts']), f"POLL 보기는 2~4개, 각 10자 이하: {el['opts']}"
    wd = os.path.join(os.path.dirname(out), 'shorts_out'); os.makedirs(wd, exist_ok=True)
    # 1) 음성: 문장만 잘라 0.15초 간격으로 다시 붙인다
    a, sr = read_wav(raw); GAP, LEAD, TAIL = 0.15, 0.05, 0.4  # 끝 0.4초 무음: 루프 문장 끝음절이 잘리지 않게(통합 제작·검수 지침 2026-10-29 4.3, 0.3~0.5초)
    parts, starts, t = [np.zeros(int(sr * LEAD))], [], LEAD
    for s in sents:
        seg = a[int(max(s['start'] - 0.02, 0) * sr):int((s['end'] + 0.05) * sr)]
        starts.append(t); parts.append(seg); t += len(seg) / sr
        parts.append(np.zeros(int(sr * GAP))); t += GAP
    total = t - GAP + TAIL; voice = np.concatenate(parts)[:int(total * sr)]
    voice = np.pad(voice, (0, max(0, int(total * sr) - len(voice))))
    vp = os.path.join(wd, 'voice.wav')
    with wave.open(vp, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(voice, -1, 1) * 32767).astype(np.int16).tobytes())
    norm = os.path.join(wd, 'voice_n.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', vp, '-af', 'highpass=f=60,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=200,loudnorm=I=-14:TP=-1.5:LRA=11',
                    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', norm], check=True)
    ends = starts[1:] + [total]
    # 2) 효과음(3~5개)과 배경음(-19dB)
    ev = []
    for i, sc in enumerate(scenes):
        for el in sc['els']:
            if el.get('sfx'):
                ev.append((starts[i] + el.get('at', 0) * (ends[i] - starts[i]), el['sfx']))
    assert len(ev) <= 5, f'효과음 {len(ev)}개 — 지침은 3~5개'
    mixed = os.path.join(wd, 'mix.wav')
    sfx.mix(norm, ev, mixed, bed_on=True, bed_db=-19)
    # 3) 자막 일정: 문장 길이에 비례해 어절 묶음을 나누고 0.1초 먼저 띄운다
    subs = []
    for i, s in enumerate(sents):
        # 화면 자막은 scenes[i].subtitle(아라비아 숫자·기호), 없으면 음성 대본(지침 4.1 tts_script/subtitle_text 이원화)
        grp = chunks(scenes[i].get('subtitle') or s['text']); L = sum(len(''.join(g).replace(' ', '')) for g in grp) or 1
        dur = s['end'] - s['start']; t0 = starts[i]
        for g in grp:
            d = dur * len(''.join(g).replace(' ', '')) / L
            subs.append((t0 - 0.1, t0 + d - 0.1, g, scenes[i].get('em'))); t0 += d
    # 4) 화면
    nf = int(total * FPS); bgimg = Image.new('RGBA', (W, H), BG + (255,))
    bd = ImageDraw.Draw(bgimg)
    for yy in range(H):
        k = yy / H; bd.line([(0, yy), (W, yy)], fill=(int(12 + 6 * (1 - k)), int(20 + 8 * (1 - k)), int(34 + 12 * (1 - k)), 255))
    tagf = font(FBD, 40); sub_cache = {}
    proc = subprocess.Popen(['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                             '-i', mixed, '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
                             '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    sheet = []
    for fi in range(nf):
        t = fi / FPS
        si = max(i for i in range(len(scenes)) if starts[i] - 0.05 <= t or i == 0)
        sc = scenes[si]; dur = ends[si] - starts[si]; p = (t - starts[si] + 0.05) / dur
        fr = bgimg.copy(); d = ImageDraw.Draw(fr)
        # 진행 바·단서·채널
        d.rounded_rectangle([60, 170, 1020, 180], radius=5, fill=(40, 54, 76, 255))
        d.rounded_rectangle([60, 170, 60 + 960 * t / total, 180], radius=5, fill=COL['yellow'] + (255,))
        if sc.get('progress'):
            d.text((60, 200), sc['progress'], font=tagf, fill=COL['yellow'])
        tag = f"김박사 월드 · {spec['ticker']}"; d.text((1020 - d.textlength(tag, font=tagf), 200), tag, font=tagf, fill=COL['sub'])
        # 핵심 영역(천천히 줌인 105→115%)
        core = Image.new('RGBA', (W, CORE_H), (0, 0, 0, 0))
        if sc.get('title'):
            ImageDraw.Draw(core).text((540 - ImageDraw.Draw(core).textlength(sc['title'], font=font(FBD, 76)) / 2, 10), sc['title'], font=font(FBD, 76), fill=COL['white'])
        for el in sc['els']:
            draw_el(core, el, p, dur)
        z = 1.0 + 0.05 * min(max(p, 0), 1)
        if z > 1.001:
            zc = core.resize((int(W * z), int(CORE_H * z)), Image.BILINEAR)
            core = zc.crop(((zc.width - W) // 2, (zc.height - CORE_H) // 2, (zc.width - W) // 2 + W, (zc.height - CORE_H) // 2 + CORE_H))
        fr.alpha_composite(core, (0, CORE_Y))
        # CTA: 마지막 3초, 높이 40~60%
        if t >= total - 3.0 and spec.get('cta'):
            cf = font(FB, fit_size(spec['cta'], FB, 72, 860)); ci = text_img(spec['cta'], cf, COL['yellow'], stroke=6)
            fr.alpha_composite(ci, (int(540 - ci.width / 2), 940))
        # 자막
        for (a0, a1, g, em) in subs:
            if a0 <= t < a1:
                key = (tuple(g), em)
                if key not in sub_cache:
                    sub_cache[key] = sub_img(g, em)
                fr.alpha_composite(sub_cache[key], (0, SUB_Y)); break
        # 면책: 처음 2초·마지막 3초
        if t < 2.0 or t >= total - 3.0:
            nf_ = font(FBD, 38); note = '교육용 분석 · 매수·매도 권유 아님'
            d2 = ImageDraw.Draw(fr); d2.text((540 - d2.textlength(note, font=nf_) / 2, NOTE_Y), note, font=nf_, fill=COL['sub'])
        rgb = fr.convert('RGB'); proc.stdin.write(rgb.tobytes())
        if fi % int(FPS * 2.5) == 0:
            sheet.append(rgb.resize((270, 480)))
    proc.stdin.close(); proc.wait()
    cols = 8; sh = Image.new('RGB', (270 * cols, 480 * ((len(sheet) + cols - 1) // cols)), BG)
    for i, x in enumerate(sheet):
        sh.paste(x, ((i % cols) * 270, (i // cols) * 480))
    sh.save(os.path.join(wd, 'contact.png'))
    print(f'saved {out} | 장면 {len(scenes)} | 길이 {total:.1f}초 | 효과음 {len(ev)} | 시트 2.5초 간격')


if __name__ == '__main__':
    main(*sys.argv[1:4])
