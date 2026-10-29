# SNS 예약 게시 (Threads · Instagram · Facebook 페이지)

`social/queue/`에 게시물 파일(JSON)을 넣고 `main`에 올리면, GitHub Actions `Social` 워크플로가 15분마다 확인해 `publish_at`이 지난 글을 채널별로 게시하고 `social/posted/`로 옮겨 커밋한다. 대기열·기록만 바뀐 커밋은 사이트를 다시 배포하지 않는다.

## 게시물 파일

파일 이름은 겹치지 않게 `<slug>-<번호>.json` (예: `lhx-2026-10-reels.json`).

```json
{
  "text": "공통 본문",
  "publish_at": "2026-10-14T19:30:00-04:00",
  "channels": ["threads", "instagram", "facebook"],
  "media": {"type": "reels", "path": "static/social/lhx-2026-10/LHX_shorts.mp4", "cover": "static/social/lhx-2026-10/cover.jpg"},
  "channel_text": {"instagram": "인스타 캡션(링크가 눌리지 않으므로 'drkimworld.com 에서 검색' 안내)"},
  "poll": ["11월 3일 해제 뒤 오른다", "내린다", "보합"],
  "replies": [{"text": "Threads 이어지는 댓글(리포트 링크)", "link_attachment": "https://drkimworld.com/r/..."}]
}
```

- `publish_at`: 시간대를 빼면 미국 동부시간. 예약 실행은 몇 분 늦을 수 있다.
- `channels`: `threads`, `instagram`, `facebook` 가운데 하나 이상.
- **Facebook 페이지**(김박사 월드, Graph API v26.0, 운영자 지시 2026-10-15): Threads와 같은 요령으로 쓴다.
  - 미디어 없는 글은 `/{page}/feed`에 본문을 올리고, `replies[0]`을 첫 댓글로 단다(링크의 `utm_source=threads`는 `facebook`으로 바뀐다). 투표(`poll`)는 페이스북에는 붙이지 않는다(참여 유도 글 노출 감소 위험, 운영자 지시 2026-10-16). 인스타 캡션에만 끝에 '여러분의 생각은? 댓글에 번호로 남겨 주세요. ① …'를 글로 붙인다(릴스 파일에 `poll`을 넣으면 적용).
  - `reels`는 `/{page}/video_reels` 3단계(start → `rupload.facebook.com`에 저장소의 영상 파일을 직접 업로드 → finish)로 올리고, 캡션은 `channel_text.facebook`이 없으면 인스타 캡션을 쓴다. `image`는 `/photos`(사진도 파일을 직접 올림), `carousel`은 사진을 `published=false`로 올린 뒤 `feed`의 `attached_media`로 묶는다. 페이스북은 사이트 주소에서 미디어를 가져가다 403으로 막힌 적이 있어(2026-10-15) 주소 대신 파일을 보낸다.
  - 오류 190(토큰)·200(권한)은 재시도하지 않고 실패로 표시한다. 일시 오류(5xx·속도 제한)는 20·60·120초 간격으로 최대 3회 다시 시도한다.
  - 앱이 개발 모드라 공개 노출을 확인해야 한다. `social/FACEBOOK_LIVE` 파일이 없으면 페이스북 글은 한 건만 올리고 나머지는 '공개 확인 대기'로 둔다. 로그아웃 상태에서 첫 글이 보이면 이 파일을 커밋한다. 안 보이면 앱을 라이브로 바꿔야 한다.
  - 비밀값 `FB_PAGE_ID`, `FB_PAGE_TOKEN`. 페이지 토큰은 비즈니스 포트폴리오 '김박사 월드'의 시스템 사용자 `kimworld-bot`에서 받은 것으로, 토큰 만료·데이터 접근 만료가 모두 없다(재발급: Business Suite → 설정 → 시스템 사용자 → 토큰 생성 → `/{page-id}?fields=access_token`).
