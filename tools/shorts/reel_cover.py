# 인스타·페이스북 릴스 표지(cover_ig.jpg, 1080×1920) — 2026-11-24 운영자 "다른 SNS 채널들도 비슷한 개선 적용"(대형 채널 디자인 학습)
# 쇼츠 0초 표지와 **같은 이름표·같은 큰 숫자**(K9 0초 표지 규칙: 아는 이름 + 160px 이상 숫자 하나)를 쓰되, 인스타 프로필 격자(3:4, 세로 240~1680)와
# 피드 미리보기에서 잘리지 않게 다시 배치한다. 0초 프레임은 애니메이션 시작 화면이라 핵심 영역 아래 절반(약 y 680~1080)이 비고
# 위쪽 브랜드 줄(y 230)은 격자에서 잘렸다(11-23 LAES·IREN 표지). 표지는 영상이 아니라 그림이므로 그 빈 칸을 두 번째 장면의 비교 막대로 채운다.
# 사용: python3 reel_cover.py shorts.json 출력.jpg [--grid 격자미리보기.jpg]
#   shorts.json 첫 장면 anim.data(label·big·big_sub·tone) 또는 els의 첫 num 요소를 읽는다. 둘째 장면이 v_bars면 막대 3개까지 그린다.
# 규칙: 모든 글자 40px 이상, 큰 숫자 260px 이상, 글자·막대는 3:4 안전 영역(y 270~1650, x 60~1020) 안, 한 화면 강조색 하나(큰 숫자 색).
#   표지 문구는 0초 프레임과 같다(새 숫자를 지어내지 않는다). 브랜드: slidekit/brand(남색 #0B1524·금색 #F5B83D·워드마크 '김박사 월드').
import json, os, re, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920
SAFE = (60, 270, 1020, 1650)          # 3:4 격자(1080×1440, 세로 240~1680) 안쪽 여백 30px
BG, GOLD, INK, SUB, MUTE, LINE = (17, 31, 54), (245, 184, 61), (230, 237, 245), (201, 214, 230), (143, 163, 188), (34, 56, 90)
TONE = {'gold': GOLD, 'yellow': GOLD, 'red': (255, 92, 92), 'green': (57, 217, 138), 'white': INK, 'blue': (79, 163, 255)}
FB = '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
FBD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'


def font(p, s):
    return ImageFont.truetype(p, int(s), index=1)


def fit(d, text, path, size, maxw, minsize):
    while size > minsize and d.textlength(text, font=font(path, size)) > maxw:
        size -= 4
    return font(path, size), size


def first_scene(spec):
    sc = (spec.get('scenes') or [{}])[0]
    an = (sc.get('anim') or {}).get('data') or {}
    if an.get('big'):
        return str(an.get('label') or ''), str(an['big']), str(an.get('big_sub') or ''), str(an.get('tone') or '')
    els = sc.get('els') or []
    for e in els:  # num 요소, 또는 160px 이상 text(옛 회차 '기조연설' 같은 큰 글자)
        if e.get('text') and (e.get('kind') == 'num' or (e.get('kind') == 'text' and (e.get('size') or 0) >= 160)):
            lab = next((x.get('text') for x in els if x is not e and x.get('kind') == 'text' and (x.get('at') or 0) == 0), '')
            return str(lab or spec.get('name') or ''), str(e['text']), str(e.get('sub') or ''), str(e.get('color') or '')
    raise SystemExit('REELCOVER_FAIL 첫 장면에 큰 숫자(anim.data.big 또는 num 요소)가 없음')


def bars_of(spec):
    for sc in (spec.get('scenes') or [])[1:3]:
        an = sc.get('anim') or {}
        if an.get('tpl') == 'v_bars':
            d = an.get('data') or {}
            its = [i for i in d.get('items') or [] if isinstance(i.get('value'), (int, float))][:3]
            if len(its) >= 2:
                return str(d.get('label') or ''), its, str(d.get('unit') or ''), int(d.get('decimals', 1))
    return None


def tone_of(big, tone):
    # 디자인 학습 T2(review/design_study.md): 글자색은 흰색 + 강조 하나, 숫자만 방향색(상승 초록·하락 빨강·그 밖 금색)
    b = big.strip()
    if b.startswith(('-', '−')): return TONE['red']
    if b.startswith('+'): return TONE['green']
    return TONE.get(tone, GOLD) if tone in ('red', 'green') else GOLD


