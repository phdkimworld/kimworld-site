"""사이트(리포트·종토방) 댓글에 운영자('김박사 월드') 대댓글을 다는 SQL을 출력한다.

입력: social/site_replies/*.json  {"replies": [{"parent": <댓글 id>, "slug": "b-joby", "body": "..."}]}
같은 부모에 같은 본문은 한 번만 들어간다(여러 번 돌려도 안전). 부모가 로그인 계정이면 '답글' 알림도 남긴다.
deploy.yml 'Board notices' 단계가 board_notices.py 뒤에 이어서 실행한다.
사용: python3 scripts/site_replies.py > replies.sql
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NICK = "김박사 월드"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,60}$")


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def main() -> None:
    now = int(time.time() * 1000)
    out = []
    for f in sorted((ROOT / "social/site_replies").glob("*.json")):
        for r in (json.loads(f.read_text(encoding="utf-8")).get("replies") or []):
            pid, slug, body = int(r["parent"]), str(r["slug"]), str(r["body"]).strip()
            if not SLUG_RE.match(slug) or not (2 <= len(body) <= 500):
                print(f"-- 건너뜀 {f.name} {pid}", file=sys.stderr)
                continue
            cond = (f"FROM comments p WHERE p.id = {pid} AND p.slug = {q(slug)} AND p.status = 'ok' "
                    f"AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.parent_id = {pid} AND c.nick = {q(NICK)} AND c.body = {q(body)})")
            # 알림을 먼저(답글이 들어가기 전이어야 NOT EXISTS가 참)
            out.append("INSERT INTO notifs (uid, type, ref, slug, from_nick, n, updated, seen) "
                       f"SELECT p.uid, 'reply', CAST(p.id AS TEXT), p.slug, {q(NICK)}, 1, {now}, 0 {cond} AND p.uid IS NOT NULL "
                       "ON CONFLICT(uid, type, ref) DO UPDATE SET n = 1, from_nick = excluded.from_nick, updated = excluded.updated, seen = 0;")
            out.append("INSERT INTO comments (slug, nick, body, ih, did, created, status, parent_id, reviewed) "
                       f"SELECT p.slug, {q(NICK)}, {q(body)}, 'operator', 'operator', {now}, 'ok', p.id, 1 {cond};")
    sys.stdout.write("\n".join(out) + ("\n" if out else ""))


if __name__ == "__main__":
    main()
