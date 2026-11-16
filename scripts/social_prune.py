#!/usr/bin/env python3
"""게시가 끝난 SNS 미디어(static/social/)를 사이트 배포본에서 뺀다(2026-11-16, 배포본 0.7GB → GitHub Pages 1GB 한도 대비).

static/social/ 의 릴스 mp4·카드 jpg는 Threads·Instagram·Facebook API가 '게시하는 순간'에만 공개 주소
(https://drkimworld.com/static/social/...)로 읽어 간다. 게시 뒤에는 각 플랫폼이 사본을 가지므로 사이트에 둘 필요가 없다.
사이트 페이지·텔레그램·블로거는 이 폴더를 쓰지 않는다(대표 이미지는 /og/, 본문 그림은 /static/charts/).

빼는 파일 = 아래를 모두 만족하는 파일만:
  ① social/queue/*.json 어디에도 쓰이지 않음(대기·부분 게시 중인 글의 미디어는 절대 빼지 않음)
  ② social/posted/*.json 게시 기록에 쓰였고, 그 기록들의 posted_at 이 모두 KEEP_DAYS(3)일보다 오래됨
기록에 없는 파일(검수용 contact.jpg, 아직 대기열에 안 들어간 새 미디어)은 그대로 배포한다.
저장소의 파일은 지우지 않는다(페이스북은 저장소 파일을 직접 올리므로, 다시 게시할 때도 그대로 쓸 수 있음).

build.py 가 매 빌드(매시 5분)마다 excluded() 로 복사에서 뺀다 → 따로 정리 단계 없이 다시 쌓이지 않는다.
사용: python3 scripts/social_prune.py            # 지금 빠지는 목록 요약
      python3 scripts/social_prune.py --log      # social/pruned/<날짜>.tsv 에 목록·용량 기록
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_DAYS = 3
_REF = re.compile(r"static/social/[^\"\\\s]+")


def _refs(path: Path) -> set[str]:
    try:
        return set(_REF.findall(path.read_text(encoding="utf-8")))
    except OSError:
        return set()


def excluded(root: Path = ROOT, now: datetime | None = None, keep_days: int = KEEP_DAYS) -> dict[str, int]:
    """배포에서 뺄 static/social 파일 {저장소 기준 경로: 바이트}."""
    now = now or datetime.now(timezone.utc)
    queued: set[str] = set()
    for f in (root / "social" / "queue").glob("*.json"):
        queued |= _refs(f)
    last: dict[str, datetime | None] = {}
    for f in (root / "social" / "posted").glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            t = datetime.fromisoformat(d["posted_at"]) if d.get("posted_at") else None
            if t and t.tzinfo is None:
                t = t.replace(tzinfo=timezone(timedelta(hours=-5)))
        except (OSError, ValueError, KeyError, TypeError):
            t = None
        for r in _refs(f):
            prev = last.get(r, datetime.min.replace(tzinfo=timezone.utc))
            last[r] = None if (t is None or prev is None) else max(prev, t)  # 시각 모르는 기록이 하나라도 있으면 남김
    cut = now - timedelta(days=keep_days)
    out = {}
    base = root / "static" / "social"
    if not base.is_dir():
        return out
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        t = last.get(rel)
        if rel not in queued and t is not None and t < cut:
            out[rel] = p.stat().st_size
    return out


def main(argv):
    ex = excluded()
    total = sum(ex.values())
    print(f"배포에서 빼는 SNS 미디어 {len(ex)}개 {total / 1e6:.1f}MB(게시 {KEEP_DAYS}일 지남·대기열 미사용)")
    if "--log" in argv:
        day = datetime.now(timezone(timedelta(hours=-5))).date().isoformat()
        f = ROOT / "social" / "pruned" / f"{day}.tsv"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("bytes\tpath\n" + "".join(f"{s}\t{k}\n" for k, s in sorted(ex.items())) + f"{total}\tTOTAL({len(ex)})\n",
                     encoding="utf-8")
        print(f"기록: {f.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