- **Threads**: TEXT 게시(본문·댓글 각 500자, 이모지는 4자로 셈). `replies`로 이어지는 댓글, `link_attachment`로 링크 카드. `poll`(보기 2~4개, 각 25바이트 이하 = 한글 약 8자)은 본문에 투표로 붙고(24시간), 본문의 `link_attachment`와 함께 쓸 수 없다.
- **Instagram**: 미디어가 있어야 게시한다(없으면 건너뜀). `media.type`
  - `image`: `path` 1장(JPEG 권장)
  - `carousel`: `paths` 2~10장
  - `reels`: `path` MP4(세로 9:16, 3~90초 권장), 선택 `cover`
  - 캡션 2,200자 이내. 캡션의 링크는 눌리지 않는다.
- `channel_text`: 채널마다 본문을 따로 쓸 때.
- 미리 검사: `python scripts/social_publish.py --check`
- 글 쓰는 기준: 미디어 저장소 `skill/SKILL.md` K8.0·K8.1 '스레드 작성 표준'(운영자 지침 2026-10-29) — 모순으로 시작, 숫자와 비교 기준, 사실·가설·예측 구분(같은 날 두 일을 인과로 단정하지 않음), 복수 해석과 반대 증거, 마지막 질문과 `poll` 보기는 같은 전망 질문, 리포트 연결은 'N부 <표 이름>', 사후 검증. 올리기 전 미디어 저장소 `tools/queue_check.py`.

## 노출을 늘리는 기본값 (운영자 지시 2026-10-20)

- `publish_at`은 영상 공개 직후 현재 시각(운영자 지시 2026-10-20 "시간 바꾸는건 안돼. 발행은 반드시 즉시"). `--next-slot`은 쓰지 않는다.
- Threads 첫 글에 `topic_tag`(기본 `미국주식`, 글마다 `"topic_tag"`로 바꿈). 태그를 받지 않으면 태그 없이 다시 올린다.
- 인스타 릴스는 체험 릴스(`trial_params` SS_PERFORMANCE)로 올린다. 끄려면 `media.trial: false`. 받지 않으면 일반 릴스로 다시 올리고 `results.instagram.trial = "unsupported"`.
- 페이스북은 릴스 파일에서만 올린다(텍스트+링크 댓글 글은 7일 11세션·평균 4초).
- 리포트 페이지는 SNS에서 온 독자에게 '글이 물은 몇 번?의 답' 바로가기(`data-sns-jump`)를 보인다. 이벤트 `sns_jump_shown`·`sns_jump_click`.

## 인스타 미디어를 drkimworld.com 에서 공개하는 방법

인스타 API는 파일을 직접 받지 않고 **공개 주소에서 가져간다**. 그래서 미디어를 저장소의 `static/social/<slug>/`에 넣는다.

1. 미디어(`static/social/...`)와 게시물(`social/queue/...`)을 같은 커밋으로 `main`에 올린다.
2. 사이트 배포(`deploy.yml`)가 돌아 `https://drkimworld.com/static/social/...`가 열린다(2~5분).
3. Social 워크플로는 주소가 200을 돌려줄 때까지 인스타 게시를 다음 실행으로 미룬다. 6시간이 지나도 열리지 않으면 실패로 표시한다.

GitHub Pages는 파일 하나 100MB, 사이트 전체 1GB까지라 쇼츠(보통 10~30MB)는 충분하다. 인스타에 게시된 뒤에는 인스타 서버에 사본이 남으므로, 오래된 `static/social/` 파일은 몇 주 뒤 지워도 된다.

## 결과와 실패

게시하면 파일에 `results.<채널>`(글 ID, 주소)과 `posted_at`이 남는다. 한 채널이 실패하면 그 글은 대기열에 남고, 이미 게시한 채널·댓글은 다음 실행에서 건너뛴다(중복 게시 방지). 실패가 있으면 워크플로가 실패로 표시된다.

## 비밀값

`THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `IG_ACCESS_TOKEN`, `IG_USER_ID`. 게시는 토큰 주인 계정으로 하며, `*_USER_ID`가 다르면 경고만 남긴다. 매주 월요일 두 토큰이 살아 있는지 확인한다(Actions에서 mode=`ping`으로 손으로 확인 가능).

## 토큰 갱신 (둘 다 60일, 발급 24시간 뒤부터 만료 전까지 갱신 가능)

50일 무렵 아래를 실행해 새 토큰을 받고(응답의 `access_token`), GitHub 비밀값을 바꾼다.

```sh
# Threads
curl -s "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=<지금 토큰>"
gh secret set THREADS_ACCESS_TOKEN -R phdkimworld/kimworld-site

