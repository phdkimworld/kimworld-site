# 회차별로 직접 디자인한 썸네일 HTML(1280x720, 글자 포함)을 PNG·JPG로 렌더링한다.
# 사용: python3 render_html.py design.html out.png [--fx]
#  --fx: 약한 필름 그레인과 비네트만 입힌다(디자인 자체는 건드리지 않음)
import asyncio, sys, os
from playwright.async_api import async_playwright
import numpy as np
from PIL import Image

async def shot(html, png):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await b.new_page(viewport={"width": 1280, "height": 720})
        await pg.goto("file://" + os.path.abspath(html)); await pg.wait_for_timeout(600)
        await pg.screenshot(path=png); await b.close()

def fx(png):
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float32)
    h, w = a.shape[:2]; y, x = np.mgrid[0:h, 0:w]
    r = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    a *= (1 - 0.22 * np.clip(r - 0.55, 0, 1))[..., None]
    a += np.random.default_rng(3).normal(0, 3.2, a.shape)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(png)

if __name__ == "__main__":
    html, out = sys.argv[1], sys.argv[2]
    asyncio.run(shot(html, out))
    if "--fx" in sys.argv: fx(out)
    Image.open(out).convert("RGB").save(os.path.splitext(out)[0] + ".jpg", quality=92)
    print("saved", out)
