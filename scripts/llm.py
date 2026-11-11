#!/usr/bin/env python3
"""Anthropic API 공통 도우미(표준 라이브러리만). 운영자 지시 2026-11-11: 월 크레딧 안에서 댓글 답글·발행 전 심사·주간 분석.

- 키(ANTHROPIC_API_KEY)가 없으면 아무것도 부르지 않고 status="no_key"를 돌려준다(실패가 아니다).
- 기능(feature)별 월 예산과 전체 월 상한을 social/llm/usage.json 장부로 지킨다. 부르기 전에 이번 호출의 최대 비용을
  어림해 예산을 넘으면 부르지 않는다(status="budget"). 사이트 Q&A 몫은 워커가 따로 관리하므로 여기 상한에 들어가지 않는다.
- 키·토큰 값은 어디에도 출력하지 않는다. 오류는 API가 준 종류와 짧은 메시지만 남긴다.

사용(파이썬):
    import llm
    r = llm.ask("comments", system="...", user="...", tier="cheap", max_tokens=600, schema={...})
    r["status"]  # ok | no_key | no_credit | budget | bad_key | refusal | truncated | error
    no_key·no_credit·budget 은 실패가 아니라 '건너뜀'이다(호출자는 기존 방식대로 두고 0으로 끝낸다).
    LLM_MOCK_RESPONSE 환경 변수가 있으면 네트워크 없이 그 글을 모델 답으로 쓴다(시험·dry 검증용).
    r["text"], r["json"], r["usd"]
명령줄:
    python3 scripts/llm.py status        # 이번 달 기능별 사용액과 남은 예산, 키 있음/없음
    python3 scripts/llm.py commit -m 메시지 경로...   # 워크플로용: 장부를 원격 최신본에 다시 더해 커밋·푸시(경쟁 안전)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE = Path(os.environ.get("LLM_USAGE_FILE") or ROOT / "social" / "llm" / "usage.json")
DELTA = Path(os.environ.get("LLM_DELTA_FILE") or ROOT / ".cache" / "llm_delta.json")   # 이번 실행에서 더한 몫(커밋 때 원격 장부에 다시 더함)
API = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"

# 모델 ID 상수(가격은 claude-api 스킬 표, 2026-11-03 기준, 1M 토큰당 달러)
MODELS = {"cheap": "claude-haiku-5-5", "judge": "claude-sonnet-5-5"}
PRICES = {  # 입력, 출력. 저가 모델은 입력 100K 토큰을 넘는 요청에서 단가가 오른다
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "in_long": 0.50, "out_long": 2.50, "long_from": 100_000},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00},
}
FALLBACK_PRICE = {"in": 5.00, "out": 25.00}   # 모르는 모델(서버 대체 응답 등)은 비싸게 셈

# 월 예산(달러). 전체 상한 120 = 기능별 합 75 + 여유. 월 크레딧 200 중 80은 사이트 Q&A(워커 별도 관리) 몫.
BUDGETS = {"comments": 40.0, "judge": 25.0, "weekly": 10.0}
TOTAL_CAP = 120.0


def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def budget(feature):
    return _env_float(f"LLM_BUDGET_{feature.upper()}", BUDGETS.get(feature, 5.0))


def total_cap():
    return _env_float("LLM_TOTAL_CAP", TOTAL_CAP)


def has_key():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


_STOP = {"status": ""}   # 한 실행 안에서 크레딧 없음(no_credit)이 한 번 나오면 더 부르지 않는다


SKIP_STATUSES = ("no_key", "no_credit", "budget", "bad_key")   # 실패가 아니라 건너뜀(bad_key 는 경고만: 키를 다시 넣어야 함)


def month_key(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


# ---------- 장부 ----------
def load_usage(path=None):
    p = Path(path or USAGE)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"months": {}}


def _empty_feat():
    return {"calls": 0, "in": 0, "out": 0, "cache_write": 0, "cache_read": 0, "usd": 0.0}


def add_usage(book, month, feature, d):
    m = book.setdefault("months", {}).setdefault(month, {"usd": 0.0, "features": {}})
    f = m["features"].setdefault(feature, _empty_feat())
    for k in ("calls", "in", "out", "cache_write", "cache_read"):
        f[k] = int(f.get(k, 0)) + int(d.get(k, 0))
    f["usd"] = round(float(f.get("usd", 0)) + float(d.get("usd", 0)), 6)
    m["usd"] = round(sum(float(x.get("usd", 0)) for x in m["features"].values()), 6)
    return book


def spent(book, month, feature=None):
    m = (book.get("months") or {}).get(month) or {}
    if feature is None:
        return float(m.get("usd", 0))
    return float(((m.get("features") or {}).get(feature) or {}).get("usd", 0))


def save_usage(book, path=None):
    p = Path(path or USAGE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(book, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def record(feature, d, month=None):
    """장부(usage.json)와 이번 실행 몫(.cache/llm_delta.json)에 같은 값을 더한다."""
    month = month or month_key()
    save_usage(add_usage(load_usage(), month, feature, d))
    delta = load_usage(DELTA)
    save_usage(add_usage(delta, month, feature, d), DELTA)


# ---------- 비용 ----------
def price_of(model):
    return PRICES.get(model, FALLBACK_PRICE)


def cost(model, inp, out, cache_write=0, cache_read=0):
    p = price_of(model)
    prompt = inp + cache_write + cache_read
    long_ = "long_from" in p and prompt > p["long_from"]
    pin, pout = (p["in_long"], p["out_long"]) if long_ else (p["in"], p["out"])
    return (inp * pin + cache_write * pin * 1.25 + cache_read * pin * 0.1 + out * pout) / 1_000_000


def estimate_tokens(text):
    """보수적 어림: 한글은 글자당 1토큰 안팎, 영문·숫자는 4글자당 1토큰 안팎."""
    han = len(re.findall(r"[가-힣]", text))
    return int(han * 1.0 + (len(text) - han) / 3.0) + 50


def usage_from_response(resp, req_model):
    """응답 usage(서버 대체가 있으면 iterations 전체)를 토큰·달러로. 대체 모델이 섞이면 비싼 단가로 센다."""
    u = resp.get("usage") or {}
    its = [x for x in (u.get("iterations") or []) if isinstance(x, dict)]
    parts = its if its else [u]
    models = {req_model, resp.get("model") or req_model}
    priced = max(models, key=lambda m: price_of(m)["in"])
    d = {"calls": 1, "in": 0, "out": 0, "cache_write": 0, "cache_read": 0, "usd": 0.0}
    for x in parts:
        d["in"] += int(x.get("input_tokens") or 0)
        d["out"] += int(x.get("output_tokens") or 0)
        d["cache_write"] += int(x.get("cache_creation_input_tokens") or 0)
        d["cache_read"] += int(x.get("cache_read_input_tokens") or 0)
    d["usd"] = round(cost(priced, d["in"], d["out"], d["cache_write"], d["cache_read"]), 6)
    return d


# ---------- 호출 ----------
def _post(body, headers, timeout):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _err_text(e):
    try:
        j = json.load(e)
        er = j.get("error") or {}
        return f"{er.get('type', '')}: {str(er.get('message', ''))[:200]}"
    except Exception:
        return ""


def ask(feature, system, user, tier="cheap", max_tokens=1024, effort=None, schema=None, cache_system=False,
        user_blocks=None, timeout=300):
    """메시지 1회. 돌려주는 값: {status, text, json, usd, model, error}.
    user_blocks 를 주면 user 대신 그 content 블록 목록을 그대로 쓴다(긴 근거에 cache_control 을 붙일 때)."""
    out = {"status": "", "text": "", "json": None, "usd": 0.0, "model": MODELS.get(tier, tier), "error": ""}
    mock = os.environ.get("LLM_MOCK_RESPONSE")
    if mock is not None:   # 시험·dry 검증용 모의 응답: 네트워크·장부 없이 이 글을 모델 답으로 돌려준다
        out["text"] = mock
        if schema:
            try:
                out["json"] = json.loads(mock)
            except ValueError:
                out["status"], out["error"] = "error", "JSON 형식 아님"
                return out
        out["status"] = "ok"
        return out
    if not has_key():
        out["status"] = "no_key"
        return out
    if _STOP["status"]:
        out["status"] = _STOP["status"]
        return out
    model = MODELS.get(tier, tier)
    content = user_blocks if user_blocks is not None else [{"type": "text", "text": user}]
    prompt_text = system + "".join(b.get("text", "") for b in content if isinstance(b, dict))
    est = cost(model, estimate_tokens(prompt_text), max_tokens)
    book, month = load_usage(), month_key()
    if spent(book, month, feature) + est > budget(feature) or spent(book, month) + est > total_cap():
        out["status"] = "budget"
        out["error"] = f"{feature} {spent(book, month, feature):.2f}/{budget(feature):.0f}달러, 전체 {spent(book, month):.2f}/{total_cap():.0f}달러"
        return out
    sys_blocks = [{"type": "text", "text": system}]
    if cache_system:
        sys_blocks[0]["cache_control"] = {"type": "ephemeral"}
    body = {"model": model, "max_tokens": max_tokens, "system": sys_blocks,
            "messages": [{"role": "user", "content": content}]}
    oc = {}
    if effort:
        oc["effort"] = effort
    if schema:
        oc["format"] = {"type": "json_schema", "schema": schema}
    if oc:
        body["output_config"] = oc
    headers = {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": API_VERSION,
               "content-type": "application/json"}
    if tier == "judge":   # 판단용 모델은 안전 분류기 거절에 대비해 서버 대체를 켠다(스킬 기본값)
        headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
        body["fallbacks"] = "default"
    resp = None
    for attempt in range(3):
        try:
            resp = _post(body, headers, timeout)
            break
        except urllib.error.HTTPError as e:
            msg = _err_text(e)
            if e.code in (429, 500, 502, 503, 504, 529) and attempt < 2:
                time.sleep(10 * (attempt + 1) ** 2)
                continue
            out["status"] = "no_credit" if "credit" in msg.lower() else ("bad_key" if e.code in (401, 403) else "error")
            out["error"] = f"HTTP {e.code} {msg}".strip()
            if out["status"] in ("no_credit", "bad_key"):   # 크레딧 없음·키 거절이면 이번 실행은 더 부르지 않는다
                _STOP["status"] = out["status"]
            return out
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            out["status"], out["error"] = "error", f"연결 실패 {type(e).__name__}"
            return out
    d = usage_from_response(resp, model)
    record(feature, d)
    out["usd"], out["model"] = d["usd"], resp.get("model") or model
    out["text"] = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
    sr = resp.get("stop_reason")
    if sr == "refusal":
        out["status"] = "refusal"
        return out
    if sr == "max_tokens":
        out["status"] = "truncated"
        return out
    if schema:
        try:
            out["json"] = json.loads(out["text"])
        except ValueError:
            m = re.search(r"\{.*\}", out["text"], re.S)
            try:
                out["json"] = json.loads(m.group(0)) if m else None
            except ValueError:
                out["json"] = None
        if out["json"] is None:
            out["status"], out["error"] = "error", "JSON 형식 아님"
            return out
    out["status"] = "ok"
    return out


# ---------- 명령줄 ----------
def status():
    book, month = load_usage(), month_key()
    print(f"키: {'있음' if has_key() else '없음(no_key — 모든 기능 건너뜀)'}")
    print(f"{month} 전체 {spent(book, month):.2f} / 상한 {total_cap():.0f}달러")
    for f in BUDGETS:
        x = ((book.get("months") or {}).get(month) or {}).get("features", {}).get(f) or _empty_feat()
        print(f"  {f}: {x['usd']:.2f} / {budget(f):.0f}달러 · 호출 {x['calls']} · 입력 {x['in']} · 출력 {x['out']}")
    return 0


def _git(*a, check=False):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=check)


def commit(message, paths):
    """워크플로 전용(CI 체크아웃에서만): 원격 main 최신본 위에 우리 산출물과 장부 증가분을 다시 얹어 커밋·푸시.
    여러 워크플로가 동시에 usage.json 을 고쳐도 rebase 충돌 없이 합쳐진다."""
    rel = [str(Path(p)) for p in paths]
    saved = {}
    for p in rel:
        fp = ROOT / p
        if fp.is_dir():
            for f in fp.rglob("*"):
                if f.is_file():
                    saved[str(f.relative_to(ROOT))] = f.read_bytes()
        elif fp.is_file():
            saved[p] = fp.read_bytes()
    usage_rel = str(USAGE.relative_to(ROOT))
    saved.pop(usage_rel, None)
    delta = load_usage(DELTA)
    for i in range(5):
        _git("fetch", "-q", "origin", "main")
        _git("reset", "-q", "--hard", "origin/main")
        for p, b in saved.items():
            fp = ROOT / p
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(b)
        book = load_usage()
        for month, m in (delta.get("months") or {}).items():
            for feat, d in (m.get("features") or {}).items():
                add_usage(book, month, feat, d)
        if delta.get("months"):
            save_usage(book)
        _git("add", "-A", "--", *(list(saved) + [usage_rel]))
        if _git("diff", "--cached", "--quiet").returncode == 0:
            print("바뀐 것 없음")
            return 0
        _git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
             "commit", "-q", "-m", message)
        if _git("push", "-q", "origin", "HEAD:main").returncode == 0:
            print(f"커밋 올림: {message}")
            return 0
        time.sleep(5 * (i + 1))
    print("::error::커밋을 올리지 못함")
    return 1


def main(argv):
    if argv[:1] == ["status"]:
        return status()
    if argv[:1] == ["commit"] and "-m" in argv:
        i = argv.index("-m")
        msg = argv[i + 1]
        paths = [a for j, a in enumerate(argv[1:], 1) if j not in (i, i + 1)]
        return commit(msg, paths)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