# Instagram (Instagram Login 방식)
curl -s "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<지금 토큰>"
gh secret set IG_ACCESS_TOKEN -R phdkimworld/kimworld-site
```

## 토큰 자동 갱신

`.github/workflows/token-refresh.yml`이 매달 1일·15일에 위 두 갱신을 자동으로 하고 비밀값을 바꾼다(`scripts/token_refresh.py`). 손으로 하려면 Actions에서 'Token refresh'를 실행한다.

- 필요한 비밀값 `GH_SECRETS_PAT`: GitHub → Settings → Developer settings → Fine-grained tokens → 저장소 `phdkimworld/kimworld-site`만 선택, 권한 **Secrets: Read and write** 하나만. 만료는 최대(또는 없음)로 두고, 이 토큰이 만료되면 새로 만들어 넣는다.
- 실패하면 워크플로가 실패로 표시된다. 60일 넘게 실패가 이어지면 토큰이 만료되어 새로 발급해야 한다.
- 페이스북 페이지 토큰은 시스템 사용자 토큰이라 만료가 없어 자동 갱신 대상이 아니다.

이미 만료됐다면 갱신이 안 되므로 Meta 개발자 앱에서 단기 토큰을 다시 받아 장기 토큰으로 교환한 뒤 같은 방법으로 넣는다.

## 댓글 모니터링 (Threads · Instagram · Facebook, 운영자 지시 2026-10-15)

유튜브 댓글 자동 답글과 같은 요령으로, 우리 게시물에 달린 시청자 댓글과 우리 답글 뒤의 대댓글에 답한다. 매시간 도는 세션 예약 작업 '댓글 자동 답글'이 함께 처리한다.

**답글 링크 위치별 유입(UTM, 운영자 지시 2026-10-16)**: 답글 파일 항목에 `"kind": "top|followup|request"`를 넣으면 `--post`가 본문의 리포트 링크에 `utm_source=<채널>&utm_medium=comment&utm_campaign=<slug>&utm_content=reply|followup|request`를 붙인다(댓글 답글·대댓글 답글·종목 요청 답글을 따로 센다, 원고에는 맨 주소만). 유튜브는 `tools/yt_reply.py --reply … --kind followup`으로 같은 값을 붙인다(utm_source=youtube). 사이트 관리자 '유입 분석 → 캠페인(UTM)'에서 위치별로 본다.

1. 세션이 `.github/workflows/social-comments.yml`을 `mode=list`로 수동 실행한다. 작업 로그의 `OPEN_JSON:` 한 줄에 채널별 '답할 차례' 목록이 나온다(`kind` top/followup, `replyTo`, `context`, `slug`).
2. 세션이 리포트 숫자로 답글을 써서 `social/replies/<날짜-시각>.json`(`{"replies":[{"platform","to","text"}]}`)으로 main에 푸시한다.
3. 같은 워크플로가 푸시를 받아 답글을 달고, 결과를 파일의 `results`에 적어 `social/replies/done/`으로 옮겨 커밋한다. 결과가 있는 항목은 다시 달지 않는다.

- Threads는 답글이 나무 구조라, 우리 글(본문·우리 답글)에 직접 단 시청자 댓글만 고르고 시청자끼리 대화는 뺀다. 인스타·페이스북은 '댓글 + 한 단계 답글'이라 유튜브와 같이 판정한다.
- 필요한 권한: Threads `threads_read_replies`·`threads_manage_replies`, Instagram `instagram_business_manage_comments`, Facebook `pages_read_engagement`·`pages_read_user_content`·`pages_manage_engagement`. `mode=probe`로 읽기 권한을 확인한다. 없는 채널은 목록에 `ok:false`와 오류가 나오고 그 채널만 건너뛴다.
- 검사: `python3 tests/test_comments.py`.
