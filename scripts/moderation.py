"""댓글·종토방 검토 도우미 (GitHub Actions moderate.yml 에서 실행)

list  : 검토할 글(자동 보류·신고로 숨김·신고 1건 이상인 게시 글, 아직 검토 안 한 것)을 출력한다.
        저장소가 공개라 실행 기록도 공개이므로, 숫자 4자리 이상·링크·아이디·이메일은 가려서 출력한다.
apply : 결정 JSON을 검증해 SQL 파일로 만든다. 형식:
        {"comments": [{"id": 12, "status": "ok|hidden|deleted"}], "ban": [3], "unban": [],
         "owner_nick": ["닉네임"], "owner": [1], "unowner": []}   ← 운영자(애널리틱스 화면) 지정·해제
users : 최근 가입한 계정(번호·닉네임·가입일)을 출력한다(닉네임은 프로필에 공개되는 값).
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


def annotate(title: str, text: str) -> None:
    """실행 기록 파일은 이 환경에서 못 읽을 수 있어, REST API로 읽히는 '주석(annotation)'으로도 남긴다."""
    esc = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::notice title={title}::{esc}")


def cmd_list(path: str) -> None:
    raw = json.load(open(path, encoding="utf-8"))
    rows = raw[0]["results"] if isinstance(raw, list) else raw.get("results", [])
    items = [{
        "id": r["id"], "where": r["slug"], "nick": redact(str(r["nick"])), "account": r.get("uid"),
        "status": r["status"], "reports": r["reports"], "likes": r["likes"],
        "account_hidden_total": r.get("hid") or 0, "body": redact(str(r["body"])),
    } for r in rows]
    print("=== QUEUE START ===")
    for it in items:
        print(json.dumps(it, ensure_ascii=False))
    print(f"=== QUEUE END ({len(items)}) ===")
    # 주석 하나에 너무 길지 않게 나눠 담는다(주석은 단계당 10개까지라 최대 9묶음 + 개수)
    chunks, cur = [], []
    for it in items:
        cur.append(it)
        if len(json.dumps(cur, ensure_ascii=False)) > 6000:
            chunks.append(cur[:-1]); cur = [it]
    if cur:
        chunks.append(cur)
    chunks = chunks[:9]
    for i, ch in enumerate(chunks):
        annotate(f"QUEUE {i + 1}/{len(chunks)}", json.dumps(ch, ensure_ascii=False))
    annotate("QUEUE COUNT", str(len(items)))


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
    for nick in d.get("owner_nick", []):
        nick = str(nick)
        if not re.fullmatch(r"[가-힣A-Za-z0-9_]{2,12}", nick):
            raise SystemExit("닉네임 형식 오류")
        sql.append(f"INSERT OR IGNORE INTO owners (uid) SELECT id FROM users WHERE nick = '{nick}' AND status = 'ok';")
    for uid in d.get("owner", []):
        sql.append(f"INSERT OR IGNORE INTO owners (uid) SELECT id FROM users WHERE id = {int(uid)};")
    for uid in d.get("unowner", []):
        sql.append(f"DELETE FROM owners WHERE uid = {int(uid)};")
    open(out, "w", encoding="utf-8").write("\n".join(sql) + "\n")
    print(f"적용할 명령 {len(sql)}개")


def cmd_users(path: str) -> None:
    raw = json.load(open(path, encoding="utf-8"))
    rows = raw[0]["results"] if isinstance(raw, list) else raw.get("results", [])
    items = [{"id": r["id"], "nick": r["nick"], "joined": r["joined"], "owner": bool(r.get("own"))} for r in rows]
    annotate("USERS", json.dumps(items, ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1] == "users":
        cmd_users(sys.argv[2])
    elif sys.argv[1] == "list":
        cmd_list(sys.argv[2])
    elif sys.argv[1] == "apply":
        cmd_apply(sys.argv[2], sys.argv[3])
