# 유튜브 영상 속 쿠팡 상품 카드(1920x1080). 운영자 지시 2026-11-10: 영상 안 배너·설명란·고정댓글로 쿠팡 상품 안내, 카테고리별로 추적·최적화.
# 사용: python3 make_shop_card.py spec.json 출력.png
#   spec = {"ticker": "LAES", "cat_name": "투자서", "line": "영상 속 산업을 더 깊이 이해하고 싶다면",
#           "name": "<짧게 줄인 상품 이름 40자 이내>", "img": "<yt-shop 아티팩트의 img_0.jpg 경로>"}
#   가격은 넣지 않는다(쿠팡 가격이 바뀐다). 효능·수익 표현을 넣지 않는다. 쿠팡 파트너스 대가성 문구는 화면 맨 아래 고정.
import json, sys, os
from PIL import Image, ImageDraw, ImageFont, ImageOps
spec = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
base = os.path.dirname(os.path.abspath(sys.argv[1]))
FD = "/usr/share/fonts/opentype/noto/"
FK, FB, FR = FD + "NotoSansCJK-Black.ttc", FD + "NotoSansCJK-Bold.ttc", FD + "NotoSansCJK-Regular.ttc"
NAVY, GOLD, CARD, MUTE = "#0E1A2B", "#F5B83D", "#16253B", "#9FB0C6"
S = 2; W, H = 1920, 1080
font = lambda p, s: ImageFont.truetype(p, int(s * S), index=1)
img = Image.new("RGB", (W * S, H * S), NAVY); d = ImageDraw.Draw(img)
T = lambda x, y, t, f, c: d.text((x * S, y * S), t, font=f, fill=c)
def wrap(text, path, size, width, maxl, min_size=None):
    """낱말 단위 줄바꿈. 안 들어가면 글자를 줄이고, 최소 크기에서도 넘치면 마지막 줄을 …로 끝낸다."""
    min_size = min_size or size * 0.7
    while True:
        f = font(path, size); lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= width * S: cur = t
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        if len(lines) <= maxl and all(d.textlength(l, font=f) <= width * S for l in lines): return f, lines
        if size * 0.92 >= min_size: size *= 0.92; continue
        lines = lines[:maxl]
        while d.textlength(lines[-1] + "…", font=f) > width * S: lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
        return f, lines
# 상품 사진: 흰 카드 위에 비율 유지
pad = 40; box = (110, 150, 110 + 700, 150 + 700)
d.rounded_rectangle([box[0] * S, box[1] * S, box[2] * S, box[3] * S], radius=36 * S, fill="#FFFFFF")
p = spec.get("img")
if p:
    p = p if os.path.isabs(p) else os.path.join(base, p)
    ph = Image.open(p).convert("RGB")
    ph = ImageOps.contain(ph, ((700 - 2 * pad) * S, (700 - 2 * pad) * S), Image.LANCZOS)
    img.paste(ph, ((box[0] + (700 - ph.width // S) // 2) * S, (box[1] + (700 - ph.height // S) // 2) * S))
x0 = 880
T(x0, 150, "김박사 월드 · %s 영상과 함께" % spec["ticker"], font(FB, 36), GOLD)
lf, ls = wrap(spec.get("line", ""), FK, 58, 930, 2); y = 215
for ln in ls: T(x0, y, ln, lf, "#FFFFFF"); y += lf.size / S * 1.34
y += 20
d.rounded_rectangle([x0 * S, y * S, (x0 + 930) * S, (y + 300) * S], radius=26 * S, fill=CARD)
T(x0 + 36, y + 26, spec.get("cat_name", ""), font(FB, 32), MUTE)
nf, nl = wrap(spec["name"], FK, 50, 858, 3, 38)
for i, ln in enumerate(nl): T(x0 + 36, y + 80 + i * nf.size / S * 1.3, ln, nf, "#FFFFFF")
y += 340
d.rounded_rectangle([x0 * S, y * S, (x0 + 930) * S, (y + 120) * S], radius=24 * S, fill=GOLD)
T(x0 + 40, y + 14, "링크는 설명란과 고정 댓글에", font(FK, 46), NAVY)
T(x0 + 40, y + 70, "쿠팡에서 바로 보실 수 있습니다", font(FB, 30), NAVY)
T(110, 960, "이 영상은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.", font(FR, 30), MUTE)
T(110, 1004, "※ 상품 안내는 투자 내용과 무관한 광고입니다.", font(FR, 26), MUTE)
img.resize((W, H), Image.LANCZOS).save(out)
print("saved", out)
