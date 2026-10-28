# 운영 통계 열람 지침 — 다른 Claude 세션·에이전트용

drkimworld.com의 방문·유입·광고·참여 통계를 다른 세션이 직접 꺼내 보는 방법이다. 이 문서만 읽으면 된다.
(작성 2026-10-26. 블로거 게시는 `docs/blogger-guide.md`, 운영 기록·애드핏 실적은 `docs/ops-log.md`)

---

## 0. 통계가 어디에 있나 (먼저 고른다)

| 통계 | 원본 | 세션이 직접 볼 수 있나 | 방법 |
| --- | --- | --- | --- |
| **사이트 자체 통계**(방문·세션·유입·리포트별 체류·스크롤·이벤트·광고 노출·투표·커뮤니티) | Cloudflare Worker + D1 (`/v1/admin/analytics`) | **예** | 1장: `Analytics report` 워크플로 → 주석 |
| 쿠팡 파트너스 검색어 성과(노출·클릭·주문·수수료) | Worker + 쿠팡 API | 예 | 4장: `Ad report` 워크플로 → 주석 |
| 쿠팡 일별 클릭·구매·수익(쿠팡 집계, 배너 포함) | 쿠팡 API 보고서 | 예 | `data/coupang_daily.csv`(매일 `Coupang stats` 워크플로가 갱신), 운영 통계 '쿠팡 파트너스 실적' |
| 카카오 애드핏 수익 | 애드핏 대시보드(API 없음). 운영자 휴대폰이 카톡 알림을 `/v1/ingest/adfit`로 자동 전달 → D1 | **예(기록본)** | 운영자가 매일 붙여 주는 데일리 리포트 → `data/adfit_daily.csv`(`scripts/adfit_add.py`로 넣음). 운영 통계 화면 '애드핏 실적'에도 보인다. 해석은 `docs/ops-log.md` |
| 구글 서치 콘솔(검색 노출·색인) | 운영자 구글 계정 | 아니오 | 운영자에게 화면 캡처 부탁(5장 링크) |
| GA4 | 운영자 구글 계정 | 아니오 | 사이트 자체 통계로 대신한다 |
| 과거 해석·결정 | `docs/ops-log.md` | 예 | 저장소에서 읽기 |

**세션의 제약** (모두 확인된 사실)
- 셸은 drkimworld.com·api.drkimworld.com에 못 닿는다. 관리 토큰(`KIMWORLD_ADMIN_TOKEN`)도 GitHub 비밀값에만 있고 세션은 읽을 수 없다
- 그래서 **GitHub Actions 워크플로가 대신 받아 와서 주석(annotation)으로 내보내고, 세션은 주석을 읽는다**
- 워크플로 로그 내려받기는 프록시가 막는다(Forbidden). 주석만 읽힌다
- `gh`는 REST만 된다(`gh api ...`). `gh run`·`gh workflow` 편의 명령은 쓰지 않는다
- 사람이 보는 통계 화면은 https://drkimworld.com/admin/ (운영자 계정 로그인 필요). 세션은 열 수 없다

---

## 1. 사이트 자체 통계 받기 (가장 많이 쓴다)

### 1-1. 준비
저장소가 세션에 없으면 `mcp__claude-code-remote__add_repo`로 `phdkimworld/kimworld-site`(access `push` — 워크플로 실행에 필요)를 붙이고 복제한다.

