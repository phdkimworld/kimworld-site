"""댓글·종토방 검토 도우미 (GitHub Actions moderate.yml 에서 실행)

list  : 검토할 글(자동 보류·신고로 숨김·신고 1건 이상인 게시 글, 아직 검토 안 한 것)을 출력한다.
        저장소가 공개라 실행 기록도 공개이므로, 숫자 4자리 이상·링크·아이디·이메일은 가려서 출력한다.
apply : 결정 JSON을 검증해 SQL 파일로 만든다. 형식:
        {"comments": [{"id": 12, "status": "ok|hidden|deleted"}], "ban": [3], "unban": []}
"""
import json
import re
import sys

STATUSES = {"ok", "hidden", "deleted"}


def redact(t: str) -> str:
    t = re.sub(r"https?://\S+|www\.\S+", "[링크]", t, flags=re.I)
    t = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "[이메일]", t)
    t = re.sub(r"@[A-Za-z0-9_]{3,}", "@[아이디]", t)
    t = re.sub(r"\b[a-z0-9-]+\.(com|net|kr|co|io|me|ly|gg)\b", "[주소]", t, flags=re.I)
    t = re.sub(r"\d[\d\s.-]{3,}\d", lambda m: "#" * len(re.sub(r"\D", "", m.group(0))), t)
    return t.replace("\n", " ")[:300]


def cmd_list(path: str) -> None:
    raw = json.load(open(path, encoding="utf-8"))
    rows = raw[0]["results"] if isinstance(raw, list) else raw.get("results", [])
    print("=== QUEUE START ===")
    for r in rows:
        print(json.dumps({
            "id": r["id"], "where": r["slug"], "nick": redact(str(r["nick"])), "account": r.get("uid"),
            "status": r["status"], "reports": r["reports"], "likes": r["likes"],
            "account_hidden_total": r.get("hid") or 0, "body": redact(str(r["body"])),
        }, ensure_ascii=False))
    print(f"=== QUEUE END ({len(rows)}) ===")


def cmd_apply(decisions: str, out: str) -> None:
    d = json.loads(decisions or "{}")
    sql = []
    for c in d.get("comments", []):
        cid, st = int(c["id"]), str(c["status"])
        if st not in STATUSES:
            raise SystemExit(f"상태 값 오류: {st}")
        extra = ", reports = 0" if st == "ok" else ""
        sql.append(f"UPDATE comments SET status = '{st}', reviewed = 1{extra} WHERE id = {cid};")
    for uid in d.get("ban", []):
        uid = int(uid)
        sql.append(f"UPDATE users SET status = 'banned' WHERE id = {uid};")
        sql.append(f"UPDATE comments SET status = 'hidden', reviewed = 1 WHERE uid = {uid} AND status = 'ok';")
    for uid in d.get("unban", []):
        sql.append(f"UPDATE users SET status = 'ok' WHERE id = {int(uid)};")
    open(out, "w", encoding="utf-8").write("\n".join(sql) + "\n")
    print(f"적용할 명령 {len(sql)}개")


if __name__ == "__main__":
    if sys.argv[1] == "list":
        cmd_list(sys.argv[2])
    elif sys.argv[1] == "apply":
        cmd_apply(sys.argv[2], sys.argv[3])
