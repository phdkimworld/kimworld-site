# 사이트 리포트용 대표 가격 차트 PNG (가로 1080, 흰 배경, 시간순 막대)
# 사용: python3 make_chart.py chart.json 출력.png
import json, sys
from PIL import Image, ImageDraw, ImageFont
c = json.load(open(sys.argv[1], encoding="utf-8"))
FD = "/usr/share/fonts/opentype/noto/"
def F(w, s): return ImageFont.truetype(FD + "NotoSansCJK-%s.ttc" % w, int(s * S), index=1)
S = 2; W = 1080; RH = 78; TOP = 150; L = 300; R = 140
rows = c["rows"]; ref = c.get("ref")
H = TOP + RH * len(rows) + (110 if ref else 70)
img = Image.new("RGB", (W * S, H * S), "#FFFFFF"); d = ImageDraw.Draw(img)
T = lambda x, y, t, f, col: d.text((x * S, y * S), t, font=f, fill=col)
y = 36
for line in c["title"][:2]: T(40, y, line, F("Bold", 34), "#0E1A2B"); y += 48
vmax = max(r[2] for r in rows + ([[0, 0, ref["v"]]] if ref else [])) * 1.05
bx = lambda v: L + (W - L - R) * v / vmax
for i, (dt, lab, v) in enumerate(rows):
    y0 = TOP + i * RH; last = i == len(rows) - 1
    T(40, y0 + 6, dt, F("Bold", 24), "#0E1A2B"); T(40, y0 + 38, lab, F("Regular", 22), "#5E6B7D")
    d.rounded_rectangle([L * S, (y0 + 14) * S, bx(v) * S, (y0 + 58) * S], radius=6 * S, fill="#E0A21B" if last else "#C9D1DB")
    txt = (("%.4f" % v).rstrip("0") if v < 1 else "%.2f" % v); f = F("Bold", 26); lx = bx(v) + 12
    if ref and v < ref["v"] and lx + d.textlength(txt, font=f) / S > bx(ref["v"]) - 6: lx = bx(ref["v"]) + 10
    T(lx, y0 + 18, txt, f, "#B07B0C" if last else "#0E1A2B")
if ref:
    x = bx(ref["v"]) * S; yb = TOP + RH * len(rows)
    for yy in range(TOP * S, yb * S, 16 * S): d.line([(x, yy), (x, yy + 8 * S)], fill="#4F7FB8", width=2 * S)
    T(bx(ref["v"]) - 8, yb + 6, ref["label"], F("Regular", 22), "#4F7FB8")
T(40, H - 44, c.get("note", ""), F("Regular", 20), "#7F8A99")
img.resize((W, H), Image.LANCZOS).save(sys.argv[2]); print("saved", sys.argv[2], W, H)
