# 유튜브 미드롤 이미지(1920x1080) 생성: 사이트 무료 리포트로 보내는 안내 화면
# 사용: python3 make_assets.py spec.json 출력폴더
import json, sys, os
from PIL import Image, ImageDraw, ImageFont
spec = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
FD = "/usr/share/fonts/opentype/noto/"
FK, FB, FR = FD+"NotoSansCJK-Black.ttc", FD+"NotoSansCJK-Bold.ttc", FD+"NotoSansCJK-Regular.ttc"
NAVY, GOLD, BLUE, CARD, MUTE = "#0E1A2B","#F5B83D","#4FA3FF","#16253B","#7F93AD"
S = 2
def font(p, s): return ImageFont.truetype(p, int(s*S), index=1)
TK = spec["ticker"]; PTS = spec["price_points"]
def midroll(fn):
    W, H = 1920, 1080; img = Image.new("RGB", (W*S, H*S), NAVY); d = ImageDraw.Draw(img)
    T = lambda x, y, t, f, c: d.text((x*S, y*S), t, font=f, fill=c)
    T(110, 90, "김박사 월드 · %s 무료 리포트" % TK, font(FB, 38), GOLD)
    for i, line in enumerate(spec["headline"][:2]): T(110, 150+i*100, line, font(FK, 76), "#FFFFFF")
    x = 110; fo = font(FK, 44)
    for i, (_, p) in enumerate(PTS):
        c = ("{:,.0f}원".format(p) if spec.get("unit") == "krw" else "$%s" % ("%d" % p if float(p).is_integer() else "%.2f" % p if p >= 1 else ("%.4f" % p).rstrip("0"))); w = d.textlength(c, font=fo)/S; col = GOLD if i % 2 == 0 else BLUE
        d.rounded_rectangle([x*S, 375*S, (x+w+48)*S, 447*S], radius=14*S, outline=col, width=3*S); T(x+24, 381, c, fo, col); x += w+48
        if i < len(PTS)-1: T(x+14, 381, "→", fo, "#5E7391"); x += 70
    for i, card in enumerate(spec["teasers"][:3]):
        x0 = 110+i*585; d.rounded_rectangle([x0*S, 505*S, (x0+540)*S, 760*S], radius=24*S, fill=CARD)
        bf = font(FK, 60)
        while d.textlength(card["big"], font=bf) > 470*S: bf = font(FK, bf.size/S*0.9)
        T(x0+36, 525, card["big"], bf, GOLD)
        for j, line in enumerate(card["lines"][:2]): T(x0+36, 630+j*48, line, font(FB, 34), "#E6EDF5")
    d.rounded_rectangle([110*S, 815*S, 1810*S, 945*S], radius=24*S, fill=GOLD)
    T(150, 828, spec["cta_line"], font(FK, 44), NAVY)
    T(150, 885, "무료 리포트는 화면 아래 고정 댓글 링크  ·  drkimworld.com", font(FB, 34), NAVY)
    T(110, 990, "※ 과거 보도를 정리한 교육용 분석이며 특정 종목의 매수·매도 권유나 수익 보장이 아닙니다.", font(FR, 26), MUTE)
    img.resize((W, H), Image.LANCZOS).save(os.path.join(out, fn))
midroll("%s_youtube_midroll_1920x1080.png" % TK.lower())
print("done", out)
