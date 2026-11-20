#!/usr/bin/env python3
"""옛 유튜브 영상 설명란 첫 줄에 사이트 종목 페이지 링크 달기(운영자 지시 2026-11-19 "적극사용" — 채널 접근 권한을 사업 개선에 적극 사용).

왜: 11-12~11-19 유튜브 7일 조회 증가의 49%가 30일 넘은 옛 영상, 67%가 사이트 리포트와 이어지지 않은 영상(쇼츠·사이트 전 영상)이다
(미디어 저장소 tools/biz_digest.py). 그 영상들 설명란에는 사이트 링크가 없어 조회가 사이트로 이어지지 않는다.

하는 일: 7일 조회 증가 상위 영상 가운데 (사이트 리포트에 youtube_id로 이어지지 않았고) 설명란 첫 세 줄에 drkimworld.com 이 없는 영상을 골라,
제목·태그에서 티커를 찾고(data/tickers.yaml에 있는 종목만), 설명란 맨 위에 한 줄을 넣는다:
  📊 <종목명>(<티커>) 최신 리포트 모음 👉 https://drkimworld.com/t/<티커>/?utm_source=youtube&utm_medium=video&utm_campaign=old-<티커>&utm_content=desc_top
- 제목·태그·나머지 설명은 그대로(snippet의 쓰기 가능한 칸을 모두 그대로 다시 보낸다). 고친 영상과 옛 설명은 social/youtube/desc_log.json 에 남겨 되돌릴 수 있다.
- 한 번에 최대 LIMIT(기본 10, 상한 15)편. MODE=plan 이면 고르기만 하고 바꾸지 않는다(기본). MODE=apply 일 때만 바꾼다.
- VIDEO_IDS 를 주면 그 영상만 대상으로 한다(같은 검사를 거친다).
- MODE=revert + VIDEO_IDS: 로그의 옛 설명으로 되돌린다.
환경 변수: YT_CLIENT_ID·YT_CLIENT_SECRET·YT_REFRESH_TOKEN(값 출력 금지), MODE, LIMIT, VIDEO_IDS, DESC_LOG(기록 파일 경로).
실행 통로: 이 저장소 워크플로 `yt-desc.yml`(2026-11-20 제작팀이 YT_* 비밀값을 넣음, 같은 날 plan 시험으로 확인). 기록은 social/youtube/desc_log.json(미디어 저장소 review/yt_desc_log.json 30건을 이어받음).
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yt_comments as yc  # noqa: E402  (token·call 재사용)

SNAP = "https://raw.githubusercontent.com/phdkimworld/kimworld-media/claude/kim-world-stock-studio-laes-ovy09b/stats_snapshots.jsonl"
LOG = Path(os.environ["DESC_LOG"]) if os.environ.get("DESC_LOG") else ROOT / "social" / "youtube" / "desc_log.json"  # 미디어 저장소 워크플로는 review/yt_desc_log.json
WRITABLE = ("title", "description", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage")


def tickers() -> dict:
    return yaml.safe_load((ROOT / "data" / "tickers.yaml").read_text(encoding="utf-8")) or {}


def linked_ids() -> set:
    out = set()
    for p in (ROOT / "content" / "reports").glob("*.md"):
        m = re.search(r"(?m)^youtube_id:\s*\"?([\w-]{11})", p.read_text(encoding="utf-8")[:3000])
        if m:
            out.add(m.group(1))
    return out


def gains7() -> list[tuple[str, int]]:
    with urllib.request.urlopen(SNAP, timeout=60) as r:
        rows = [json.loads(x) for x in r.read().decode("utf-8").splitlines() if x.strip()]
    last = rows[-1]
    t = dt.datetime.fromisoformat(last["t"]) - dt.timedelta(days=7)
    base = None
    for x in rows:
        if dt.datetime.fromisoformat(x["t"]) <= t:
            base = x
    base = base or rows[0]
    g = {k: v - base["v"].get(k, 0) for k, v in last["v"].items() if k in base["v"]}  # 7일 전에도 있던 영상(옛 영상)만
    return sorted(g.items(), key=lambda kv: -kv[1])


def find_ticker(sn: dict, tk: dict) -> str | None:
    text = " ".join([sn.get("title", "")] + list(sn.get("tags") or []))
    for m in re.findall(r"#\s*([A-Z0-9]{1,6})\b", sn.get("title", "") + " " + sn.get("description", "")[:400]):
        if m in tk:
            return m
    for m in re.findall(r"\(([A-Z0-9]{1,6})\)", sn.get("title", "")):
        if m in tk:
            return m
    for k, v in tk.items():  # 한글 이름이 제목에 있으면
        if isinstance(v, dict) and v.get("name") and len(v["name"]) >= 2 and v["name"] in sn.get("title", ""):
            return k
    for k in tk:
        if re.search(rf"\b{re.escape(k)}\b", text):
            return k
    return None


def line_for(t: str, tk: dict) -> str:
    name = (tk.get(t) or {}).get("name") or t
    q = urllib.parse.urlencode({"utm_source": "youtube", "utm_medium": "video", "utm_campaign": f"old-{t.lower()}", "utm_content": "desc_top"})
    return f"📊 {name}({t}) 최신 리포트 모음 👉 https://drkimworld.com/t/{t.lower()}/?{q}"


MALL = "🛒 김박사 몰(쿠팡 장보기 입구): https://drkimworld.com/mall/?utm_source=youtube&utm_medium=video&utm_campaign=old&utm_content=mall"
DISC = "※ 이 영상은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def new_desc(old: str, site_line: str) -> str:
    """2026-11-19 운영자 "내 모든 컨텐츠에 트래픽 있을거 같은데다가 다 배포해": 맨 위 사이트 링크(없을 때만, 사이트와 안 이어진 영상) +
    그 바로 아래 김박사 몰 한 줄(없을 때) + 맨 끝 쿠팡 대가성 문구(없을 때). 나머지는 그대로."""
    lines = old.split("\n") if old else []
    if site_line:
        lines = [site_line] + lines
    if "drkimworld.com/mall" not in old:
        at = 1 if lines and "drkimworld.com" in lines[0] else 0
        lines = lines[:at] + [MALL] + lines[at:]
    out = "\n".join(lines)
    if "쿠팡 파트너스" not in out:
        out = out.rstrip() + "\n\n" + DISC
    return out[:4900]


def put(tok, body):
    req = urllib.request.Request(yc.API + "videos?part=snippet", data=json.dumps(body).encode(), method="PUT",
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def main() -> int:
    if not yc.available():
        print("::notice title=옛 영상 설명::유튜브 키 없음, 건너뜀")
        return 0
    mode = (os.environ.get("MODE") or "plan").strip()
    limit = max(1, min(15, int(os.environ.get("LIMIT") or 10)))
    want = [x for x in re.split(r"[\s,]+", os.environ.get("VIDEO_IDS") or "") if re.fullmatch(r"[\w-]{11}", x)]
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    tok = yc.token()

    if mode == "revert":
        done = 0
        for vid in want:
            old = next((e for e in reversed(log) if e["id"] == vid and "old_description" in e), None)
            if not old:
                print(f"::warning title=되돌리기::{vid} 기록 없음")
                continue
            sn = yc.call(tok, "videos", part="snippet", id=vid)["items"][0]["snippet"]
            body = {"id": vid, "snippet": {k: sn[k] for k in WRITABLE if k in sn}}
            body["snippet"]["description"] = old["old_description"]
            put(tok, body)
            log.append({"id": vid, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "action": "revert"})
            done += 1
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"::notice title=되돌리기::{done}편")
        return 0

    tk, linked = tickers(), linked_ids()
    already = {e["id"] for e in log if e.get("action") in ("prepend", "mall")}
    cands = [(v, g) for v, g in (gains7() if not want else [(w, 0) for w in want]) if v not in already]
    picked, seen = [], 0
    for i in range(0, min(len(cands), 120), 50):
        chunk = cands[i:i + 50]
        items = yc.call(tok, "videos", part="snippet", id=",".join(v for v, _ in chunk)).get("items", [])
        by = {it["id"]: it["snippet"] for it in items}
        for v, g in chunk:
            seen += 1
            sn = by.get(v)
            if not sn:
                continue
            d0 = sn.get("description") or ""
            t = find_ticker(sn, tk) if v not in linked and "drkimworld.com" not in "\n".join(d0.splitlines()[:3]) else None
            if "drkimworld.com/mall" in d0 and not t:
                continue  # 이미 몰 줄이 있고 사이트 줄도 필요 없음
            picked.append((v, g, t, sn))
            if len(picked) >= limit:
                break
        if len(picked) >= limit:
            break
    for v, g, t, sn in picked:
        print(f"::notice title=옛 영상 설명 {'바꿈' if mode == 'apply' else '후보'}::{v} {'사이트+' + t if t else '몰만'} +{g}/7일 · {sn.get('title', '')[:50]}")
    if mode != "apply":
        print(f"::notice title=옛 영상 설명::후보 {len(picked)}편(살펴본 {seen}편) — MODE=apply 로 실행하면 바꿈")
        return 0
    ok = 0
    for v, g, t, sn in picked:
        body = {"id": v, "snippet": {k: sn[k] for k in WRITABLE if k in sn}}
        old = sn.get("description") or ""
        body["snippet"]["description"] = new_desc(old, line_for(t, tk) if t else "")
        if body["snippet"]["description"] == old:
            continue
        try:
            put(tok, body)
        except urllib.error.HTTPError as e:
            print(f"::warning title=옛 영상 설명::{v} HTTP {e.code} {yc.err(e)[:120]}")
            continue
        log.append({"id": v, "ticker": t, "gain7": g, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "action": "mall", "site_line": bool(t), "old_description": old})
        ok += 1
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"::notice title=옛 영상 설명::{ok}편 바꿈 · 기록 social/youtube/desc_log.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