def draw_cover(spec):
    img = Image.new('RGB', (W, H), BG)
    glow = Image.new('RGB', (W, H), BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((60, 480, 1020, 1200), fill=(52, 74, 112))   # 주인공(큰 숫자) 뒤 조명 — 디자인 학습 T4 '밝은 남색 + 주인공 뒤 조명'
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 0.9)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = SAFE
    tk = str(spec.get('ticker') or '')
    label, big, big_sub, tone = first_scene(spec)
    col = tone_of(big, tone)
    # 1) 위쪽 줄(격자 안 y 290): 왼쪽 티커 이름표, 오른쪽 '● 김박사 월드'(디자인 학습 T7 — 브랜드는 작게, 늘 같은 자리, 금색)
    if tk:
        cf = font(FBD, 44)
        tw = d.textlength(tk, font=cf)
        d.rounded_rectangle((x0, 286, x0 + tw + 48, 356), 35, fill=(30, 50, 82))
        d.text((x0 + 24, 293), tk, font=cf, fill=INK)
    wf = font(FB, 42)
    wm = '김박사 월드'
    ww = d.textlength(wm, font=wf)
    d.ellipse((x1 - ww - 40, 307, x1 - ww - 14, 333), fill=GOLD)
    d.text((x1 - ww, 294), wm, font=wf, fill=GOLD)
    # 2) 이름 + 질문(0초 표지 label '이름 · 질문'을 두 줄로, 줄마다 크게)
    parts = [p.strip() for p in re.split(r'\s*·\s*', label, maxsplit=1) if p.strip()] or [str(spec.get('name') or tk)]
    y = 430
    for i, p in enumerate(parts[:2]):
        f, s = fit(d, p, FB, 112 if i == 0 else 96, x1 - x0, 64)
        d.text(((W - d.textlength(p, font=f)) / 2, y), p, font=f, fill=INK)
        y += int(s * 1.25)
    # 3) 큰 숫자(0초 표지와 같은 값, 260px 이상)
    bf, bs = fit(d, big, FB, 280, x1 - x0 - 40, 260)
    l, t, r, b = d.textbbox((0, 0), big, font=bf)
    by = max(y + 60, 730)
    d.text(((W - (r - l)) / 2 - l, by - t), big, font=bf, fill=col)
    y = by + (b - t) + 40
    # 4) 기준 한 줄(big_sub) — 두 줄까지
    if big_sub:
        sf = font(FBD, 44)
        words, lines, cur = big_sub.split(' '), [], ''
        for w_ in words:
            nxt = (cur + ' ' + w_).strip()
            if d.textlength(nxt, font=sf) > (x1 - x0) and cur:
                lines.append(cur); cur = w_
            else:
                cur = nxt
        lines.append(cur)
        for ln in lines[:2]:
            d.text(((W - d.textlength(ln, font=sf)) / 2, y), ln, font=sf, fill=SUB)
            y += 60
    # 5) 둘째 장면 비교 막대(있으면) — 빈 아래 칸을 내용으로
    bb = bars_of(spec)
    if bb:
        blab, its, unit, dec = bb
        y = max(y + 50, 1150)
        lf, vf = font(FBD, 44), font(FB, 48)
        if blab:
            hf, _ = fit(d, blab, FBD, 42, x1 - x0, 40)
            d.text((x0, y), blab, font=hf, fill=MUTE); y += 70
        vmax = max(abs(i['value']) for i in its) or 1
        lw = max(d.textlength(str(i['label']), font=lf) for i in its) + 30
        for i in its:
            v = i['value']
            hi = i.get('hi')
            bw = int((x1 - x0 - lw - 210) * abs(v) / vmax)
            d.text((x0, y), str(i['label']), font=lf, fill=INK if hi else SUB)
            c = col if hi else LINE
            d.rounded_rectangle((x0 + lw, y + 10, x0 + lw + max(bw, 8), y + 56), 10, fill=c)
            txt = f"{v:+.{dec}f}{unit}" if unit == '%' else f"{v:.{dec}f}{unit}"
            d.text((x0 + lw + max(bw, 8) + 18, y + 2), txt, font=vf, fill=INK if hi else SUB)
            y += 92
    # 6) 고지(40px, 안전 영역 아래쪽)
    nf = font(FBD, 40)
    note = '교육용 분석 · 매수·매도 권유 아님'
    d.text(((W - d.textlength(note, font=nf)) / 2, 1580), note, font=nf, fill=MUTE)
    if y > 1560:
        raise SystemExit(f'REELCOVER_FAIL 내용이 고지 줄까지 내려옴(y={y}) — 막대 수를 줄인다')
    return img


def main(a):
    if len(a) < 2:
        sys.exit(__doc__ or 'python3 reel_cover.py shorts.json out.jpg [--grid g.jpg]')
    spec = json.load(open(a[0], encoding='utf-8'))
    img = draw_cover(spec)
    img.save(a[1], quality=92)
    if '--grid' in a:
        g = img.crop((0, 240, W, 1680)).resize((360, 480))
        g.save(a[a.index('--grid') + 1], quality=90)
    print('REELCOVER_OK', a[1])


if __name__ == '__main__':
    main(sys.argv[1:])
