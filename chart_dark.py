"""리포트 대표 차트(static/charts/*.png, 흰 배경)를 검은 화면에 맞는 투명 배경 차트로 바꾼다(빌드 때 dist에만, 원본은 그대로).

차트는 tools/charts/make_chart.py가 정해진 몇 가지 색(글자·막대·기준선)만 흰 바탕에 그린다. 그래서 픽셀마다
'어느 색을 얼마나 진하게 칠했나(알파)'를 거꾸로 구해, 같은 진하기로 어두운 화면용 색을 투명 바탕에 다시 칠한다.
CSS 색 반전(invert)과 달리 바탕이 회색 판으로 남지 않고, 강조색(마지막 막대 주황)도 그대로 살아 있다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# 밝은 차트 색 → 어두운 화면 색
INK = [
    ("#0E1A2B", "#F2F4F7"),  # 제목·날짜·숫자
    ("#5E6B7D", "#9AA5B4"),  # 설명 글자
    ("#C9D1DB", "#3B4554"),  # 막대
    ("#E0A21B", "#F0B23A"),  # 마지막 막대(지금)
    ("#B07B0C", "#F5BC4A"),  # 마지막 막대 숫자
    ("#4F7FB8", "#7FA8DE"),  # 기준선
    ("#7F8A99", "#8C96A5"),  # 아래 주석
]


def _rgb(h: str):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def to_dark(src: Path, dst: Path) -> bool:
    import numpy as np
    from PIL import Image
    im = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
    h, w, _ = im.shape
    white = np.array([255, 255, 255], np.float32)
    d_all = (white - im).reshape(-1, 3)
    idx = np.nonzero(d_all.max(1) > 0)[0]          # 흰 바탕(대부분)은 건너뛰고 칠한 픽셀만 계산
    d = d_all[idx]
    best_err = np.full(len(idx), np.inf, np.float32)
    best_a = np.zeros(len(idx), np.float32)
    best_k = np.zeros(len(idx), np.int32)
    for k, (lite, _) in enumerate(INK):
        ink = white - np.array(_rgb(lite), np.float32)  # 그 색을 다 칠했을 때의 거리
        a = np.clip((d @ ink) / float(ink @ ink), 0, 1)  # 최소제곱 진하기
        err = ((d - a[:, None] * ink) ** 2).sum(-1)
        m = err < best_err
        best_err[m], best_a[m], best_k[m] = err[m], a[m], k
    dark = np.array([_rgb(dk) for _, dk in INK], np.float32)
    out = np.zeros((h * w, 4), np.float32)
    out[:, :3] = dark[0]
    out[idx, :3] = dark[best_k]
    out[idx, 3] = best_a * 255
    out = out.reshape(h, w, 4).clip(0, 255).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst, optimize=True)
    return True


VIEW_BG = (0, 0, 0)  # '크게 보기'(그림만 따로 여는 화면)의 바탕 = 사이트 바탕(--bg #000)


def view_name(name: str) -> str:
    """'크게 보기'용 파일 이름: aave-2026-10.png → aave-2026-10.view.png"""
    return name[:-4] + ".view.png" if name.endswith(".png") else name


def write_view(dark_png: Path, dst: Path) -> None:
    """투명 바탕 어두운 차트를 검은 바탕에 깔아 불투명 PNG로 쓴다.
    그림만 따로 열면 브라우저가 투명 부분을 밝은 회색으로 칠해 밝은 글자가 안 보이기 때문(2026-10-16 운영자 신고)."""
    from PIL import Image
    im = Image.open(dark_png).convert("RGBA")
    bg = Image.new("RGBA", im.size, VIEW_BG + (255,))
    bg.alpha_composite(im)
    bg.convert("RGB").save(dst, optimize=True)


def convert_all(src_dir: Path, out_dir: Path, cache_dir: Path | None = None) -> int:
    """src_dir의 차트를 out_dir(같은 이름)에 어두운 판으로 쓴다. 바뀌지 않은 차트는 캐시에서 꺼낸다.
    '크게 보기'용 불투명 판(<이름>.view.png)도 함께 쓴다(변환이 안 되면 원본을 그대로 복사해 링크가 깨지지 않게)."""
    n = 0
    try:
        import numpy  # noqa: F401
    except Exception:
        for f in sorted(src_dir.glob("*.png")):
            (out_dir / view_name(f.name)).write_bytes(f.read_bytes())
        return 0  # numpy가 없으면 원본(흰 배경)을 그대로 둔다
    import os
    # 캐시는 사용자 홈 아래(검사용 임시 사이트·매시 빌드가 같은 결과를 다시 계산하지 않게). CHART_CACHE로 바꿀 수 있다
    cache_dir = Path(os.environ.get("CHART_CACHE") or cache_dir or Path.home() / ".cache" / "kimworld-charts-dark")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(src_dir.glob("*.png")):
        h = hashlib.md5(f.read_bytes() + b"v2").hexdigest()[:12]
        c = cache_dir / f"{f.stem}-{h}.png"
        cv = cache_dir / f"{f.stem}-{h}.view.png"
        try:
            if not c.exists():
                to_dark(f, c)
            if not cv.exists():
                write_view(c, cv)
            (out_dir / f.name).write_bytes(c.read_bytes())
            (out_dir / view_name(f.name)).write_bytes(cv.read_bytes())
            n += 1
        except Exception:
            (out_dir / view_name(f.name)).write_bytes(f.read_bytes())
            continue
    return n


def write_webp(src_dir: Path, out_dir: Path, cache_dir: Path | None = None) -> int:
    """out_dir에 쓴 본문 차트(<이름>.png, 크게 보기 판 제외)마다 같은 그림의 WebP(<이름>.webp)를 함께 쓴다(2026-11-19 운영 점검:
    차트 PNG(어두운 판) → 무손실 WebP로 약 35% 크기. 유튜브 랜딩 빠른 이탈이 가장 큰 묶음이라 휴대폰 첫 로딩을 가볍게). 리포트 화면은
    <picture>로 WebP를 먼저 주고 PNG를 대체로 남긴다. src_dir에 같은 이름 WebP(이야기형 그림)가 이미 있으면 건드리지 않는다.
    변환이 안 되면 PNG 내용을 같은 이름으로 써 둔다(화면의 <source>가 깨지지 않게). 변환한 개수를 돌려준다."""
    import os
    try:
        from PIL import Image
    except Exception:
        return 0
    cache_dir = Path(os.environ.get("CHART_CACHE") or cache_dir or Path.home() / ".cache" / "kimworld-charts-dark")
    cache_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(out_dir.glob("*.png")):
        if f.name.endswith(".view.png") or (src_dir / (f.stem + ".webp")).exists():
            continue
        data = f.read_bytes()
        c = cache_dir / f"{f.stem}-{hashlib.md5(data + b'w2').hexdigest()[:12]}.webp"
        try:
            if not c.exists():
                with Image.open(f) as im:
                    im.save(c, "WEBP", lossless=True, method=4)  # 색이 몇 개뿐인 차트라 무손실이 손실 압축보다 작다
            (out_dir / (f.stem + ".webp")).write_bytes(c.read_bytes())
            n += 1
        except Exception:
            (out_dir / (f.stem + ".webp")).write_bytes(data)  # 화면의 <source>가 깨지지 않게(브라우저는 내용으로 PNG를 알아봄)
    return n


def has_webp(out_dir: Path, png_src: str) -> bool:
    """'/static/charts/x.png' 에 대응하는 WebP가 out_dir에 쓰였는지."""
    name = png_src.rsplit("/", 1)[-1]
    return name.endswith(".png") and (out_dir / (name[:-4] + ".webp")).exists()
