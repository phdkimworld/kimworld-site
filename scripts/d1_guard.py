#!/usr/bin/env python3
"""d1-query.yml 입력 검사(읽기 전용·개인정보 표 차단). 환경 변수 SQL·NAME. 통과하면 0, 아니면 ::error 후 1."""
import os
import re
import sys

# 개인정보·비밀 값이 든 표(운영자 결정 '개인정보 수집·노출 금지'): 세션이 원문을 읽지 않는다. 합계가 필요하면 운영 통계(/v1/admin/analytics)·digest.md로.
DENY = {"users", "sessions", "oauth_state", "oauth_nick", "dm_threads", "dm_msgs", "dm_reports", "avatars", "app_keys",
        "adfit_keys", "push_subs", "peppers", "user_reports", "ask_log", "blocks", "follows", "owners"}
WRITE = r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|truncate|begin|commit)\b"


def check(sql: str, name: str) -> str | None:
    s = sql.strip().rstrip(";").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,48}", name or ""):
        return "name은 영문 소문자·숫자·-_ (49자 이하)"
    if not re.match(r"(?is)^(select|with)\b", s):
        return "SELECT 또는 WITH로 시작하는 한 문장만"
    if ";" in s:
        return "한 문장만(; 금지)"
    if re.search(WRITE, s, re.I):
        return "쓰기·스키마 낱말 금지(읽기 전용)"
    if re.search(r"--|/\*", s):
        return "주석 금지"
    bad = sorted(t for t in DENY if re.search(rf"\b{t}\b", s, re.I))
    if bad:
        return "개인정보 표는 읽지 않음: " + ", ".join(bad)
    return None


if __name__ == "__main__":
    err = check(os.environ.get("SQL", ""), os.environ.get("NAME", ""))
    if err:
        print(f"::error title=D1 검사::{err}")
        sys.exit(1)
    print("검사 통과")
