#!/usr/bin/env python3
"""김박사 월드 정적 사이트 생성기.

  python3 build.py            # 공개 리포트만 빌드 → dist/
  python3 build.py --drafts   # 초안까지 빌드(초안은 noindex, 목록·사이트맵 제외, 주소로만 열림)
  python3 build.py --strict   # 경고도 실패로 처리(CI에서 사용)

입력:  site.yaml, ads.yaml, data/*.yaml, content/reports/*.md, content/pages/*.md, templates/, static/
출력:  dist/ (GitHub Pages가 그대로 서비스)
"""
from __future__ import annotations

import os

import argparse
import datetime as dt
import html
import json
import math
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown.extensions.toc import slugify_unicode
from report_figures import add_figures

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
KST = dt.timezone(dt.timedelta(hours=9))

REQUIRED = ["ticker", "title", "theme", "date", "data_as_of", "summary", "sources"]
COUPANG_DISCLOSURE = "이 영역은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
COUPANG_PAGE_NOTICE = "이 페이지에는 쿠팡 파트너스 링크가 포함되어 있습니다."
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
ADSENSE_CLIENT_RE = re.compile(r"^ca-pub-\d{10,20}$")
ADFIT_RE = re.compile(r"^DAN-[A-Za-z0-9]+$")


class BuildError(Exception):
    pass


class Log:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)


# ---------------------------------------------------------------- 읽기


