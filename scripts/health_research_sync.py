#!/usr/bin/env python3
"""건강월드 리서치(비공개 healthworld-ops research/episodes.json·papers.json) → 사이트 health/research.json 스냅숏
(2026-11-26 운영자 "건강몰에 제품 별로 그동안 쌓인 리서치들이 잘 연결되서 고객에게 백분 도움 되는 구조로").
공개해도 되는 칸만 옮긴다(질문·답·핵심 숫자·영상 ID·논문 카드). 운영 메모(note)·작업 번호(job)는 옮기지 않는다.

python3 scripts/health_research_sync.py <healthworld-ops 경로>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VID = re.compile(r"([A-Za-z0-9_-]{11})$")


def vid(x: str) -> str:
    m = VID.search((x or "").strip().rstrip("/"))
    return m.group(1) if m and x and x not in ("—", "-") else ""


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "../healthworld-ops") / "research"
    eps = json.loads((src / "episodes.json").read_text(encoding="utf-8"))
    papers = json.loads((src / "papers.json").read_text(encoding="utf-8"))
    out_eps = []
    for e in eps:
        if "공개 안 함" in (e.get("note") or ""):
            continue
        out_eps.append({k: e.get(k, "") for k in ("slug", "date", "angle", "ingredient", "question", "answer", "key")}
                       | {"long": vid(e.get("long", "")), "short": vid(e.get("short", ""))})
    keep = {e["slug"] for e in out_eps}
    out_p = []
    for p in papers:
        used = [s for s in p.get("episodes") or [] if s in keep]
        if used:
            out_p.append({"study": p.get("study", ""), "pmid": str(p.get("pmid") or ""), "population": p.get("population", ""),
                          "results": p.get("results") or [], "episodes": used})
    dst = ROOT / "health" / "research.json"
    dst.write_text(json.dumps({"episodes": out_eps, "papers": out_p}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"편 {len(out_eps)} · 논문 {len(out_p)} → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
