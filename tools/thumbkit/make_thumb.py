# 유튜브 썸네일 1280x720: 배경 장면(생성 이미지 또는 코드 장면) + 시네마틱 후처리 + 제목·차트·가격표 합성
# 사용: python3 make_thumb.py spec.json 출력.png
import json, sys, os, asyncio, shutil
import numpy as np, cv2
from playwright.async_api import async_playwright
KIT = os.path.dirname(os.path.abspath(__file__))
spec = json.load(open(sys.argv[1], encoding="utf-8")); out = os.path.abspath(sys.argv[2])
work = os.path.dirname(os.path.abspath(sys.argv[1]))
W, H = 1280, 720

async def shot(html_path, png, init=None):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await b.new_page(viewport={"width": W, "height": H})
        if init: await pg.add_init_script(init)
        await pg.goto("file://" + html_path); await pg.wait_for_timeout(600)
        await pg.screenshot(path=png); await b.close()

def cover_crop(src, dst):
    im = cv2.imread(src); h, w = im.shape[:2]; s = max(W / w, H / h)
    im = cv2.resize(im, (int(w * s + .5), int(h * s + .5)), interpolation=cv2.INTER_LANCZOS4)
    y0 = (im.shape[0] - H) // 2; x0 = (im.shape[1] - W) // 2
    cv2.imwrite(dst, im[y0:y0 + H, x0:x0 + W])

def cinematic(src, dst, bloom=1.0, generated=False):
    im = cv2.imread(src).astype(np.float32) / 255
    if not generated or bloom > 0:
        lum = im.max(axis=2, keepdims=True); bright = im * np.clip((lum - .55) / .45, 0, 1)
        glow = sum(cv2.GaussianBlur(bright, (0, 0), s) * wgt for s, wgt in ((6, .6), (18, .5), (42, .45)))
        im = 1 - (1 - im) * (1 - np.clip(glow * bloom, 0, 1))          # screen 블렌드 블룸
    im = np.clip((im - .5) * 1.12 + .5, 0, 1)                            # 대비
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV); hsv[..., 1] = np.clip(hsv[..., 1] * 1.18, 0, 1); im = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)  # 채도
    yy, xx = np.mgrid[0:H, 0:W]; d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    im *= np.clip(1.15 - .45 * d ** 2, .35, 1)[..., None]                # 비네트
    im += np.random.default_rng(1).normal(0, .012, im.shape).astype(np.float32)  # 필름 그레인
    cv2.imwrite(dst, (np.clip(im, 0, 1) * 255).astype(np.uint8))

bg_raw = os.path.join(work, "bg_raw.png"); bg_fx = os.path.join(work, "bg_fx.png")
if spec.get("bg_image"):                    # 이미지 생성 도구나 사용자가 준 배경
    cover_crop(os.path.join(work, spec["bg_image"]), bg_raw); gen = True
else:                                        # 코드로 그린 장면
    asyncio.run(shot(os.path.join(work, spec["scene_html"]), bg_raw)); gen = False
cinematic(bg_raw, bg_fx, spec.get("bloom", 0.35 if gen else 1.0), gen)
ov = os.path.join(work, "_overlay.html"); shutil.copy(os.path.join(KIT, "overlay.html"), ov)
asyncio.run(shot(ov, out, "window.SPEC=" + json.dumps(spec, ensure_ascii=False) + ";"))
print("saved", out)