### 1-2. 실행 → 기다림 → 주석 받기 (복사해서 그대로)
```bash
REPO=phdkimworld/kimworld-site
# days: 7(기본)·30·90 중 하나. 워커가 그 밖의 값은 30으로 바꾸므로 워크플로가 7·30·90만 넘긴다
gh api -X POST repos/$REPO/actions/workflows/analytics-report.yml/dispatches -f ref=main -f 'inputs[days]=7'
sleep 15
R=$(gh api "repos/$REPO/actions/workflows/analytics-report.yml/runs?per_page=1" --jq '.workflow_runs[0].id')
until [ "$(gh api repos/$REPO/actions/runs/$R --jq .status)" = completed ]; do sleep 10; done   # 보통 30초~1분
gh api repos/$REPO/actions/runs/$R --jq .conclusion
J=$(gh api repos/$REPO/actions/runs/$R/jobs --jq '.jobs[0].id')
gh api repos/$REPO/check-runs/$J/annotations --jq '.[]|select(.title|startswith("AN"))|.message' > /tmp/an_parts.txt
wc -l /tmp/an_parts.txt
```
- 주석 제목 `AN HTTP`: 워커 응답 코드와 크기(`200 51540 bytes` 정상). 200이 아니면 `AN BODY`에 응답 앞부분
- 주석 제목 `AN 1/n` … `AN n/n`: 통계 JSON을 섹션별로 나눈 조각. 순서는 보장되지 않는다
- 줄마다 JSON 한 덩어리다. 하나로 합치기:
```bash
python3 - <<'E'
import json
d = {}
for line in open('/tmp/an_parts.txt', encoding='utf-8'):
    line = line.strip()
    if line.startswith('{'):
        d.update(json.loads(line))
json.dump(d, open('/tmp/an.json', 'w'), ensure_ascii=False, indent=1)
print(sorted(d))
E
```
- 바로 직전 실행 결과를 다시 보고 싶으면 실행 없이 2번째 줄부터(`R=`) 하면 된다(매일 점검 작업이 이미 돌렸을 수 있다)

### 1-3. 필드 뜻 (`/tmp/an.json`)
날짜는 **한국 날짜(KST)** 기준이다. 걸러 낸 봇은 빠져 있다(`bots`에 개수만).

**전체**
- `days`, `since`: 기간과 시작일
- `totals.{pv,uv,sess,multi,newv,signups,secs}`: 각각 `now`(이번 기간)·`prev`(직전 같은 길이)·`chg_pct`
  - pv 페이지뷰, uv 순방문자, sess 세션, multi 2쪽 이상 본 세션, newv 신규 방문자, signups 가입, secs 총 체류 초
- `totals.mobile_pct`, `pages_per_sess`, `multi_page_pct`
- `active`: `dau`·`wau`·`mau`
- `series[]`: 날짜별 `pv·uv·sess·secs·signups`

**유입**
- `channels[]`: 채널별(youtube·social·direct·messenger·search·referral·internal·app). 필드: `sess`, `pv`, `prevSess`, `pages/sess`, `secs/sess`, `engaged_pct`(참여 세션 비율), `deep_pct`(깊이 본 비율), `new_pct`, `app_pct`, `ev`(그 채널 방문자의 이벤트 수)
- `sources[]`: 세부 출처(예: `youtube`, `threads`, `share-kakaotalk`, `daum-search`, `ig`, `app-home`. utm_source가 붙은 방문은 그 값으로 잡힌다(블로거 글은 `blogger`)). 필드는 channels와 같다
- `landings[]`: 첫 페이지 × 출처별 세션·체류
- `campaigns[]`: utm 묶음. `src/med/cont` 예: `youtube/video/pinned`(고정댓글), `youtube/video/description`, `youtube/comment/reply`, `threads/social/reply`, `share/link`, `blogger/post`
- `dow[]`: 요일(0=일)×채널 세션

**페이지·읽기**
- `reports[]`, `pages[]`: 경로별 `pv`, `entries`(첫 페이지로 들어온 수), `likes`, `comments`, `reposts`, `app`, `secs/pv`, `scroll_pct`(평균 최대 스크롤)
- `types[]`: 페이지 유형별(r 리포트, h 홈, t 종목, s 검색, u 프로필, o 기타) pv와 `secs/pv`
- `sections`: 리포트 구간 도달 곡선. 키 `top·ans·can·news·term·p1~p6·src·more·comm`(리포트 위→아래 순서), 값 `[도달률%, 평균 체류초]`. `all`은 전체, `reports`는 리포트별
- `hours[]`: **한국 시각** 시간대별 pv(관리 화면에는 동부 시각 차트도 있다)

**행동·광고**
- `events`: 이벤트별 `now`/`prev`. 자주 보는 것:
  - `adv_adfit`·`adv_coupang`: 광고가 실제로 화면에 보인 횟수(뷰어빌리티 측정용)
  - `sent_vote`(투자 심리 투표), `poll_share`, `share`, `share_kakao`(카톡으로 보내기), `update_request`(리포트 업데이트 요청)
  - `yt_jump_shown/click`, `yt_play`(리포트 안 영상), `install_*`(앱 설치 유도), `signup`, `login_start`, `next_bar`, `mid_next_click`, `home_report`
