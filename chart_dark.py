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


def convert_all(src_dir: Path, out_dir: Path, cache_dir: Path | None = None) -> int:
    """src_dir의 차트를 out_dir(같은 이름)에 어두운 판으로 쓴다. 바뀌지 않은 차트는 캐시에서 꺼낸다."""
    n = 0
    try:
        import numpy  # noqa: F401
    except Exception:
        return 0  # numpy가 없으면 원본(흰 배경)을 그대로 둔다
    import os
    # 캐시는 사용자 홈 아래(검사용 임시 사이트·매시 빌드가 같은 결과를 다시 계산하지 않게). CHART_CACHE로 바꿀 수 있다
    cache_dir = Path(os.environ.get("CHART_CACHE") or cache_dir or Path.home() / ".cache" / "kimworld-charts-dark")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(src_dir.glob("*.png")):
        h = hashlib.md5(f.read_bytes() + b"v2").hexdigest()[:12]
        c = cache_dir / f"{f.stem}-{h}.png"
        try:
            if not c.exists():
                to_dark(f, c)
            (out_dir / f.name).write_bytes(c.read_bytes())
            n += 1
        except Exception:
            continue
    return n
