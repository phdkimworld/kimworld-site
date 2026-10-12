"""종토방 첫 글(공지)을 만드는 SQL을 출력한다. 이미 공지가 있는 종토방은 건드리지 않는다(여러 번 돌려도 안전).

공지 = 종목 소개 한두 문장(그 종목 최신 리포트 '1부' 첫 문단에서) + 종토방 규칙.
사용: python3 scripts/board_notices.py > notices.sql
"""
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RULES = ("종토방 규칙\n"
         "· 이 종목에 대한 개인 의견을 나누는 곳이며, 투자 권유가 아닙니다.\n"
         "· 링크·연락처·리딩방·종목 추천 홍보는 자동으로 가려집니다.\n"
         "· 욕설·비방·개인정보·도배는 신고 3건이면 가려지고, 반복하면 이용이 제한됩니다.")


def intro_of(body: str, limit: int = 160) -> str:
    m = re.search(r"^## 1부[^\n]*\n+(.+?)(?:\n\n|\Z)", body, flags=re.S | re.M)
    if not m:
        return ""
    t = re.sub(r"^\*\*핵심\*\*\s*", "", m.group(1).strip())          # 앞의 **핵심** 표시
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                      # 링크는 글자만
    t = re.sub(r"[*_`]", "", t).replace("\n", " ").strip()
    # 첫 문장 하나(너무 짧으면 둘째 문장까지). 한국어 문장 끝 '다.'
    sents = re.split(r"(?:(?<=다\.)|(?<=\)\.))\s+", t)
    out = sents[0]
    if len(out) < 50 and len(sents) > 1 and len(out) + len(sents[1]) < limit:
        out += " " + sents[1]
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def main() -> None:
    tickers = yaml.safe_load((ROOT / "data/tickers.yaml").read_text(encoding="utf-8")) or {}
    today = dt.date.today()
    latest: dict[str, tuple] = {}
    for f in sorted((ROOT / "content/reports").glob("*.md")):
        if f.name.startswith("_"):
            continue
        raw = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, flags=re.S)
        if not m:
            continue
        meta, body = yaml.safe_load(m.group(1)) or {}, m.group(2)
        if meta.get("draft") or str(meta.get("date")) > today.isoformat():
            continue
        tk = str(meta.get("ticker", "")).upper()
        if tk and (tk not in latest or str(meta.get("date")) > latest[tk][0]):
            latest[tk] = (str(meta.get("date")), body)
    out = []
    now_ms = int(dt.datetime.now().timestamp() * 1000)
    for tk, (_, body) in sorted(latest.items()):
        t = tickers.get(tk) or {}
        name = t.get("name") or tk
        head = f"{name}({tk}) 종토방을 엽니다."
        intro = intro_of(body)
        text = "\n".join([head, "· 회사: " + intro if intro else "", "", RULES])[:500]
        esc = text.replace("'", "''")
        slug = "b-" + tk.lower()
        out.append(
            "INSERT INTO comments (slug, nick, body, ih, did, created, status, pinned, reviewed) "
            f"SELECT '{slug}', '김박사 월드', '{esc}', 'notice', 'notice', {now_ms}, 'ok', 1, 1 "
            f"WHERE NOT EXISTS (SELECT 1 FROM comments WHERE slug = '{slug}' AND pinned = 1);")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
