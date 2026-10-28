#!/usr/bin/env python3
"""서버(D1)에 쌓인 애드핏 데일리 리포트를 data/adfit_daily.csv에 합친다(analytics-report.yml에서 실행).

입력: .cache/an.json 의 "adfit" (휴대폰 자동 전달 → /v1/ingest/adfit → D1)
같은 날이 이미 있으면 숫자만 서버 값으로 바꾸고 메모는 남긴다. 바뀐 게 없으면 파일을 건드리지 않는다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adfit_add import COLS, load, save  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    try:
        live = json.loads((ROOT / ".cache" / "an.json").read_text(encoding="utf-8")).get("adfit") or []
    except Exception:
        live = []
    rows = {r["day"]: r for r in load()}
    changed = 0
    for x in live:
        if not x.get("day"):
            continue
        old = rows.get(x["day"])
        # 매체별 보고서처럼 빠진 값(누적 등)은 예전 값을 지킨다
        new = {k: (str(x.get(k)) if x.get(k) is not None else str((old or {}).get(k, ""))) for k in COLS if k != "note"}
        if old and all(str(old.get(k, "")) == new[k] for k in new):
            continue
        rows[x["day"]] = {**new, "note": (old or {}).get("note", "")}
        changed += 1
    if changed:
        save(list(rows.values()))
    print(f"::notice title=ADFIT SYNC::서버 {len(live)}일, 새로 넣거나 고친 날 {changed}")


if __name__ == "__main__":
    main()
