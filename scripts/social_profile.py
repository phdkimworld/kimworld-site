"""SNS 프로필(바이오) 읽기 (운영자 지시 2026-10-27 "각 sns 페이지 바이오도 권한이 있으면 들어가서 보고 개선 대상에 포함").

읽기만 한다. 결과는 작업 로그의 "PROFILE_JSON:" 한 줄로 낸다(세션이 읽어 개선안을 만든다).
 - Threads: me?fields=username,name,threads_biography
 - 인스타그램: me?fields=username,name,biography,website,followers_count,media_count
 - 페이스북 페이지: {FB_PAGE_ID}?fields=name,about,description,website,category,followers_count,link
필드가 거절되면 최소 필드로 다시 묻고, 실패는 채널별 error로 남긴다(토큰 값은 찍지 않는다).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from social_publish import IG_API, TH_API, call, fb_call  # noqa: E402


def try_fields(get, fields_list):
    last = None
    for fields in fields_list:
        try:
            return get(fields), fields
        except Exception as e:  # 권한 없는 필드가 섞이면 더 적은 필드로
            last = str(e)[:300]
    raise RuntimeError(last or "알 수 없는 오류")


def read_all():
    out = {}
    tok = os.environ.get("THREADS_ACCESS_TOKEN")
    if tok:
        try:
            d, f = try_fields(lambda f: call(TH_API, "GET", "me", {"fields": f}, tok),
                              ["username,name,threads_biography", "username,name"])
            out["threads"] = {"ok": True, "fields": f, **d}
        except Exception as e:
            out["threads"] = {"ok": False, "error": str(e)}
    tok = os.environ.get("IG_ACCESS_TOKEN")
    if tok:
        try:
            d, f = try_fields(lambda f: call(IG_API, "GET", "me", {"fields": f}, tok),
                              ["username,name,biography,website,followers_count,media_count",
                               "username,biography,followers_count", "username"])
            out["instagram"] = {"ok": True, "fields": f, **d}
        except Exception as e:
            out["instagram"] = {"ok": False, "error": str(e)}
    tok, pid = os.environ.get("FB_PAGE_TOKEN"), os.environ.get("FB_PAGE_ID")
    if tok and pid:
        try:
            d, f = try_fields(lambda f: fb_call("GET", pid, {"fields": f}, tok),
                              ["name,about,description,website,category,followers_count,link",
                               "name,about,website,link", "name"])
            out["facebook"] = {"ok": True, "fields": f, **d}
        except Exception as e:
            out["facebook"] = {"ok": False, "error": str(e)}
    return out


def set_profile(path):
    """페이스북 페이지 소개(about)만 API로 고친다. Threads·인스타 바이오는 API로 고칠 수 없어 앱에서 직접 바꾼다."""
    want = json.load(open(path, encoding="utf-8"))
    res = {}
    fb = want.get("facebook", {})
    tok, pid = os.environ.get("FB_PAGE_TOKEN"), os.environ.get("FB_PAGE_ID")
    if fb.get("about") and tok and pid:
        try:
            fb_call("POST", pid, {"about": fb["about"]}, tok)
            res["facebook"] = {"ok": True}
        except Exception as e:
            res["facebook"] = {"ok": False, "error": str(e)}
    print("PROFILE_SET_JSON:" + json.dumps(res, ensure_ascii=False))
    return 0 if all(v.get("ok") for v in res.values()) else 1


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--set":
        sys.exit(set_profile(sys.argv[2]))
    r = read_all()
    for k, v in r.items():
        print(f"{k}: {'읽기 정상' if v.get('ok') else '읽기 실패'}")
    print("PROFILE_JSON:" + json.dumps(r, ensure_ascii=False))