- `ads[]`: 슬롯별 `imps`·`clicks`·`ctr_pct`(사이트가 센 값. 애드핏 대시보드 숫자와 다르다 — 애드핏은 요청·렌더·보인 노출을 따로 센다)
- `bots`: 거른 봇(`dc` 데이터센터, `quick` 3초 안 이탈, `quick_land`)

**커뮤니티·기타**
- `community`: 사용자·글·답글·신고·팔로우 수
- `actions`: 리포스트·인용
- `app`: 앱(PWA) 사용자·pv
- `sentiment`: 투표 수·투표자·종목 수·상위 종목(bull/bear)
- `updReq`: 리포트 업데이트 요청 많은 종목(최근 30일)
- `cohorts[]`: 날짜별 신규 `n`, 다음날 재방문 `d1`, 7일 안 재방문 `d7`
- `os`: 운영체제별 pv
- `topics`, `topicNew`: 커뮤니티 주제
- `searches_total`, `search_miss`(못 찾은 검색 수), `search_miss_top`(티커·회사명처럼 생긴 것만)

### 1-4. 자주 묻는 질문을 바로 뽑는 예
```bash
# 채널별 세션(직전 기간 자료가 없으면 "없음")
jq -r '.channels[]|"\(.ch)\t\(.sess)\t(직전 기간 \(.prevSess // "없음"))"' /tmp/an.json
# 구글·네이버·다음 검색 유입
jq -r '.sources[]|select(.ch=="search")|"\(.src)\t\(.sess)"' /tmp/an.json
# 리포트별 체류·스크롤 상위
jq -r '.reports[]|"\(.path)\tpv \(.pv)\t\(."secs/pv")초\t스크롤 \(.scroll_pct)%"' /tmp/an.json | head -20
# 일별 추이
jq -r '.series[]|"\(.day)\tpv \(.pv)\tuv \(.uv)\t세션 \(.sess)"' /tmp/an.json
# 광고가 실제로 보인 횟수(이번 vs 전 기간)
jq '.events|{adv_adfit,adv_coupang}' /tmp/an.json
```

---

## 2. 해석할 때 주의

- **애드핏 수익은 사이트 통계에 없다.** 애드핏은 API가 없고, 운영자가 데일리 리포트(요청·노출·렌더드·클릭·eCPM·적립금)를 채팅에 붙여 주면 `printf '%s' "<붙여 준 글>" | python3 scripts/adfit_add.py`로 `data/adfit_daily.csv`에 넣고 커밋한다(`--show`로 최근 10일과 7일 요약). 해석 한 줄은 `docs/ops-log.md` '애드핏 실적'에. eCPM = 적립금 ÷ *보인* 노출 × 1000. "보이는 비율" = 노출 ÷ 렌더드 노출
- 애드핏 요청 수가 사이트 pv보다 훨씬 많은 것은 정상이다(한 페이지에 광고 여러 개, 빠른 이탈·봇도 요청은 센다)
- 사이트 통계의 날짜는 KST, 애드핏 리포트 날짜도 한국 날짜, 운영자 대화는 미국 동부 시각이다
- 숫자가 작다(하루 세션 20~60). 하루 변동으로 결론 내지 말고 7일 합계·전주 대비로 본다
- 유튜브가 유입의 대부분이다. 영상 업로드 날 급증하고 주말에 준다
- `direct` 안에는 앱 실행·북마크·주소 입력이 섞인다. 앱 실행은 `app` 채널로 따로 잡도록 고쳐 두었다(2026-10-19)
- 검색 유입: 2026-10-26 기준 구글 0, 네이버 0, 다음 몇 건. 서치 콘솔 색인 34개(10-15 기준)

---

## 3. 공개 저장소 주의 (개인정보)