def short_answer(body: str) -> str:
    """리포트의 '## 짧은 답' 절을 꾸밈 없는 글로(AI 답변·검색 요약용 FAQ 구조화 데이터). 없으면 빈 글자."""
    m = re.search(r"^##\s*짧은 답\s*\n(.*?)(?=^##\s|\Z)", body, flags=re.S | re.M)
    if not m:
        return ""
    t = m.group(1)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_`>#]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:1200]


def video_question(summary: str, body_html: str) -> tuple[str, str]:
    """요약 끝 질문(영상이 던지는 질문)과 그 답이 나오는 1부 이후 소제목 id. 못 찾으면 ("", "").
    유튜브에서 온 독자에게 '영상의 질문 → 답 바로 보기'를 보이려고 쓴다(2026-10-23, yt_jump 누름 2%)."""
    sents = re.split(r"(?<=[.?!])\s+", (summary or "").strip())
    q = sents[-1].strip() if sents else ""
    if not q.endswith("?") or len(q) < 10:
        return "", ""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    secs = []  # (id, 이름, 꾸밈 없는 본문)
    heads = list(re.finditer(r'<h([23])[^>]*\bid="([^"]+)"[^>]*>(.*?)</h\1>', body_html, flags=re.S))
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body_html)
        secs.append((h.group(2), norm(re.sub(r"<[^>]+>", "", h.group(3))), norm(re.sub(r"<[^>]+>", " ", body_html[h.end():end]))))
    start = next((i for i, s in enumerate(secs) if re.match(r"^1부", s[1])), None)
    if start is None:
        return "", ""
    qn = norm(q)
    for n in range(min(len(qn) - 4, 24), 7, -1):
        key = qn[:n]
        for sid, _, txt in secs[start:]:
            for m in re.finditer(re.escape(key), txt):
                tail = re.split(r"(?<=[.?!])\s", txt[m.start():], maxsplit=1)[0]
                if not tail.rstrip().endswith("?"):
                    return q, sid
    return q, ""

def load_yaml(p: Path, default=None):
    if not p.exists():
        return default
    return yaml.safe_load(p.read_text(encoding="utf-8")) or default


def parse_front(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        raise BuildError(f"{path.relative_to(ROOT)}: 맨 위에 --- 로 감싼 머리말이 없습니다.")
    try:
        return yaml.load(m.group(1), Loader=_UniqueKeyLoader) or {}, m.group(2)
    except yaml.constructor.ConstructorError as e:
        raise BuildError(f"{path.relative_to(ROOT)}: 머리말에 같은 키가 두 번 있습니다({e.problem}). 뒤의 값이 앞의 값을 덮어씁니다.")


class _UniqueKeyLoader(yaml.SafeLoader):
    """머리말에서 같은 키가 두 번 나오면 오류(독립 검토 2026-10-16: 출처 url 중복이 조용히 덮어써짐)."""
    def construct_mapping(self, node, deep=False):
        seen = set()
        for k, _ in node.value:
            key = self.construct_object(k, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(None, None, f"중복 키 '{key}'", k.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def to_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v).strip())


def fix_list_breaks(md_text: str) -> str:
    """목록 바로 앞에 빈 줄이 없으면 마크다운이 목록을 문단 글자로 이어 붙인다('… 올랐다. - 예: …').
    문단 줄 다음에 '- '·'* '·'1. '로 시작하는 줄이 오면 사이에 빈 줄을 넣는다(코드 블록·표·인용 안은 건드리지 않음)."""
    out, fence = [], False
    lines = md_text.split("\n")
    item = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+\S")
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
        if (not fence and i and item.match(ln) and out and out[-1].strip()
                and not item.match(out[-1]) and not out[-1].startswith(("    ", "\t", "|", ">", "#"))
                and not re.match(r"^\s+\S", out[-1])):
            out.append("")
        out.append(ln)
    return "\n".join(out)


def md_renderer():
    return markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "footnotes", "toc"],
        extension_configs={"toc": {"slugify": slugify_unicode, "toc_depth": "2-3"}},
    )


# ---------------------------------------------------------------- 본문 가공

SKIP_TAGS = {"a", "summary", "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "th", "button", "sup", "script", "style"}


def apply_glossary(body_html: str, glossary: list[dict]) -> tuple[str, list[dict]]:
    """각 용어가 처음 나오는 본문 텍스트에 표시를 단다(제목·링크·코드·표 머리 제외)."""
    used = []
    remaining = []
    for g in glossary:
        t = str(g["term"])
        if re.fullmatch(r"[A-Za-z0-9/\-.]+", t):
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])")
        else:
            pat = re.compile(re.escape(t))
        remaining.append((t, str(g["def"]), pat))
    parts = re.split(r"(<[^>]+>)", body_html)
    stack: list[str] = []
    out = []
    for part in parts:
        if part.startswith("<"):
            m = re.match(r"<\s*(/)?\s*([a-zA-Z0-9]+)", part)
            if m:
                tag = m.group(2).lower()
                if m.group(1):
                    if tag in stack:
                        while stack and stack.pop() != tag:
                            pass
                elif not part.endswith("/>") and tag in SKIP_TAGS:
                    stack.append(tag)
            out.append(part)
            continue
        if stack or not part.strip() or not remaining:
            out.append(part)
            continue
        # 한 텍스트 조각 안에서 아직 안 쓴 용어를 하나씩 찾는다
        text = part
        changed = True
        while changed and remaining:
            changed = False
            best = None
            for i, (t, d, pat) in enumerate(remaining):
                m = pat.search(text) if "\x00" not in text else None
                if m and (best is None or m.start() < best[1].start()):
                    best = (i, m)
            if best:
                i, m = best
                t, d, _ = remaining.pop(i)
                tid = f"term-{len(used)}"
                used.append({"term": t, "def": d, "id": tid})
                text = text[: m.start()] + f"\x00{len(used)-1}\x00" + text[m.end():]
                changed = True
        def put(mm):
            u = used[int(mm.group(1))]
            return (
                f'<button type="button" class="term" aria-describedby="{u["id"]}" data-def="{html.escape(u["def"], quote=True)}">'
                f'{html.escape(u["term"])}</button>'
            )
        out.append(re.sub(r"\x00(\d+)\x00", put, text))
    return "".join(out), used


def ad_weights(ads) -> dict:
    """쿠팡 상자 학습 자료(정적 파일, 매시 빌드 때 갱신). 브라우저가 이걸 보고 묶음을 고른다(API 부담 없음).
    - 노출·클릭: Cloudflare 기록(.cache/ad_stats.json, 지난 30일) → 묶음별 합계, 이용 환경별(s), 자리별(l)
    - 수수료: 쿠팡 실적(.cache/coupang_reports.json, 지난 30일) → 묶음별 주문·수수료"""
    def load(name):
        try:
            return json.loads((ROOT / ".cache" / name).read_text(encoding="utf-8"))
        except Exception:
            return {}
    raw = load("ad_stats.json")
    rows = raw[0].get("results", []) if isinstance(raw, list) and raw else (raw.get("results", []) if isinstance(raw, dict) else [])
    rep = load("coupang_reports.json").get("by_sub", {})
    g: dict[str, dict] = {}
    for gs in ads.c_auto.values():
        for x in gs:
            sid = str(x.get("sub_id") or "")
            if sid:
                g[sid] = {"t": ads.theme_slug.get(x.get("theme"), ""), "i": 0, "c": 0, "s": {}, "l": {}}
    tot_i = tot_c = 0
    for r in rows:
        sid = str(r.get("g") or "")
        i, c = int(r.get("imps") or 0), int(r.get("clicks") or 0)
        tot_i += i; tot_c += c
        if sid not in g:
            continue
        e = g[sid]; e["i"] += i; e["c"] += c
        for key, k in (("s", str(r.get("seg") or "")), ("l", str(r.get("slot") or ""))):
            v = e[key].setdefault(k, [0, 0]); v[0] += i; v[1] += c
    tot_r = 0.0
    for sid, v in rep.items():
        if sid in g:
            g[sid]["r"] = round(float(v.get("commission") or 0)); g[sid]["o"] = int(v.get("orders") or 0)
        tot_r += float(v.get("commission") or 0)
    ctr = (tot_c + 2) / (tot_i + 100)                      # 전체 클릭률(자료가 적으면 2%에 가깝게)
    epc = (tot_r / tot_c) if tot_c and tot_r else 0.0      # 클릭 1번당 평균 수수료(실적이 있을 때만)
    return {"v": 1, "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "prior": {"ctr": round(ctr, 5), "n": 40}, "epc": round(epc, 2), "explore": 0.1, "g": g}


def chart_info(slug: str) -> dict | None:
    """피드 카드에 붙일 대표 차트(static/charts/<slug>.png)와 크기(레이아웃 밀림 방지)."""
    f = ROOT / "static" / "charts" / f"{slug}.png"
    if not f.exists():
        return None
    try:
        from PIL import Image
        with Image.open(f) as im:
            w, h = im.size
    except Exception:
        w, h = 1080, 1080
    return {"src": f"/static/charts/{slug}.png", "w": w, "h": h}


def wrap_tables(html_in: str, extra: str = "") -> str:
    """표를 가로 스크롤 상자로 감싼다(표 자체는 폭을 꽉 채우고, 넘칠 때만 상자 안에서 밀린다)."""
    cls = ("table-wrap " + extra).strip()
    if "table-text" in extra:
        # 글 위주 표(개인정보처리방침 등): 휴대폰에서 칸마다 머리글을 붙인 카드로 보이도록 data-label을 단다
        def label(tm: re.Match) -> str:
            t = tm.group(0)
            heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", t, flags=re.S)]
            def row(rm: re.Match) -> str:
                i = iter(heads)
                return re.sub(r"<td(\s[^>]*)?>", lambda m: f'<td data-label="{html.escape(next(i, ""))}"{m.group(1) or ""}>', rm.group(0))
            return re.sub(r"<tr>.*?</tr>", row, t, flags=re.S)
        html_in = re.sub(r"<table>.*?</table>", label, html_in, flags=re.S)
    return html_in.replace("<table>", f'<div class="{cls}"><table>').replace("</table>", "</table></div>")


def fold_event_cards(body_html: str) -> str:
    """'이벤트 카드' 부의 연도별 묶음(### 2026년 …)을 접힌 상자로 바꾼다. 모바일에서 길이를 줄이기 위해서다."""
    h2s = [m.start() for m in re.finditer(r"<h2[\s>]", body_html)]
    for i, pos in enumerate(h2s):
        end_h = body_html.find("</h2>", pos)
        if "이벤트 카드" not in body_html[pos:end_h]:
            continue
        sec_end = h2s[i + 1] if i + 1 < len(h2s) else len(body_html)
        sec = body_html[pos:sec_end]
        h3 = list(re.finditer(r'<h3( id="[^"]*")?>(.*?)</h3>', sec, flags=re.S))
        out, last = [], 0
        for j, m in enumerate(h3):
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not re.match(r"\d{4}", title):
                continue
            stop = h3[j + 1].start() if j + 1 < len(h3) else len(sec)
            inner = sec[m.end():stop]
            n = len(re.findall(r"<p><strong>\d{4}\.\d{1,2}", inner))
            cnt = f' <span class="fold-n">카드 {n}장</span>' if n else ""
            out.append(sec[last:m.start()])
            out.append(f'<details class="fold"{m.group(1) or ""}><summary><span class="fold-t">{title}</span>{cnt}</summary>{inner}</details>\n')
            last = stop
        out.append(sec[last:])
        return body_html[:pos] + "".join(out) + body_html[sec_end:]
    return body_html


def _h2_sections(body_html: str):
    """본문의 <h2> 위치와 제목 목록."""
    out = []
    for m in re.finditer(r'<h2( id="([^"]*)")?>(.*?)</h2>', body_html, flags=re.S):
        out.append((m.start(), m.end(), m.group(2) or "", re.sub(r"<[^>]+>", "", m.group(3)).strip()))
    return out


def _fold_h3(sec: str, keep, summary_extra=None, lift_lesson=False) -> str:
    """구간 안의 <h3> 묶음을 접힌 상자로 바꾼다. keep(title)이 True면 그대로 둔다.
    lift_lesson: 묶음 안 '교훈' 인용 블록은 상자 밖(바로 아래)에 꺼내 두어 접어도 요점은 보이게 한다."""
    h3 = list(re.finditer(r'<h3( id="[^"]*")?>(.*?)</h3>', sec, flags=re.S))
    if not h3:
        return sec
    out, last = [], 0
    for j, m in enumerate(h3):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        stop = h3[j + 1].start() if j + 1 < len(h3) else len(sec)
        if keep(title, j, len(h3)):
            continue
        inner = sec[m.end():stop]
        lesson = ""
        if lift_lesson:
            lm = re.search(r"<blockquote>\s*<p><strong>교훈</strong>.*?</blockquote>", inner, flags=re.S)
            if lm:
                lesson = lm.group(0).replace("<blockquote>", '<blockquote class="lesson-out">', 1)
                inner = inner[:lm.start()] + inner[lm.end():]
        extra = summary_extra(inner) if summary_extra else ""
        out.append(sec[last:m.start()])
        out.append(f'<details class="fold"{m.group(1) or ""}><summary><span class="fold-t">{title}</span>{extra}</summary>{inner}</details>\n{lesson}')
        last = stop
    out.append(sec[last:])
    return "".join(out)


def shape_for_reading(body_html: str) -> str:
    """중간 이탈을 줄이는 본문 정리(2026-10-14). 원고는 그대로 두고 화면에서만 바꾼다.
    - '먼저 알아둘 용어' 목록을 접는다(첫머리 속도 방지턱. 본문에서는 용어를 눌러 뜻을 본다)
    - 2부 연대기: 가장 최근 시기만 펼치고 나머지는 접되 각 시기의 '교훈'은 밖에 보인다
    - 4부 패턴: 패턴마다 접고 '전형적 반응'을 제목 옆에 보인다. '큰 그림'은 펼친다
    - 5부: 5.1 국면 진단·5.5 고유 계산만 펼치고 나머지 절은 접는다. 6부: 체크리스트만 펼친다
    - 부가 끝날 때마다 다음 부의 핵심 첫 문장을 '다음 이야기' 줄로 보여 준다(열린 고리)
    - '진단' 인용 블록에 #diagnosis 를 단다(요약 상자·영상 바로가기에서 링크)"""
    secs = _h2_sections(body_html)
    if not secs:
        return body_html
    pieces, last = [], 0
    for i, (st, en, sid, title) in enumerate(secs):
        sec_end = secs[i + 1][0] if i + 1 < len(secs) else len(body_html)
        head, sec = body_html[st:en], body_html[en:sec_end]
        if title.startswith("먼저 알아둘 용어"):
            n = len(re.findall(r"<li>", sec))
            m = re.search(r"<ul>.*?</ul>", sec, flags=re.S)
            if m and n:
                sec = sec[:m.start()] + f'<details class="fold"><summary><span class="fold-t">용어 {n}개 보기</span> <span class="fold-n">본문에서 밑줄 친 용어를 누르면 뜻이 나옵니다</span></summary>{m.group(0)}</details>' + sec[m.end():]
        elif re.match(r"2부", title):
            sec = _fold_h3(sec, keep=lambda t, j, n: j == n - 1 or not t.startswith("시기"), lift_lesson=True)
        elif re.match(r"4부", title):
            def typ(inner):
                m = re.search(r"<li><strong>전형적 반응</strong>:?\s*(.*?)</li>", inner, flags=re.S)
                return f' <span class="fold-n">{re.sub(r"<[^>]+>", "", m.group(1)).strip()}</span>' if m else ""
            sec = _fold_h3(sec, keep=lambda t, j, n: not re.match(r"P\d", t), summary_extra=typ)
        elif re.match(r"5부", title):
            sec = _fold_h3(sec, keep=lambda t, j, n: bool(re.match(r"5\.[15]\b", t)) or not re.match(r"5\.\d", t))
        elif re.match(r"6부", title):
            sec = _fold_h3(sec, keep=lambda t, j, n: "체크리스트" in t or not re.match(r"6\.\d", t))
        # 다음 부 예고(이 부의 끝에): 다음 h2가 'N부'면 그 부의 '핵심' 첫 문장
        if re.match(r"[1-5]부", title) and i + 1 < len(secs) and re.match(r"[2-6]부", secs[i + 1][3]):
            nst, nen, nid, ntitle = secs[i + 1]
            nxt_end = secs[i + 2][0] if i + 2 < len(secs) else len(body_html)
            km = re.search(r"<p><strong>핵심</strong>\s*(.*?)</p>", body_html[nen:nxt_end], flags=re.S)
            if km and nid:
                sents = re.split(r"(?<=다\.)\s", re.sub(r"<[^>]+>", "", km.group(1)).strip())
                first = sents[0] if len(sents[0]) >= 30 or len(sents) == 1 else sents[0] + " " + sents[1]
                sec += f'<a class="next-part" href="#{nid}"><span class="np-k">다음 · {html.escape(ntitle)}</span><span class="np-t">{html.escape(first)}</span></a>\n'
        pieces.append(body_html[last:st]); pieces.append(head + sec); last = sec_end
    pieces.append(body_html[last:])
    out = "".join(pieces)
    out = re.sub(r"<blockquote>(\s*<p><strong>[^<]*진단)", r'<blockquote id="diagnosis">\1', out, count=1)
    return out


def split_for_ads(body_html: str, want_mid: bool, want_products: bool, want_late: bool = False) -> list[tuple[str, str]]:
    """본문을 광고 자리에서 나눈다. 반환: [("html", 조각) | ("ad", 자리이름)]
    want_late: 긴 리포트에서 본문 4분의 3쯤 소제목 앞에 한 자리 더(가운데 광고와 끝 광고 사이가 너무 멀지 않게)."""
    h2 = [m.start() for m in re.finditer(r"<h2[\s>]", body_html)]
    # 가운데 광고: 첫머리(훅·같은 뉴스) 안이 아니라 1부와 대표 차트를 지난 '2부' 제목 앞에 둔다(2026-10-14, 첫머리 이탈 줄이기)
    part2 = [p for p in h2 if re.match(r"<h2[^>]*>\s*2부", body_html[p:p + 80])]
    mid = (part2[0] if part2 else (h2[2] if len(h2) >= 3 else -1)) if want_mid else -1
    prod = -1
    if want_products:
        prod = len(body_html)
        found = False
        for i, pos in enumerate(h2):
            end = body_html.find("</h2>", pos)
            if "운영자 판단" in body_html[pos:end]:
                prod = h2[i + 1] if i + 1 < len(h2) else len(body_html)
                found = True
                break
        if not found:
            # "운영자 판단"이 없는 긴 리포트는 본문 한가운데에 가장 가까운 소제목 앞에 둔다(끝의 광고와 몰리지 않게)
            later = [p for p in h2 if p > mid + 1]
            if later:
                prod = min(later, key=lambda p: abs(p - len(body_html) / 2))
        if prod == mid:
            prod = -1  # 두 광고가 붙으면 아래쪽을 끈다
    late = -1
    if want_late:
        cands = [p for p in h2 if p > max(mid, prod) + 1 and p < len(body_html) * 0.9]
        if cands:
            late = min(cands, key=lambda p: abs(p - len(body_html) * 0.75))
    cuts = sorted([(p, n) for p, n in ((mid, "report_mid"), (prod, "report_products"), (late, "report_late")) if p >= 0])
    out, last = [], 0
    for p, n in cuts:
        if p > last:
            out.append(("html", body_html[last:p]))
        out.append(("ad", n))
        last = p
    if last < len(body_html):
        out.append(("html", body_html[last:]))
    return out


def mid_next_pick(r: dict) -> tuple[dict | None, str]:
    """본문 중간 링크 대상: 같은 종목 후속편 → 같은 종목 지난 리포트 → 같은 테마 다른 종목(2026-10-20: 테마 다른 종목 링크는
    리포트 265뷰에 누름 0. 유튜브·Threads 독자는 그 종목 하나를 보러 오므로 같은 종목 리포트를 먼저 잇는다)."""
    if r.get("newer"):
        return r["newer"], "이 종목 후속 리포트"
    if r.get("ticker_reports"):
        return r["ticker_reports"][0], "이 종목 지난 리포트"
    rel = (r.get("related") or [None])[0]
    return rel, "같은 테마 다른 종목"


def insert_mid_next(body_html: str, rel: dict | None, label: str = "함께 읽기") -> str:
    """짧은 답 절 끝(없거나 광고 자리와 붙으면 본문 40% 안팎 문단 사이)에 같은 테마 다음 리포트 한 줄 링크를 끼운다(2026-10-16 운영 통계: 리포트 평균 스크롤 55%·
    유튜브 유입 세션당 1.4쪽이라 맨 아래 '다음에 읽을 만한' 칸까지 내려오는 사람이 적다). 소제목(광고 자리) 바로 앞은 피하고
    인용·목록·접기·표 안에는 넣지 않는다."""
    if not rel or plain_len(body_html) < 3000:
        return body_html
    title = rel["title"].split(" | ")[0].strip()  # 검색용 꼬리말(| 주가 내러티브와 패턴 투자전략)은 링크 글에서 뺀다
    box = (f'<p class="mid-next"><span class="mid-next-k">{html.escape(label)}</span> '
           f'<a href="{html.escape(rel["url"], quote=True)}" data-mid-next>{html.escape(rel["ticker"])} · {html.escape(title)} →</a></p>\n')
    # 2026-10-24: 40% 지점 링크는 5일째 누름 0, 구간 도달은 '짧은 답' 82% → 2부 52% → '다음 리포트' 17%(리포트 60뷰).
    # 그래서 '짧은 답' 절 끝(다음 소제목 바로 앞)에 둔다. 다음 소제목이 '2부'(가운데 광고 자리)면 광고와 붙으므로 예전 자리로.
    m = re.search(r"<h2[^>]*>\s*짧은 답\s*</h2>", body_html)
    if m:
        nxt = re.compile(r"<h2[\s>]").search(body_html, m.end())
        h2 = [x.start() for x in re.finditer(r"<h2[\s>]", body_html)]
        has_p2 = bool(re.search(r"<h2[^>]*>\s*2부", body_html))
        is_mid_ad = nxt and (re.match(r"<h2[^>]*>\s*2부", body_html[nxt.start():nxt.start() + 80])
                             or (not has_p2 and len(h2) >= 3 and nxt.start() == h2[2]))
        if nxt and not is_mid_ad:
            return body_html[:nxt.start()] + box + body_html[nxt.start():]
    target = len(body_html) * 0.4
    best = -1
    for m in re.finditer(r"</p>\s*(?=<p[\s>])", body_html):
        pos = m.end()
        before = body_html[:pos]
        if any(before.count(f"<{t}") != before.count(f"</{t}>") for t in ("blockquote", "details", "table", "li", "aside", "figure")):
            continue
        if best < 0 or abs(pos - target) < abs(best - target):
            best = pos
    if best < 0 or not (0.25 <= best / len(body_html) <= 0.6):
        return body_html
    return body_html[:best] + box + body_html[best:]


def plain_len(s: str) -> int:
    return len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", s)))


# ---------------------------------------------------------------- 광고

class Ads:
    def __init__(self, cfg: dict, log: Log):
        self.cfg = cfg or {}
        self.on = bool(self.cfg.get("enabled", True))
        self.log = log
        a = self.cfg.get("adsense") or {}
        self.adsense_client = str(a.get("client") or "").strip()
        if self.adsense_client and not ADSENSE_CLIENT_RE.match(self.adsense_client):
            log.err(f"ads.yaml adsense.client 형식 오류: ca-pub- 뒤에 숫자가 와야 합니다")
            self.adsense_client = ""
        self.adsense_slots = {k: str(v or "").strip() for k, v in (a.get("slots") or {}).items()}
        for k, v in self.adsense_slots.items():
            if v and not v.isdigit():
                log.err(f"ads.yaml adsense.slots.{k} 는 숫자여야 합니다")
                self.adsense_slots[k] = ""
        f = self.cfg.get("adfit") or {}
        self.adfit_w = int(f.get("width") or 320)
        self.adfit_h = int(f.get("height") or 100)
        # 단위마다 크기가 다를 수 있다(예: 본문 중간 300x250). 없으면 width/height
        self.adfit_sizes = {k: (int(v[0]), int(v[1])) for k, v in (f.get("sizes") or {}).items() if isinstance(v, (list, tuple)) and len(v) == 2}
        self.adfit_units = {k: str(v or "").strip() for k, v in (f.get("units") or {}).items()}
        # 카카오 애드핏 운영정책: 한 페이지에 카카오 광고 4개 초과 금지, 콘텐츠와 함께 광고를 계속 동적으로 불러오기 금지.
        # 그래서 애드핏은 처음 받는 HTML의 고정 자리에만, 한 페이지 4개까지(같은 단위는 한 번). 아래로 더 내려가며 채우는 자리는 애드센스·쿠팡
        self.adfit_max = int(f.get("max_per_page") or 4)
        if self.adfit_max > 4:
            log.err("ads.yaml adfit.max_per_page 는 4 이하(애드핏 운영정책: 한 페이지 4개 초과 금지)")
            self.adfit_max = 4
        self._page_adfit: set = set()
        for k, v in self.adfit_units.items():
            if v and not ADFIT_RE.match(v):
                log.err(f"ads.yaml adfit.units.{k} 형식 오류(DAN-로 시작)")
                self.adfit_units[k] = ""
        # 데이블(추천 콘텐츠 광고): 승인 뒤 받은 서비스 이름·위젯 번호를 넣으면 켜진다. 비어 있으면 아무것도 출력하지 않는다
        dbl = self.cfg.get("dable") or {}
        self.dable_service = str(dbl.get("service") or "").strip()
        if self.dable_service and not re.fullmatch(r"[A-Za-z0-9.-]{3,80}", self.dable_service):
            log.err("ads.yaml dable.service 형식 오류(예: drkimworld.com)")
            self.dable_service = ""
        self.dable_widgets = {}
        for k, v in (dbl.get("widgets") or {}).items():
            v = str(v or "").strip()
            if v and not re.fullmatch(r"[A-Za-z0-9]{4,24}", v):
                log.err(f"ads.yaml dable.widgets.{k} 형식 오류(영문·숫자 위젯 번호)")
                v = ""
            self.dable_widgets[str(k)] = v
        # ads.txt 에 덧붙일 줄(새 광고 네트워크가 요구할 때): "도메인, 계정번호, DIRECT|RESELLER[, 인증ID]"
        self.ads_txt_extra = []
        for ln in self.cfg.get("ads_txt_extra") or []:
            ln = str(ln).strip()
            if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}\s*,\s*[A-Za-z0-9_.-]+\s*,\s*(DIRECT|RESELLER)(\s*,\s*[A-Za-z0-9]+)?", ln):
                self.ads_txt_extra.append(ln)
            elif ln:
                log.err(f"ads.yaml ads_txt_extra 형식 오류: {ln}")
        c = self.cfg.get("coupang") or {}
        self.c_allowed = [d.lower() for d in (c.get("allowed_domains") or ["coupang.com", "coupangcdn.com"])]
        self.c_banner = str(c.get("banner_html") or "").strip()
        self.c_banner_h = int(c.get("banner_height") or 140)
        if self.c_banner:
            bad = self.bad_hosts(self.c_banner)
            if bad:
                log.err(f"ads.yaml coupang.banner_html 에 쿠팡 밖 주소가 있습니다: {', '.join(bad)}")
                self.c_banner = ""
        self.c_products = c.get("products") or {}
        for theme, items in self.c_products.items():
            for it in items or []:
                bad = self.bad_hosts(str(it.get("url", "")) + " " + str(it.get("image", "")))
                if bad or not str(it.get("url", "")).startswith("https://"):
                    log.err(f"ads.yaml coupang.products.{theme} 의 '{it.get('name')}' 주소가 쿠팡 https 주소가 아닙니다")
        self.c_per_box = int(c.get("products_per_box") or 3)
        self.c_blocked = [str(w).lower() for w in (c.get("blocked_words") or [])]
        self.c_book_blocked = [str(w).lower() for w in (c.get("book_blocked_words") or [])]
        # 쿠팡 API 자동 상품(scripts/coupang_sync.py 결과). 없으면 위 수동 상품만 쓴다.
        self.c_auto: dict[str, list[dict]] = {}
        auto_path = Path(os.environ.get("COUPANG_CACHE") or ROOT / ".cache" / "coupang_auto.json")
        try:
            entries = (json.loads(auto_path.read_text(encoding="utf-8")).get("entries") or {}).values()
        except Exception:
            entries = []
        for e in entries:
            prods = [x for x in (e.get("products") or [])
                     if str(x.get("url", "")).startswith("https://") and not self.bad_hosts(str(x.get("url", "")) + " " + str(x.get("image", "")))]
            if prods:
                self.c_auto.setdefault(str(e.get("theme")), []).append(
                    {"keyword": e.get("keyword"), "sub_id": e.get("sub_id"), "date": e.get("date", ""), "products": prods, "theme": str(e.get("theme"))})
        for groups in self.c_auto.values():
            groups.sort(key=lambda g: str(g.get("sub_id")))
        self._common_rot = 0  # 공통 묶음을 상자마다 돌려 넣는 순번
        self._all_rot = 0     # 모든 테마 상자에 싣는 묶음을 돌리는 순번
        self.theme_slug: dict[str, str] = {"_common": "common"}  # 테마 이름 → 주소용 이름(build 에서 채움). 맞춤형 광고 선택에 쓴다
        self.place = self.cfg.get("placements") or {}
        # 대화 사이 광고 리듬(first번째 글 뒤부터 every개마다, 최대 max개)
        rh = self.cfg.get("rhythm") or {}
        def _r(k, d):
            v = rh.get(k) or {}
            return {"first": int(v.get("first", d[0])), "every": int(v.get("every", d[1])), "max": int(v.get("max", d[2]))}
        self.rhythm = {"report_comments": _r("report_comments", (6, 6, 3)), "board": _r("board", (4, 6, 4)),
                       "home_feed": _r("home_feed", (4, 6, 5))}
        if min(self.rhythm[k]["every"] for k in self.rhythm) < 1:
            log.err("ads.yaml rhythm: 광고 사이 간격(every)은 1 이상")
        valid = {"adsense_in_article", "adsense_display", "adfit_report_mid", "adfit_report_end", "adfit_list", "adfit_feed", "adfit_feed2", "adfit_rail", "adfit_bottom", "coupang_banner", "coupang_products", "dable_report", "none", None}  # page_bottom: 페이지 맨 아래(리포트 면책 위·목록 끝)
        for k, v in self.place.items():
            for one in (v if isinstance(v, list) else [v]):
                if one not in valid:
                    log.err(f"ads.yaml placements.{k} 값 '{one}' 을 알 수 없습니다")
                if k in ("thread_inline", "explore_inline", "profile_inline") and one not in ("coupang_products", "adsense_in_article", "none", None):
                    log.err(f"ads.yaml placements.{k} 은 coupang_products·adsense_in_article·none 만 가능(화면에서 끼워 넣는 자리)")

    def bad_hosts(self, s: str) -> list[str]:
        hosts = {h.lower() for h in re.findall(r"(?:https?:)?//([A-Za-z0-9.-]+)", s)}
        return sorted(h for h in hosts if not any(h == d or h.endswith("." + d) for d in self.c_allowed))

    CP_GROUPS_MAX = 7  # 쿠팡 상자 하나에 싣는 묶음 수(보이는 1개 + 학습 후보 6개)

    # 자리 → 광고 종류
    ADFIT_KEY = {"adfit_report_mid": "report_mid", "adfit_report_end": "report_end", "adfit_feed": "feed", "adfit_feed2": "feed2",
                 "adfit_rail": "rail", "adfit_bottom": "bottom"}

    def begin_page(self) -> None:
        """새 페이지를 그리기 시작: 이 페이지에서 쓴 애드핏 단위 기록을 비운다(한 페이지 4개·같은 단위 한 번)."""
        self._page_adfit = set()

    def adfit_count(self) -> int:
        return len(self._page_adfit)

    def adfit_key(self, kind: str) -> str:
        if kind == "adfit_list":
            return "list" if self.adfit_units.get("list") else "report_end"
        return self.ADFIT_KEY.get(kind, "")

    def kind(self, slot: str, ctx: dict | None = None):
        """자리에 낼 광고 종류. 목록이면 앞에서부터 실제로 낼 수 있는 첫 번째(예: 애드핏 번호가 없으면 쿠팡).
        애드핏 광고 단위는 한 페이지에 한 번만 쓴다(같은 ctx 안에서 이미 쓴 단위면 다음 후보로)."""
        if not self.on:
            return None
        v = self.place.get(slot)
        used, no_adfit = self._page_adfit, bool((ctx or {}).get("no_adfit"))
        for one in (v if isinstance(v, list) else [v]):
            if str(one).startswith("adfit_") and (no_adfit or self.adfit_key(one) in used or len(used) >= self.adfit_max):
                continue
            if self.available(one):
                return one
        return None

    def available(self, kind) -> bool:
        if not self.on or not kind or kind == "none":
            return False
        if kind == "adsense_in_article":
            return bool(self.adsense_client and self.adsense_slots.get("in_article"))
        if kind == "adsense_display":
            return bool(self.adsense_client and self.adsense_slots.get("display"))
        if kind == "adfit_report_mid":
            return bool(self.adfit_units.get("report_mid"))
        if kind == "adfit_report_end":
            return bool(self.adfit_units.get("report_end"))
        if kind == "adfit_list":
            return bool(self.adfit_units.get("list") or self.adfit_units.get("report_end"))
        if kind in ("adfit_feed", "adfit_feed2", "adfit_rail", "adfit_bottom"):
            return bool(self.adfit_units.get(self.ADFIT_KEY[kind]))
        if kind == "dable_report":
            return bool(self.dable_service and self.dable_widgets.get("report"))
        if kind == "coupang_banner":
            return bool(self.c_banner)
        if kind == "coupang_products":
            return bool(self.c_products or self.c_auto)
        return False

    def products_for(self, theme: str, exclude_words: list[str]) -> list[dict]:
        items = list(self.c_products.get(theme) or []) + list(self.c_products.get("_default") or [])
        ex = [w.lower() for w in exclude_words if w] + self.c_blocked
        out, seen = [], set()
        for it in items:
            name = str(it.get("name") or "").strip()
            url = str(it.get("url") or "").strip()
            if not name or not url.startswith("https://") or url in seen or self.bad_hosts(url):
                continue
            if any(w in name.lower() for w in ex):
                continue
            seen.add(url)
            out.append({"name": name, "url": url, "image": str(it.get("image") or "").strip()})
            if len(out) >= self.c_per_box:
                break
        return out

    def auto_groups_for(self, theme: str, exclude_words: list[str], skip_theme: str = "") -> list[dict]:
        """테마의 자동 상품 묶음(검색어별). 다룬 회사·금지어 상품은 빼고, 로켓배송 → 쿠팡 순위 순으로 고른다.
        theme="*"이면 모든 테마, skip_theme은 뺄 테마(리포트 본문 상자와 겹치지 않게)."""
        ex = [w.lower() for w in exclude_words if w] + self.c_blocked
        out = []
        common = self.c_auto.get("_common") or []
        if theme == "*":
            src = [g for t, gs in self.c_auto.items() if t not in (skip_theme, "_common") for g in gs] + common
        else:
            # 테마 묶음 + 공통 묶음 4개(상자마다 돌아가며 다른 4개: 페이지가 무거워지지 않게, 학습은 여러 페이지에 걸쳐 쌓인다)
            k = self._common_rot % len(common) if common else 0
            self._common_rot += 4
            src = (self.c_auto.get(theme) or []) + (common[k:] + common[:k])[:4]
        for g in src:
            ex_g = ex + (self.c_book_blocked if "책" in str(g.get("keyword") or "") else [])
            prods = [x for x in g["products"] if not any(w in str(x.get("name", "")).lower() for w in ex_g)]
            prods.sort(key=lambda x: (not x.get("rocket"), int(x.get("rank") or 999)))
            if prods:
                out.append({**g, "products": prods[: self.c_per_box]})
        return out

    @staticmethod
    def _card(it: dict, slot: str, sub: str = "") -> str:
        img = (f'<span class="cp-img"><img src="{html.escape(it["image"])}" alt="" loading="lazy" width="160" height="160"></span>'
               if it.get("image") else "")
        price = f'<span class="cp-price">{int(it["price"]):,}원</span>' if it.get("price") else ""
        rocket = '<span class="cp-rocket">로켓배송</span>' if it.get("rocket") else ""
        sub_attr = f' data-cp-sub="{html.escape(sub)}"' if sub else ""
        return (f'<a class="cp-card" href="{html.escape(it["url"])}" target="_blank" rel="sponsored noopener" '
                f'data-cp-slot="{slot}"{sub_attr}>{img}<span class="cp-name">{html.escape(it["name"])}</span>'
                f'{price}{rocket}<span class="cp-go">쿠팡에서 보기</span></a>')

    def render(self, slot: str, ctx: dict | None = None) -> str:
        """slot의 광고 HTML. 설정이 없으면 빈 문자열."""
        ctx = ctx if ctx is not None else {}
        kind = self.kind(slot, ctx)
        if not self.available(kind):
            return ""
        label = '<div class="ad-label">광고</div>'
        if kind in ("adsense_in_article", "adsense_display"):
            slot_id = self.adsense_slots["in_article" if kind == "adsense_in_article" else "display"]
            attrs = 'data-ad-layout="in-article" data-ad-format="fluid"' if kind == "adsense_in_article" else 'data-ad-format="auto" data-full-width-responsive="true"'
            return (
                f'<aside class="ad ad-adsense" data-slot="{slot}" aria-label="광고">{label}'
                f'<ins class="adsbygoogle" style="display:block;text-align:center" {attrs} '
                f'data-ad-client="{self.adsense_client}" data-ad-slot="{slot_id}"></ins>'
                f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></aside>'
            )
        if kind == "dable_report":
            wid = self.dable_widgets["report"]
            # 데이블 위젯(같이 볼 만한 글 + 광고). 로그·로더 스크립트는 head_tags 에 있다
            return (f'<aside class="ad ad-dable" data-slot="{slot}" aria-label="추천 콘텐츠와 광고">'
                    f'<div id="dablewidget_{wid}" data-widget_id="{wid}"></div>'
                    f'<script>window.dable&&dable("renderWidget","dablewidget_{wid}")</script></aside>')
        if str(kind).startswith("adfit_"):
            key = self.adfit_key(kind)
            self._page_adfit.add(key)
            unit = self.adfit_units.get(key)
            w, h = self.adfit_sizes.get(key, (self.adfit_w, self.adfit_h))
            # PC 오른쪽 칸 상자: 휴대폰처럼 그 칸이 안 보이는 화면에서는 광고를 아예 부르지 않는다(보이지 않는 노출 금지)
            guard = ('<script>(function(a){if(a&&a.offsetParent===null&&a.parentNode)a.parentNode.removeChild(a)})(document.currentScript.parentNode)</script>'
                     if kind == "adfit_rail" else "")
            return (
                f'<aside class="ad ad-adfit" data-slot="{slot}" aria-label="광고" style="min-height:{h + 24}px">{label}'
                f'<ins class="kakao_ad_area" style="display:none;" data-ad-unit="{unit}" '
                f'data-ad-width="{w}" data-ad-height="{h}" data-ad-onfail="kwAdFail"></ins>{guard}'
                f'<script async src="https://t1.daumcdn.net/kas/static/ba.min.js" onerror="this.parentNode.classList.add(\'hidden\')"></script></aside>'
            )
        if kind == "coupang_banner":
            # 쿠팡 배너는 페이지에 바로 넣는다(틀 안에 가두면 쿠팡 스크립트가 주소를 확인하지 못해 빈칸이 됨).
            # 가로 크기가 고정(예: 680)이라 좁은 화면에서는 site.js가 비율대로 줄인다(.cp-banner)
            mw = re.search(r'"width"\s*:\s*"?(\d+)', self.c_banner)
            bw, bh = (int(mw.group(1)) if mw else 680), self.c_banner_h
            # 쿠팡 스크립트가 막히면(광고 차단 등) 오류 없이 상자를 숨긴다
            guarded = self.c_banner.replace("new PartnersCoupang.G(", "window.PartnersCoupang && new PartnersCoupang.G(") + \
                '<script>if(!window.PartnersCoupang){var _a=document.currentScript.closest("aside");if(_a)_a.classList.add("hidden")}</script>'
            return (
                f'<aside class="ad ad-coupang" data-slot="{slot}" aria-label="광고">{label}'
                f'<p class="ad-disclosure">{COUPANG_DISCLOSURE}</p>'
                f'<div class="cp-banner" data-w="{bw}" style="max-width:{bw}px;aspect-ratio:{bw}/{bh}">'
                f'<div class="cp-banner-in" style="width:{bw}px;height:{bh}px">{guarded}</div></div></aside>'
            )
        if kind == "coupang_products":
            groups = self.auto_groups_for(ctx.get("theme", ""), ctx.get("exclude", []), ctx.get("skip_theme", ""))
            # 한 페이지 쿠팡 상자 상한(홈은 2개: 금융 리포트 사이트의 첫인상을 상품이 덮지 않게)
            if ctx.get("cp_max") is not None and int(ctx.get("_cp_n", 0)) >= int(ctx["cp_max"]):
                return ""
            if groups and ctx.get("theme") == "*" and len(groups) > self.CP_GROUPS_MAX:
                # 모든 테마 상자: 상자마다 다른 7개 묶음만 싣는다(전체를 다 실으면 홈 HTML에 숨은 상품이 수백 개).
                # 학습은 여러 상자·페이지에 걸쳐 모든 묶음에 고르게 쌓인다
                k = self._all_rot % len(groups); self._all_rot += self.CP_GROUPS_MAX
                first0 = int(ctx.get("_cp_i", 0)) % len(groups)
                rot = groups[k:] + groups[:k]
                pick = [groups[first0]] + [g for g in rot if g is not groups[first0]][: self.CP_GROUPS_MAX - 1]
                groups = pick
                ctx["_cp_first_override"] = 0
            if groups:
                # 묶음을 모두 넣고, 방문마다 하나를 무작위로 보여 준다(site.js). 스크립트가 없으면 첫 묶음.
                # 가격 기준일은 묶음마다 다르다(검색어마다 받은 날이 다름). 보이는 묶음의 날짜가 함께 보이도록 묶음 안에 둔다.
                # 이 페이지에서 몇 번째 쿠팡 상자인지(앞 자리가 다른 광고면 번호를 당긴다). 스크립트 없어도 상자마다 다른 묶음
                first = int(ctx.get("_cp_i", 0))
                if first >= len(groups) and "_cp_first_override" not in ctx:
                    return ""  # 묶음이 상자 수보다 적으면 같은 상품이 두 번 보이지 않게 이 상자는 뺀다
                ctx["_cp_i"] = first + 1
                if "_cp_first_override" in ctx:
                    first = ctx.pop("_cp_first_override")
                else:
                    # 테마 상자: 보이는 묶음 + 다른 후보 최대 6개(그 테마 묶음을 먼저)
                    groups = [groups[first]] + [g for i, g in enumerate(groups) if i != first][: self.CP_GROUPS_MAX - 1]
                    first = 0
                ctx["_cp_n"] = int(ctx.get("_cp_n", 0)) + 1

                def grp(g, vis):
                    return (f'<div class="cp-group" data-cp-group data-cp-sub="{html.escape(str(g.get("sub_id") or ""))}" data-cp-theme="{html.escape(self.theme_slug.get(g.get("theme"), ""))}" data-cp-date="{str(g.get("date") or "").replace("-", ".")}"{"" if vis else " hidden"}><div class="cp-grid">'
                            + "".join(self._card(it, slot, g["sub_id"]) for it in g["products"]) + "</div></div>")
                # 보이는 묶음만 문서에 두고, 학습용 다른 후보는 <template> 안에(검색엔진·스크립트 없는 화면에는 상품 3개만)
                alts = "".join(grp(g, False) for i, g in enumerate(groups) if i != first)
                inner = grp(groups[first], True) + (f"<template data-cp-alt>{alts}</template>" if alts else "")
                # 가격 기준일 문구는 상자에 한 번. 보이는 묶음이 바뀌면 site.js가 날짜를 바꾼다
                d0 = str(groups[first].get("date") or "").replace("-", ".")
                note = f'<p class="cp-note" data-cp-note{"" if d0 else " hidden"}>가격은 <span>{d0}</span> 기준이며 바뀔 수 있습니다.</p>'
                return (f'<aside class="ad ad-coupang-products" data-slot="{slot}" aria-label="광고">{label}'
                        f'<p class="ad-disclosure">{COUPANG_DISCLOSURE}</p><div class="cp-rot">{inner}</div>{note}</aside>')
            items = self.products_for(ctx.get("theme", ""), ctx.get("exclude", []))
            if not items:
                return ""
            cards = []
            for it in items:
                img = (
                    f'<span class="cp-img"><img src="{html.escape(it["image"])}" alt="" loading="lazy" width="160" height="160"></span>'
                    if it["image"] else ""
                )
                cards.append(
                    f'<a class="cp-card" href="{html.escape(it["url"])}" target="_blank" rel="sponsored noopener" '
                    f'data-cp-slot="{slot}">{img}<span class="cp-name">{html.escape(it["name"])}</span><span class="cp-go">쿠팡에서 보기</span></a>'
                )
            return (
                f'<aside class="ad ad-coupang-products" data-slot="{slot}" aria-label="광고">{label}'
                f'<p class="ad-disclosure">{COUPANG_DISCLOSURE}</p><div class="cp-grid">{"".join(cards)}</div></aside>'
            )
        return ""

    def head_tags(self) -> str:
        out = ""
        if self.on and self.adsense_client:
            out += (
                '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
                f'{self.adsense_client}" crossorigin="anonymous"></script>'
            )
        if self.on and self.dable_service:
            # 데이블 기본 설치 코드: 모든 페이지에서 방문 로그를 한 번 보내 추천 학습에 쓰고, 위젯은 자리에서 그린다
            out += ("<script>(function(d,a,b,l,e,_){d[b]=d[b]||function(){(d[b].q=d[b].q||[]).push(arguments)};"
                    "e=a.createElement(l);e.async=1;e.charset='utf-8';e.src='//static.dable.io/dist/plugin.min.js';"
                    "_=a.getElementsByTagName(l)[0];_.parentNode.insertBefore(e,_);})(window,document,'dable','script');"
                    f"dable('setService','{self.dable_service}');dable('sendLogOnce');</script>")
        return out

    def ads_txt(self) -> str:
        lines = ["# KimWorld ads.txt"]
        if self.adsense_client:
            lines.append(f"google.com, {self.adsense_client.replace('ca-', '')}, DIRECT, f08c47fec0942fa0")
        lines += self.ads_txt_extra
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 빌드

SERIES_RE = re.compile(r"\s*\|\s*(주가|가격) 내러티브와 패턴 투자전략\s*$")


def seo_fields(r: dict) -> dict:
    """검색 결과 제목용: '<한글 이름>(<티커>) 주가 분석 — <훅>'. 사람들이 치는 말(이름·티커·주가)을 맨 앞에 둔다."""
    t = r["title"].strip()
    kind = "가격" if "가격 내러티브" in t else "주가"
    t = SERIES_RE.sub("", t)
    name, hook = "", t
    m = re.match(r"^(.+?)\s+(?:주가|가격) 내러티브와 패턴 투자전략\s*[:：]\s*(.+)$", t)
    if m:
        name, hook = m.group(1).strip(), m.group(2).strip()
    else:
        m = re.match(r"^([^,，]{1,20})[,，]\s*(.+)$", t)
        if m:
            name, hook = m.group(1).strip(), m.group(2).strip()
    name = name or r["company"] or r["ticker"]
    head = name if name.upper() == r["ticker"].upper() else f"{name}({r['ticker']})"
    # 공유 미리보기(카카오톡·쓰레드·X)용: 검색 제목처럼 길게 쓰지 않고 '이름, 훅' 한 줄. 설명은 요약 앞 문장 + 무료 안내
    share_title = hook if hook.startswith(name) else f"{name}, {hook}"
    summ = re.sub(r"\s+", " ", str(r.get("summary") or "")).strip()
    sents = re.findall(r".+?[.?!](?=\s|$)", summ) or [summ]  # "3.3배"의 점은 문장 끝이 아니다
    desc = ""
    for x in sents:
        if len(desc) + len(x) > 92 and desc:
            break
        desc = (desc + " " + x.strip()).strip()
    if len(desc) > 100:
        desc = desc[:98].rstrip() + "…"
    return {"seo_name": name, "seo_kind": kind, "seo_title": f"{head} {kind} 분석 — {hook}", "seo_hook": hook,
            "share_title": share_title, "share_desc": f"{desc} 무료로 전문 보기"}


def build(drafts=False, strict=False, out: Path = DIST):
    log = Log()
    site = load_yaml(ROOT / "site.yaml", {})
    # 도메인 연결 전에는 워크플로가 SITE_URL 에 github.io 주소를 넣어 준다(그 주소에서도 화면이 깨지지 않게)
    site["site_url"] = str(os.environ.get("SITE_URL") or site.get("site_url", "")).rstrip("/")
    base_path = urlparse(site["site_url"]).path.rstrip("/")  # GitHub Pages 프로젝트 주소면 /kimworld-site
    ads = Ads(load_yaml(ROOT / "ads.yaml", {}), log)
    themes = load_yaml(ROOT / "data" / "themes.yaml", [])
    theme_by_name = {t["name"]: t for t in themes}
    ads.theme_slug = {"_common": "common", **{t["name"]: t["slug"] for t in themes}}
    tickers = load_yaml(ROOT / "data" / "tickers.yaml", {})
    glossary = load_yaml(ROOT / "data" / "glossary.yaml", [])
    today = dt.datetime.now(KST).date()

    # ---- 리포트 읽기
    reports = []
    for p in sorted((ROOT / "content" / "reports").glob("*.md")):
        if p.name.startswith("_"):
            continue
        slug = p.stem
        name = f"content/reports/{p.name}"
        try:
            meta, body = parse_front(p)
        except Exception as e:
            log.err(str(e))
            continue
        if not SLUG_RE.match(slug):
            log.err(f"{name}: 파일 이름은 영문 소문자·숫자·하이픈만 씁니다(예: rgti-2026-10)")
            continue
        missing = [k for k in REQUIRED if meta.get(k) in (None, "", [])]
        if missing:
            log.err(f"{name}: 필수 항목 없음 → {', '.join(missing)}")
            continue
        ticker = str(meta["ticker"]).upper()
        if ticker not in tickers:
            log.err(f"{name}: ticker {ticker} 가 data/tickers.yaml 에 없습니다")
            continue
        if meta["theme"] not in theme_by_name:
            log.err(f"{name}: theme '{meta['theme']}' 가 data/themes.yaml 에 없습니다")
            continue
        for k in ("holding", "holding_detail"):
            if k in meta:
                log.err(f"{name}: '{k}' 항목은 쓰지 않습니다(운영자 보유 여부는 공개하지 않음)")
        try:
            d, upd, asof = to_date(meta["date"]), to_date(meta.get("updated")), to_date(meta["data_as_of"])
        except Exception:
            log.err(f"{name}: 날짜는 YYYY-MM-DD 형식")
            continue
        sources = meta.get("sources") or []
        for i, s in enumerate(sources):
            if not isinstance(s, dict) or not s.get("title"):
                log.err(f"{name}: sources[{i}] 에 title 이 없습니다")
            elif s.get("url") and not re.match(r"https?://[^\s\"'<>]+$", str(s["url"])):
                log.err(f"{name}: sources[{i}] 주소는 http(s):// 로 시작하는 정상 주소여야 합니다")
        # 보안: 리포트 본문에 스크립트·외부 틀·이벤트 속성·위험한 링크를 넣지 못하게 한다(조사 중 섞여 들어온 악성 내용 차단)
        for pat, why in ((r"<\s*(script|iframe|object|embed|form|meta|link|style|base)\b", "실행·삽입 태그"),
                         (r"\son[a-z]+\s*=", "이벤트 속성(on...=)"),
                         (r"(\]\(|<|href\s*=\s*[\"']?|src\s*=\s*[\"']?)\s*(javascript|vbscript|data)\s*:", "위험한 링크 주소")):
            if re.search(pat, body, flags=re.I):
                log.err(f"{name}: 본문에 허용하지 않는 {why}가 있습니다")
        is_draft = bool(meta.get("draft"))
        if is_draft and not drafts:
            continue
        if d > today and not drafts:
            continue  # 예약 공개: 날짜가 되면 다음 빌드에 나타난다
        sponsor = meta.get("sponsor")
        # 협찬 글은 맨 위 [광고] 표시만 의무(표시·광고법). 다룬 회사가 협찬해도 표시하면 법적 금지는 아니다
        for ph in site.get("lint", {}).get("banned_phrases", []):
            if ph in body or ph in str(meta.get("title")) or ph in str(meta.get("summary")):
                log.err(f"{name}: 금지 표현 '{ph}'")
        md = md_renderer()
        body_html, n_figs = add_figures(wrap_tables(md.convert(fix_list_breaks(body))))  # 본문 그림(report_figures.py)
        body_html = shape_for_reading(fold_event_cards(body_html))
        # 차트 이미지는 눌러서 원본 크기로 볼 수 있게(모바일에서 글자가 작다)
        body_html = re.sub(r'(<img [^>]*src="(/static/charts/[^"]+)"[^>]*>)',
                           lambda m: f'<a class="chart-link" href="{m.group(2)[:-4] + ".view.png" if m.group(2).endswith(".png") else m.group(2)}" target="_blank" rel="noopener" aria-label="차트 크게 보기">{m.group(1)}</a>', body_html)
        toc = [t for t in md.toc_tokens]
        chars = plain_len(body_html)
        min_chars = int(site.get("lint", {}).get("min_chars", 0))
        if not is_draft and chars < min_chars:
            log.warn(f"{name}: 본문이 짧습니다({chars}자 < {min_chars}자)")
        if not is_draft and len(sources) < 2:
            log.warn(f"{name}: 출처가 2개 미만입니다")
        tk = tickers[ticker]
        reports.append({
            "slug": slug, "ticker": ticker, "company": tk.get("name", ""), "company_en": tk.get("name_en", ""),
            "exchange": tk.get("exchange", ""), "aliases": tk.get("aliases", []),
            "title": str(meta["title"]), "theme": meta["theme"], "theme_slug": theme_by_name[meta["theme"]]["slug"],
            "date": d, "updated": upd, "data_as_of": asof, "summary": str(meta["summary"]).strip(),
            "key_points": [str(x) for x in (meta.get("key_points") or [])][:5],
            "chart": chart_info(slug),
            "youtube_id": str(meta.get("youtube_id") or "").strip(),
            "sources": sources, "sponsor": sponsor if isinstance(sponsor, dict) else None,
            "draft": is_draft, "body_html": body_html, "toc": toc, "chars": chars,
            "minutes": max(1, math.ceil(chars / 600)), "url": f"{base_path}/r/{slug}/",
            "body_md": body, "short_answer": short_answer(body),
        })
        reports[-1].update(seo_fields(reports[-1]))
        if reports[-1]["youtube_id"] and not re.fullmatch(r"[A-Za-z0-9_-]{11}", reports[-1]["youtube_id"]):
            log.err(f"{name}: youtube_id 는 11자리 영상 ID")

    reports.sort(key=lambda r: (r["date"], r["slug"]), reverse=True)
    public = [r for r in reports if not r["draft"]]

    # ---- 관계 계산
    by_ticker: dict[str, list] = {}
    for r in public:
        by_ticker.setdefault(r["ticker"], []).append(r)
    for r in reports:
        same = by_ticker.get(r["ticker"], [])
        r["ticker_reports"] = [x for x in same if x is not r]
        newer = [x for x in same if x["date"] > r["date"]]
        r["newer"] = newer[-1] if newer else None
        r["related"] = [x for x in public if x["theme"] == r["theme"] and x["ticker"] != r["ticker"]][:4]
        # 목차에서 찾아 두는 자리: 리스크·체크리스트(요약 상자 바로가기), 영상에서 다 못 다룬 뒷부분(유튜브에서 온 독자 바로가기)
        flat = []
        for t in r["toc"]:
            flat.append(t); flat.extend(t.get("children") or [])
        r["check_id"] = next((t["id"] for t in flat if "체크리스트" in t["name"]), "") or next((t["id"] for t in flat if "리스크" in t["name"]), "")
        r["yt_jump"] = [t for t in r["toc"] if re.match(r"^[3-6]부", t["name"])][:4] or r["toc"][2:6]
        r["has_diag"] = 'id="diagnosis"' in r["body_html"]
        # 영상이 던진 질문(요약 끝 문장)과 답이 나오는 소제목: 유튜브 독자 바로가기 줄 맨 앞에
        r["yt_q"], r["yt_ans_id"] = video_question(r["summary"], r["body_html"]) if r["youtube_id"] else ("", "")
        if r["yt_q"] and not r["yt_ans_id"]:
            r["yt_ans_id"] = next((t["id"] for t in r["toc"] if t["name"].strip() == "짧은 답"), "")
        # SNS 글이 묻는 '몇 번?'의 답이 있는 3부 소제목(운영자 지시 2026-10-20 SNS 퍼널: 질문 → 답으로 바로)
        r["answer_id"] = next((t["id"] for t in flat if re.search(r"무너진 날|거래일 뒤|몇 번", t["name"])), "")
        idx = public.index(r) if r in public else -1
        r["prev"] = public[idx + 1] if idx >= 0 and idx + 1 < len(public) else None
        r["next"] = public[idx - 1] if idx > 0 else None

    # ---- 출력 준비
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "static", out / "static")
    # 대표 차트(흰 배경 원본)를 검은 화면용 투명 배경 차트로(chart_dark.py, 원본은 그대로·공유 그림은 원본 사용)
    import chart_dark
    chart_dark.convert_all(ROOT / "static" / "charts", out / "static" / "charts")

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "xml"]))
    env.filters["kdate"] = lambda d: f"{d.year}년 {d.month}월 {d.day}일" if d else ""
    env.filters["iso"] = lambda d: d.isoformat() if d else ""
    env.filters["seo_items"] = lambda slugs, su: [{"@type": "ListItem", "position": i + 1, "url": f"{su}/r/{x}/"} for i, x in enumerate(slugs)]
    asset_ver = str(int(dt.datetime.now().timestamp()))
    common = {
        "site": site, "base": base_path, "themes": themes, "ads": ads, "ads_head": ads.head_tags(),
        "asset_ver": asset_ver, "year": today.year, "tickers": tickers,
        "COUPANG_PAGE_NOTICE": COUPANG_PAGE_NOTICE,
        # 종토방이 있는 종목(리포트가 있는 종목). 글 속 $TSLA 링크와 글쓰기 상자에 쓴다
        "board_ticks": [{"c": c, "n": (tickers.get(c) or {}).get("name", ""),
                         "s": next((t["slug"] for t in themes if t["name"] == (tickers.get(c) or {}).get("theme")), "")} for c in sorted(by_ticker)],
    }

    def write(rel: str, tpl: str, **ctx):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        page_url = site["site_url"] + "/" + rel.replace("index.html", "")
        html_out = env.get_template(tpl).render(**common, page_url=page_url, **ctx)
        if base_path:  # 본문 마크다운의 /static/…, /disclaimer/ 같은 링크에도 하위 경로를 붙인다
            html_out = re.sub(r'((?:href|src|action)=")/(?!/)(?!' + re.escape(base_path.lstrip("/")) + r'/)',
                              r"\1" + base_path + "/", html_out)
        dest.write_text(html_out, encoding="utf-8")

    # ---- 리포트 페이지
    og_dir = out / "og"
    og_dir.mkdir()
    og_font = find_font()
    for r in reports:
        ads.begin_page()
        body, used_terms = apply_glossary(r["body_html"], glossary)
        body = insert_mid_next(body, *mid_next_pick(r))
        exclude = []  # 리포트에서 다룬 회사의 상품도 광고에 나올 수 있다(법적 제한 없음)
        ad_ctx = {"theme": r["theme"], "exclude": exclude}
        pieces = []
        mid_html = ads.render("report_mid", ad_ctx)
        prod_html = ads.render("report_products", ad_ctx)
        # 긴 리포트(본문 1만 5천 자 이상)만 4분의 3 지점에 한 자리 더. 본문 상자와 겹치지 않게 다른 테마 상품에서
        far_ctx = {"theme": "*", "skip_theme": r["theme"], "exclude": exclude}
        late_html = ads.render("report_late", far_ctx) if r["chars"] >= 15000 else ""
        slot_html = {"report_mid": mid_html, "report_products": prod_html, "report_late": late_html}
        for kind, val in split_for_ads(body, bool(mid_html), bool(prod_html), bool(late_html)):
            if kind == "html":
                pieces.append(val)
            else:
                pieces.append(slot_html[val])
        # 넓은 화면 오른쪽 목차 아래에 따라 내려오는 상자(휴대폰에서는 안 보임)
        rail_html = ads.render("rail", far_ctx)
        end_html = ads.render("report_recommend", ad_ctx) + ads.render("report_end", ad_ctx)
        bottom_html = "" if r["sponsor"] else ads.render("report_bottom", ad_ctx)
        page_bottom = "" if r["sponsor"] else ads.render("page_bottom", {**ad_ctx, "no_adfit": True})  # 바로 위가 애드핏 하단 상자라 애드핏을 붙여 두지 않는다
        used_ads = [x for x in pieces if x.startswith('<aside class="ad')] + [x for x in (end_html, bottom_html) if x]
        has_coupang = any("ad-coupang" in x for x in used_ads)
        og_rel = f"og/{r['slug']}.png"
        r["og_image"] = f"{site['site_url']}/{og_rel}" if make_og(og_dir / f"{r['slug']}.png", r, site, og_font) else f"{site['site_url']}/static/og-default.png"
        # 댓글 사이 광고(댓글이 쌓였을 때만 화면에서 끼워 넣음): 다른 테마 상품 묶음에서 골라 본문 상자와 겹치지 않게
        thread_ad = ads.render("thread_inline", {"theme": "*", "skip_theme": r["theme"], "exclude": exclude})
        write(f"r/{r['slug']}/index.html", "report.html", r=r, body_pieces=pieces, end_ad=end_html, thread_ad=thread_ad, rail_ad=rail_html,
              bottom_ad=bottom_html, page_bottom=page_bottom, has_coupang=has_coupang, terms=used_terms, today=today,
              stale=(today - r["data_as_of"]).days > int(site.get("stale_days", 180)))

    # ---- 종목·테마·홈·검색
    ticker_list = []
    for code, rs in sorted(by_ticker.items(), key=lambda kv: kv[1][0]["date"], reverse=True):
        t = tickers[code]
        ticker_list.append({"code": code, "name": t.get("name"), "count": len(rs), "last": rs[0]["date"], "theme": t.get("theme")})
        tex = [code, t.get("name", ""), t.get("name_en", ""), *(t.get("aliases") or [])]
        ads.begin_page()
        write(f"t/{code.lower()}/index.html", "ticker.html", code=code, t=t, rs=rs,
              list_ad=ads.render("list", {"theme": t.get("theme", "")}), page_bottom=ads.render("page_bottom", {}),
              thread_ad=ads.render("thread_inline", {"theme": "*"}))
    for th in themes:
        rs = [r for r in public if r["theme"] == th["name"]]
        ads.begin_page()
        write(f"theme/{th['slug']}/index.html", "theme.html", th=th, rs=rs, list_ad=ads.render("list", {"theme": th["name"]}), page_bottom=ads.render("page_bottom", {}))
    ads.begin_page()
    home_ctx = {"theme": "*", "cp_max": 2}  # 같은 ctx를 이어 써서 피드 광고마다 다른 상품 묶음
    home_list = ads.render("list", home_ctx)
    hf = ads.rhythm["home_feed"]
    feed_ads = [x for x in (ads.render("feed_inline", home_ctx) for _ in range(max(0, hf["max"] - 1))) if x]
    home_rail = ads.render("rail", home_ctx)
    write("index.html", "index.html", rs=public, ticker_list=ticker_list, list_ad=home_list, feed_ads=feed_ads,
          feed_first=hf["first"], feed_every=hf["every"], rail_ad=home_rail,
          page_bottom=ads.render("page_bottom", home_ctx), is_home=True,
          feed_more_ad=ads.render("thread_inline", {"theme": "*"}))  # '글 더 보기'로 이어 불러온 글 사이(애드센스·쿠팡만, 애드핏은 정책상 불가)
    ads.begin_page()
    ex_ctx = {"theme": "*"}
    write("search/index.html", "search.html", rs=public, ticker_list=ticker_list, explore_ad=ads.render("explore", ex_ctx),
          explore_inline=ads.render("explore_inline", {"theme": "*"}), page_bottom=ads.render("page_bottom", {}))
    if site.get("api_url"):
        ads.begin_page()
        write("u/index.html", "user.html", profile_ad=ads.render("profile_inline", {"theme": "*"}), page_bottom=ads.render("page_bottom", {}))
        ads.begin_page()
        write("dm/index.html", "dm.html", dm_ad=ads.render("dm_list", {"theme": "*"}))  # 쪽지함(화면에서 API로 채움, 검색 노출 안 함)  # 이용자 프로필(화면에서 API로 채움, 검색 노출 안 함)
        # 글 상세(종토방·라운지 글 하나와 답글). 답글 사이 광고는 종토방과 같은 리듬
        write("settings/index.html", "settings.html")  # 설정(푸시 알림·쪽지 받기·글자 크기·앱·계정). 아래 탭 줄 '설정'
        write("admin/index.html", "admin.html")  # 운영 통계(운영자 계정만 API가 자료를 준다, 검색 노출·링크 없음)
        pd_ctx = {"theme": "*"}
        ads.begin_page()
        write("p/index.html", "post.html", thread_ad=ads.render("thread_inline", {"theme": "*"}), rhythm=ads.rhythm["board"],
              post_ad=ads.render("post_detail", pd_ctx), page_bottom=ads.render("page_bottom", {}))
    write("404.html", "404.html")

    # ---- 고정 페이지
    pages = []
    op = site.get("operator", {})
    repl = {
        "{{site_name}}": site.get("site_name", ""),
        "{{channel_name}}": op.get("display_name") or site.get("site_name", ""),
        "{{youtube_url}}": op.get("youtube_url") or "#",
        "{{report_count}}": str(len(reports)),
        "{{theme_count}}": str(len({r["theme"] for r in reports})),
    }
    # 발행·갱신 기록(최근 40건): 사이트가 꾸준히 관리된다는 것을 독자·검색엔진이 볼 수 있게
    _log = sorted(public, key=lambda r: (r["updated"] or r["date"], r["date"]), reverse=True)[:40]
    _kd = lambda d: f"{d.year}.{d.month:02d}.{d.day:02d}"
    repl["{{recent_updates}}"] = "\n".join(
        f'- {_kd(r["updated"] or r["date"])} · {"갱신" if r["updated"] else "새 리포트"} · [{r["ticker"]} {html.escape(r.get("seo_name") or r.get("company") or "")}]({r["url"]}) — 숫자 기준 {_kd(r["data_as_of"])}, 출처 {len(r.get("sources") or [])}개'
        for r in _log)
    repl["{{public_count}}"] = str(len(public))
    repl["{{source_total}}"] = str(sum(len(r.get("sources") or []) for r in public))
    # 광고·제휴 문의 메일(도메인 역할 주소, 운영자 개인 메일 아님). 화면에는 '＠'로 적고 site.js가 눌렀을 때 진짜 주소로 바꾼다(주소 수집 로봇 막기)
    _yt_fallback = f'[{op.get("display_name") or site.get("site_name", "")} 유튜브 채널]({op.get("youtube_url") or "#"})의 댓글'

    def _mail_link(addr):
        _u, _d = addr.split("@", 1)
        return f'<a class="mail-link" href="#" data-u="{html.escape(_u)}" data-d="{html.escape(_d)}">{html.escape(_u)}＠{html.escape(_d)}</a>'

    _contact = site.get("contact") or {}
    _mail_on = {}
    for _key in ("ads_email", "contact_email", "privacy_email"):
        _cm = str(_contact.get(_key) or "").strip()
        _mail_on[_key] = bool(_cm and "@" in _cm and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", _cm))
        repl["{{" + _key + "}}"] = _mail_link(_cm) if _mail_on[_key] else _yt_fallback
    _ads_mail_on = _mail_on["ads_email"]
    page_flags = {
        "ga4": bool((site.get("analytics") or {}).get("ga4_id")),
        "dable": bool(ads.on and ads.dable_service),
        "adsmail": _ads_mail_on,
        "noadsmail": not _ads_mail_on,
        "contactmail": _mail_on["contact_email"],
        "nocontactmail": not _mail_on["contact_email"],
        "privacymail": _mail_on["privacy_email"],
        "noprivacymail": not _mail_on["privacy_email"],
        "newsletter": bool((site.get("newsletter") or {}).get("url")),
        "api": bool(site.get("api_url")),
    }
    for p in sorted((ROOT / "content" / "pages").glob("*.md")):
        meta, body = parse_front(p)
        for k, v in repl.items():
            body = body.replace(k, v)
        # 줄 끝에 <!--if:이름--> 이 붙은 줄은 그 기능을 켰을 때만 남긴다(안 쓰는 서비스를 방침·고지에 적지 않기 위해)
        body = "\n".join(ln for ln in body.split("\n")
                         if not (m := re.search(r"<!--if:(\w+)-->", ln)) or page_flags.get(m.group(1)))
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        html_body = wrap_tables(md_renderer().convert(body), "table-text")
        pages.append({"slug": p.stem, "title": meta.get("title", p.stem)})
        ads.begin_page()
        write(f"{p.stem}/index.html", "page.html", p={"title": meta.get("title"), "description": meta.get("description", ""),
              "updated": to_date(meta.get("updated")), "html": html_body}, page_bottom=ads.render("page_bottom", {}))

    # ---- 검색 색인, 피드, 사이트맵, 기타
    index = [{
        "u": r["url"], "t": r["title"], "k": r["ticker"], "c": r["company"], "e": r["company_en"],
        "a": r["aliases"], "th": r["theme"], "ts": r["theme_slug"], "s": r["summary"], "d": r["date"].isoformat(),
        "st": r.get("share_title") or "", "ch": (r.get("chart") or {}).get("src", ""),
    } for r in public]
    (out / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "ad-weights.json").write_text(json.dumps(ad_weights(ads), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    su = site["site_url"]
    seo = site.get("seo") or {}
    theme_last = {}
    for r in public:
        theme_last.setdefault(r["theme"], r["updated"] or r["date"])
    # (주소, 마지막 수정일, 대표 이미지). 리포트가 없는 테마 페이지는 내용이 없으므로 넣지 않는다(noindex)
    urls = [(f"{su}/", today, None)] + [(f"{su}/r/{r['slug']}/", r["updated"] or r["date"], r.get("og_image")) for r in public]
    # 종목 화면은 리포트가 2개 이상일 때만(1개면 리포트와 거의 같은 내용이라 noindex, ticker.html)
    urls += [(f"{su}/t/{c.lower()}/", max(x["updated"] or x["date"] for x in rs), None) for c, rs in by_ticker.items() if len([x for x in rs if not x["draft"]]) >= 2]
    urls += [(f"{su}/theme/{t['slug']}/", theme_last[t["name"]], None) for t in themes if t["name"] in theme_last]
    urls += [(f"{su}/{p['slug']}/", None, None) for p in pages]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for u, lm, img in urls:
        sm.append(f"<url><loc>{html.escape(u)}</loc>" + (f"<lastmod>{lm.isoformat()}</lastmod>" if lm else "")
                  + (f"<image:image><image:loc>{html.escape(img)}</image:loc></image:image>" if img else "") + "</url>")
    sm.append("</urlset>")
    (out / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")

    items = []
    for r in public[:50]:
        pub = dt.datetime.combine(r["date"], dt.time(9, 0), KST)
        items.append(
            f"<item><title>{html.escape(r['seo_title'])}</title><link>{su}/r/{r['slug']}/</link>"
            f"<guid isPermaLink=\"true\">{su}/r/{r['slug']}/</guid><pubDate>{format_datetime(pub)}</pubDate>"
            f"<category>{html.escape(r['theme'])}</category><category>{html.escape(r['ticker'])}</category>"
            f"<description>{html.escape(r['summary'])}</description></item>"
        )
    last = dt.datetime.combine(public[0]["date"], dt.time(9, 0), KST) if public else dt.datetime.now(KST)
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{html.escape(site['site_name'])}</title><link>{su}/</link>"
        f'<atom:link href="{su}/rss.xml" rel="self" type="application/rss+xml"/>'
        f"<description>{html.escape(site.get('description', ''))}</description><language>ko</language>"
        f"<lastBuildDate>{format_datetime(last)}</lastBuildDate>"
        + "".join(items) + "</channel></rss>"
    )
    (out / "rss.xml").write_text(rss, encoding="utf-8")
    # AI 답변 엔진(챗GPT·클로드·퍼플렉시티·제미나이·코파일럿·애플)과 검색엔진 수집기를 이름으로 분명히 허용한다(운영자 결정 2026-10-15: AI 답변 노출 극대화)
    ai_bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai", "PerplexityBot", "Perplexity-User",
               "Google-Extended", "Applebot-Extended", "Amazonbot", "meta-externalagent", "DuckAssistBot", "MistralAI-User", "cohere-ai"]
    # /search/<무엇> 은 예전 도메인 주인이 남긴 스팸 주소(서치 콘솔 2026-10-19 확인: 영양제 이름 등, 지금은 404).
    # 새 사이트의 적은 크롤링 몫을 그 주소들에 쓰지 않게 막는다. 우리 검색 화면(/search/)은 허용(그 화면은 원래 noindex)
    rules = "Allow: /\nAllow: /search/$\nAllow: /search/?\nDisallow: /search/\nDisallow: /admin/\nDisallow: /dm/\nDisallow: /settings/\n"
    # 일반 검색엔진은 HTML 리포트만 색인한다(마크다운 사본 /r/*.md 는 원본 표시를 달 수 없어 '중복'으로 잡히지 않게 막는다)
    search_bots = ["Googlebot", "Bingbot", "Yeti", "Daum", "Applebot"]
    robots = ("".join(f"User-agent: {b}\n" for b in ai_bots) + rules
              + "\n" + "".join(f"User-agent: {b}\n" for b in search_bots) + rules + "Disallow: /r/*.md$\n"
              + "\nUser-agent: *\n" + rules + "Disallow: /r/*.md$\n" + f"\nSitemap: {su}/sitemap.xml\nSitemap: {su}/rss.xml\n")
    if seo.get("daum_webmaster_pin"):  # 다음 웹마스터도구 소유 확인 줄(공개값)
        robots += f"\n#DaumWebMasterTool:{seo['daum_webmaster_pin']}\n"
    (out / "robots.txt").write_text(robots, encoding="utf-8")
    # ---- AI 답변 엔진용: /llms.txt(사이트 안내 + 리포트 목록) · /r/<slug>.md(리포트 원문 마크다운)
    def md_clean(t: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", t).strip()
    for r in public:
        head = [f"# {r['title']}", "",
                f"- 종목: {r['company']} ({r['ticker']}, {r['exchange']}) · 테마: {r['theme']}",
                f"- 공개: {r['date'].isoformat()} · 숫자 기준일: {r['data_as_of'].isoformat()}" + (f" · 갱신: {r['updated'].isoformat()}" if r.get('updated') else ""),
                f"- 원문: {su}/r/{r['slug']}/", f"- 출처 표기: 김박사 월드(drkimworld.com)", "", f"> {r['summary']}", ""]
        if r["key_points"]:
            head += ["## 핵심 요약", ""] + [f"- {k}" for k in r["key_points"]] + [""]
        tail = ["", "## 출처", ""] + [f"- [{x.get('title', '')}]({x.get('url', '')})" + (f" ({x.get('date')})" if x.get("date") else "") for x in r["sources"] if isinstance(x, dict)]
        tail += ["", "---", "이 글은 공개 자료를 정리한 정보 제공용 분석이며 특정 종목의 매수·매도를 권유하지 않습니다."]
        (out / "r" / f"{r['slug']}.md").write_text(md_clean("\n".join(head) + "\n" + r["body_md"] + "\n" + "\n".join(tail)) + "\n", encoding="utf-8")
    llm = [f"# {site.get('site_name')} ({site.get('site_name_en', '')})", "",
           f"> {site.get('description', '')}", "",
           "김박사 월드는 미국 성장·테마주(양자컴퓨팅, AI 반도체, 우주항공, 휴머노이드, 원자력, 코인 등)를 회사 공시(SEC 8-K·10-Q 등)·실적·주요 언론 보도로 분석한 한국어 무료 리포트 사이트입니다. "
           "각 리포트는 주가를 움직인 이벤트를 날짜·반응 폭과 함께 정리하고, 반복된 패턴과 지금 국면을 설명합니다. 모든 숫자에는 기준일이 있고, 출처 목록이 붙어 있습니다.",
           "", "인용할 때는 '김박사 월드(drkimworld.com)'와 리포트 주소를 함께 밝혀 주세요. 투자 권유가 아닌 정보 제공용 분석입니다.", "",
           "## 리포트(최신순, 마크다운 원문 링크)", ""]
    for r in public:
        llm.append(f"- [{r['company']}({r['ticker']}) · {r['title']}]({su}/r/{r['slug']}.md): {r['summary']} (공개 {r['date'].isoformat()}, 숫자 기준 {r['data_as_of'].isoformat()})")
    llm += ["", "## 종목·테마 목록", ""]
    for tk in sorted({r["ticker"] for r in public}):
        rr = [r for r in public if r["ticker"] == tk][0]
        llm.append(f"- [{rr['company']} ({tk})]({su}/t/{tk.lower()}/)")
    llm += ["", "## 기타", "", f"- [사이트 소개]({su}/about/)", f"- [면책 고지]({su}/disclaimer/)", f"- [사이트맵]({su}/sitemap.xml)", f"- [RSS]({su}/rss.xml)"]
    (out / "llms.txt").write_text("\n".join(llm) + "\n", encoding="utf-8")
    key = str(seo.get("indexnow_key") or "")
    if re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):  # IndexNow 키 파일(공개값): 빙·네이버에 새 글을 바로 알린다
        (out / f"{key}.txt").write_text(key, encoding="utf-8")
    (out / "ads.txt").write_text(ads.ads_txt(), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    # 웹앱(홈 화면에 설치): 앱 정보 + 서비스 워커(오프라인 대비, 정적 파일 캐시) + 오프라인 안내 페이지
    manifest = {
        "id": f"{base_path}/", "name": site["site_name"], "short_name": site["site_name"], "description": site.get("description", ""),
        "start_url": f"{base_path}/?utm_source=pwa&utm_medium=app", "scope": f"{base_path}/", "display": "standalone",
        "background_color": "#000000", "theme_color": "#000000", "lang": "ko", "dir": "ltr", "categories": ["finance", "news"],
        "icons": [
            {"src": f"{base_path}/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": f"{base_path}/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": f"{base_path}/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            {"src": f"{base_path}/static/badge-96.png", "sizes": "96x96", "type": "image/png", "purpose": "monochrome"},  # 알림·테마 아이콘용 단색
            {"src": f"{base_path}/static/icon.svg", "sizes": "any", "type": "image/svg+xml"},
        ],
        "shortcuts": [
            {"name": "검색", "url": f"{base_path}/search/", "icons": [{"src": f"{base_path}/static/icon-192.png", "sizes": "192x192"}]},
            {"name": "글쓰기", "url": f"{base_path}/?compose=1", "icons": [{"src": f"{base_path}/static/icon-192.png", "sizes": "192x192"}]},
        ],
    }
    (out / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    sw = (ROOT / "static" / "js" / "sw.template.js").read_text(encoding="utf-8")
    (out / "sw.js").write_text(sw.replace("__VER__", asset_ver).replace("__BASE__", base_path).replace("__API__", str(site.get("api_url") or "").rstrip("/")), encoding="utf-8")
    write("offline/index.html", "offline.html")
    host = urlparse(su).hostname or ""
    if host and not host.endswith("github.io"):
        (out / "CNAME").write_text(host + "\n", encoding="utf-8")
    make_default_og(out / "static" / "og-default.png", site, og_font)
    # 종토방·라운지 글 공유 그림(API의 /s/p/번호 공유 미리보기가 쓴다)
    for t in ticker_list + [{"code": "talk", "name": "라운지"}]:
        make_board_og(og_dir / f"b-{str(t['code']).lower()}.png", str(t["code"]), str(t.get("name") or t["code"]), og_font)

    # ---- 결과
    for w in log.warnings:
        print("⚠️ ", w)
    for e in log.errors:
        print("❌", e)
    print(f"리포트 {len(public)}개 공개" + (f", 초안 {len(reports) - len(public)}개" if drafts else "") + f" → {out}")
    if log.errors or (strict and log.warnings):
        raise SystemExit(1)
    return {"reports": reports, "log": log}


# ---------------------------------------------------------------- 공유 이미지

def find_font():
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if Path(p).exists():
            return p
    return None


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= width:
            cur += ch
        else:
            # 가능하면 공백에서 줄바꿈
            cut = cur.rfind(" ")
            if cut > len(cur) * 0.6:
                lines.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


OG_BG, OG_AMBER, OG_INK = "#0b1220", "#f59e0b", "#0b1220"
_HL = re.compile(r"\d|반토막|[두세네다섯]\s*배|배가|분의|최고|최저|급등|급락")


def _og_words(d, text, font, maxw):
    """한 줄씩 단어를 채운다. 반환: [[단어, ...], ...]"""
    lines, cur = [], []
    for w in text.split():
        trial = " ".join(cur + [w])
        if cur and d.textlength(trial, font=font) > maxw:
            lines.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _og_base(W=1200, H=630):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), OG_BG)
    d = ImageDraw.Draw(img)
    for y in range(H):  # 위→아래로 아주 옅게 밝아지는 배경
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(11 + 8 * t), int(18 + 10 * t), int(32 + 16 * t)))
    return img, d


def _og_brand(img, d, font, x, y):
    from PIL import Image
    ic = ROOT / "static" / "icon-192.png"
    if ic.exists():
        with Image.open(ic) as im:
            im = im.convert("RGBA").resize((44, 44))
            img.paste(im, (x, y), im)
        x += 58
    d.text((x, y + 4), "김박사 월드", font=font, fill="#cbd5e1")


def _og_cta(d, font, x, y, text="무료 리포트 전문 보기 →"):
    tw = d.textlength(text, font=font)
    d.rounded_rectangle([x, y, x + tw + 56, y + 68], radius=34, fill=OG_AMBER)
    d.text((x + 28, y + 13), text, font=font, fill=OG_INK)
    return x + tw + 56


def make_og(dest: Path, r: dict, site: dict, font_path) -> bool:
    """공유 미리보기 그림(1200×630, 카카오톡·쓰레드·X·페이스북 공통 1.91:1).
    작은 화면에서도 읽히게 훅을 크게, 숫자는 강조색, 오른쪽에 리포트 차트 일부, 아래에 '무료 리포트 전문 보기' 버튼."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return False
    if not font_path:
        return False
    W, H = 1200, 630
    img, d = _og_base(W, H)
    F = lambda n: ImageFont.truetype(font_path, n, index=1)
    f_brand, f_meta, f_tick, f_cta = F(30), F(30), F(34), F(32)
    chart = ROOT / "static" / "charts" / f"{r['slug']}.png"
    has_chart = chart.exists()
    left_w = 640 if has_chart else W - 128
    # 오른쪽: 리포트 대표 차트의 윗부분을 카드처럼(아래는 흐리게 사라짐) — '자료로 쓴 리포트'라는 신호
    if has_chart:
        cx, cy, cw, ch = 764, 64, 372, 502
        with Image.open(chart) as im:
            im = im.convert("RGB")
            sc = cw / im.width
            im = im.resize((cw, int(im.height * sc)))
            im = im.crop((0, 0, cw, min(ch, im.height)))
        card = Image.new("RGB", (cw, ch), "#ffffff"); card.paste(im, (0, 0))
        fade = Image.new("L", (cw, ch), 255)
        fd = ImageDraw.Draw(fade)
        for yy in range(ch - 150, ch):
            fd.line([(0, yy), (cw, yy)], fill=int(255 * (ch - yy) / 150))
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=26, fill=255)
        from PIL import ImageChops
        mask = ImageChops.multiply(mask, fade)
        img.paste(card, (cx, cy), mask)
    _og_brand(img, d, f_brand, 64, 56)
    # 티커 배지 + 회사·테마
    tk = r["ticker"]; tw = d.textlength(tk, font=f_tick)
    d.rounded_rectangle([64, 124, 64 + tw + 32, 176], radius=12, fill=OG_AMBER)
    d.text((80, 128), tk, font=f_tick, fill=OG_INK)
    meta = f"{r.get('seo_name') or r['company']} · {r['theme']}"
    d.text((64 + tw + 52, 134), meta, font=f_meta, fill="#94a3b8")
    # 훅: 3줄 안에 들어가는 가장 큰 글자. 숫자·변화 단어는 강조색
    hook = r.get("share_title") or r["title"]
    hook = re.sub(r"^" + re.escape(str(r.get("seo_name") or "")) + r"\s*[,，]\s*", "", hook) if r.get("seo_name") else hook
    size, lines = 72, []
    while size >= 46:
        f_h = F(size)
        lines = _og_words(d, hook, f_h, left_w)
        if len(lines) <= 3:
            break
        size -= 4
    lines = lines[:3]
    if len(lines) == 3 and len(_og_words(d, hook, f_h, left_w)) > 3:
        lines[2][-1] = lines[2][-1] + "…"
    lh = int(size * 1.32)
    y = 214 + (3 - len(lines)) * lh // 2
    for ln in lines:
        x = 64
        for i, w in enumerate(ln):
            col = OG_AMBER if _HL.search(w) else "#f8fafc"
            d.text((x, y), w, font=f_h, fill=col)
            x += d.textlength(w + " ", font=f_h)
        y += lh
    end = _og_cta(d, f_cta, 64, 520)
    d.text((end + 24, 538), "drkimworld.com", font=f_meta, fill="#64748b")
    img.save(dest, "PNG", optimize=True)
    return True


def make_board_og(dest: Path, code: str, name: str, font_path) -> bool:
    """종토방·라운지 글을 공유할 때 쓰는 그림: '$티커 종토방' + 대화 보러 가기."""
    try:
        from PIL import ImageFont
    except Exception:
        return False
    if not font_path:
        return False
    img, d = _og_base()
    F = lambda n: ImageFont.truetype(font_path, n, index=1)
    _og_brand(img, d, F(30), 64, 56)
    title = "라운지" if code == "talk" else f"${code.upper()} 종토방"
    d.text((64, 190), title, font=F(96), fill=OG_AMBER if code != "talk" else "#f8fafc")
    sub = "종목 없이 나누는 투자 이야기" if code == "talk" else f"{name} 이야기를 나누는 개인 투자자들"
    d.text((64, 320), sub, font=F(44), fill="#e2e8f0")
    d.text((64, 384), "공시·실적으로 쓴 무료 리포트와 함께 읽는 커뮤니티", font=F(32), fill="#94a3b8")
    end = _og_cta(d, F(32), 64, 520, "대화 보러 가기 →")
    d.text((end + 24, 538), "drkimworld.com", font=F(30), fill="#64748b")
    img.save(dest, "PNG", optimize=True)
    return True


def make_default_og(dest: Path, site: dict, font_path):
    try:
        from PIL import ImageFont
    except Exception:
        return
    img, d = _og_base()
    if font_path:
        F = lambda n: ImageFont.truetype(font_path, n, index=1)
        _og_brand(img, d, F(30), 64, 56)
        d.text((64, 170), "주가가 왜 그렇게", font=F(76), fill="#f8fafc")
        d.text((64, 270), "움직였는지", font=F(76), fill=OG_AMBER)
        d.text((64, 384), site.get("tagline", ""), font=F(36), fill="#cbd5e1")
        end = _og_cta(d, F(32), 64, 520, "무료 리포트 보기 →")
        d.text((end + 24, 538), "drkimworld.com", font=F(30), fill="#64748b")
    img.save(dest, "PNG", optimize=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--out", default=str(DIST))
    a = ap.parse_args()
    try:
        build(drafts=a.drafts, strict=a.strict, out=Path(a.out))
    except BuildError as e:
        print("❌", e)
        sys.exit(1)
