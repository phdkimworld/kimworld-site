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
        c = ("{:,.0f}원".format(p) if spec.get("unit") == "krw" else "$%s" % ("%d" % p if float(p).is_integer() else ("%.3f" % p if round(p, 2) != round(p, 3) else "%.2f" % p) if p >= 1 else ("%.4f" % p).rstrip("0"))); w = d.textlength(c, font=fo)/S; col = GOLD if i % 2 == 0 else BLUE
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
# 운영자 지시 2026-10-21: 리포트 말고 김박사 월드 사이트와 설치 앱의 기능도 미드롤에서 알린다.
# 두 번째 이미지(<tk>_youtube_midroll_app_1920x1080.png)는 slides.json의 "midroll_app"으로 넣으면 마지막 전체 화면 안내(닫기)에 뜬다
def count_reports():
    import glob, re
    n = 0
    for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "content", "reports", "*.md")):
        head = open(f, encoding="utf-8").read(3000)
        if not re.search(r"^draft:\s*true", head, re.M): n += 1
    return n
def app_midroll(fn):
    W, H = 1920, 1080; img = Image.new("RGB", (W*S, H*S), NAVY); d = ImageDraw.Draw(img)
    T = lambda x, y, t, f, c: d.text((x*S, y*S), t, font=f, fill=c)
    nm = spec.get("name_ko", TK); n = spec.get("report_count") or count_reports()
    T(110, 80, "김박사 월드 · 웹사이트와 앱으로 더 편하게", font(FB, 38), GOLD)
    hl = "%s 새 리포트, 놓치지 말고 받아 보세요" % nm.split("(")[0]; hf = font(FK, 70)
    while d.textlength(hl, font=hf) > 1700*S: hf = font(FK, hf.size/S*0.92)
    T(110, 140, hl, hf, "#FFFFFF")
    T(110, 238, "무료 리포트 %d개 · 종목·테마별로 모아 보기" % n, font(FB, 40), "#C9D6E6")
    feats = spec.get("app_features") or [
        ("팔로우 알림", ["종목을 팔로우하면", "새 리포트를 푸시로 알려요"]),
        ("업데이트 요청", ["버튼 한 번으로 요청,", "요청 많은 종목은 제작에 반영"]),
        ("투자자 투표", ["불리시·베어리시 투표와", "종목 순위를 한눈에"]),
        ("커뮤니티", ["리포트마다 의견을 나누고", "다른 투자자를 팔로우"]),
    ]
    for i, (big, lines) in enumerate(feats[:4]):
        x0 = 110 + i*435; d.rounded_rectangle([x0*S, 320*S, (x0+400)*S, 640*S], radius=24*S, fill=CARD)
        d.ellipse([(x0+30)*S, 345*S, (x0+86)*S, 401*S], fill=GOLD); T(x0+46, 349, str(i+1), font(FK, 36), NAVY)
        bf = font(FK, 50)
        while d.textlength(big, font=bf) > 340*S: bf = font(FK, bf.size/S*0.9)
        T(x0+30, 420, big, bf, GOLD)
        for j, line in enumerate(lines[:2]): T(x0+30, 512+j*46, line, font(FB, 30), "#E6EDF5")
    d.rounded_rectangle([110*S, 700*S, 1810*S, 900*S], radius=24*S, fill=GOLD)
    T(150, 722, "drkimworld.com  →  홈 화면에 앱 설치(무료)", font(FK, 54), NAVY)
    T(150, 810, "설치하면 아이폰에서도 푸시 알림 · 링크는 고정 댓글과 설명란 첫 줄", font(FB, 36), NAVY)
    T(110, 980, "※ 과거 보도를 정리한 교육용 분석이며 특정 종목의 매수·매도 권유나 수익 보장이 아닙니다.", font(FR, 26), MUTE)
    img.resize((W, H), Image.LANCZOS).save(os.path.join(out, fn))
app_midroll("%s_youtube_midroll_app_1920x1080.png" % TK.lower())
print("done", out)