저장소가 공개라 **Actions 주석도 누구나 볼 수 있다.** 그래서 `scripts/analytics_report.py`는 집계 숫자만 내보낸다(닉네임·사용자 목록·검색어 원문·IP 없음. 검색 실패어는 티커·회사명처럼 생긴 것만).
- 이 스크립트에 사용자 단위 정보·검색어 원문을 내보내는 코드를 넣지 않는다
- 통계를 저장소 파일로 커밋할 때도 집계 숫자만(예: `docs/ops-log.md`에 요약)
- 세션 안 `/tmp/an.json`은 세션이 끝나면 사라진다. 그대로 커밋하지 않는다

---

## 4. 쿠팡 파트너스 검색어 성과

```bash
REPO=phdkimworld/kimworld-site
gh api -X POST repos/$REPO/actions/workflows/ad-report.yml/dispatches -f ref=main
sleep 15
R=$(gh api "repos/$REPO/actions/workflows/ad-report.yml/runs?per_page=1" --jq '.workflow_runs[0].id')
until [ "$(gh api repos/$REPO/actions/runs/$R --jq .status)" = completed ]; do sleep 10; done
J=$(gh api repos/$REPO/actions/runs/$R/jobs --jq '.jobs[0].id')
gh api repos/$REPO/check-runs/$J/annotations --jq '.[]|"\(.title): \(.message)"' | grep -v -i "node\|ubuntu"
```
검색어별 노출·클릭·주문·수수료가 주석으로 나온다(2주마다 정기 점검이 돌린다). 결과 해석과 검색어 교체 규칙은 `AGENTS.md`의 쿠팡 항목을 따른다.

---

## 5. 운영자에게 부탁해야 하는 통계 (휴대폰용 링크)

- 서치 콘솔 실적(노출·클릭·검색어): https://search.google.com/search-console/performance/search-analytics — 기간 '지난 28일'로 캡처
- 서치 콘솔 색인: https://search.google.com/search-console/index — 색인됨/안 됨 개수와 이유 목록 캡처
- 애드핏: 운영자가 매일 받는 '카카오애드핏 데일리 리포트' 텍스트를 붙여 달라고 하면 된다
- 사이트 관리 화면(사람용 차트): https://drkimworld.com/admin/ — 운영자 계정 로그인

---

## 6. 문제가 생기면

| 증상 | 원인 | 할 일 |
| --- | --- | --- |
| `AN HTTP` 가 `403` + `Just a moment` | Cloudflare 봇 검사가 러너를 막음 | 워크플로는 workers.dev 주소를 먼저 쓴다. `CLOUDFLARE_API_TOKEN`·`CLOUDFLARE_ACCOUNT_ID` 비밀값이 살아 있는지(주석 `AN HTTP` 주소) 확인 |
| `AN HTTP` 가 `403` + `owner` | 관리 토큰 불일치 | 워커의 `ADMIN_TOKEN`은 `API (views, comments)` 워크플로가 GitHub `KIMWORLD_ADMIN_TOKEN`(없으면 Cloudflare 토큰에서 만든 값)으로 넣는다. 비밀값이 바뀌었으면 `api.yml`을 수동 실행해 다시 맞춘 뒤 재시도 |
| `AN` 주석이 없음 | 실행 실패 | `.conclusion`과 `AN` 오류 주석(`analytics 응답을 읽지 못함`) 확인 |
| 주석 조각 수가 9를 넘음 | 한 단계에 주석 10개 제한 | 스크립트가 9조각까지만 내보낸다. 긴 목록은 자동으로 줄인다 |
| 숫자가 0 | 워커 D1 문제·배포 직후 | `API (views, comments)` 워크플로 최근 실행 성공 여부 확인 |

---

## 7. 이 통계로 하는 정기 작업 (참고)

- 매일 점검(예약 작업): 이 워크플로로 7일 통계를 받아 수익성·개선점을 보고, 입력·비용 없이 고칠 수 있는 것을 바로 반영하고 `docs/ops-log.md`에 남긴다
- 매주 월요일: 애드센스 재신청 준비 점검(하루 세션 100·검색 유입 주 20 등 기준)
- 2주마다: 쿠팡 검색어 성과
같은 일을 중복으로 하지 않도록, 시작 전에 `docs/ops-log.md`의 날짜별 기록(최신이 위, '개선 후보' 아래)을 먼저 읽는다.
