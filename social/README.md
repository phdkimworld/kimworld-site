# SNS 예약 게시 (Threads · Instagram)

`social/queue/`에 게시물 파일(JSON)을 넣고 `main`에 올리면, GitHub Actions `Social` 워크플로가 15분마다 확인해 `publish_at`이 지난 글을 채널별로 게시하고 `social/posted/`로 옮겨 커밋한다. 대기열·기록만 바뀐 커밋은 사이트를 다시 배포하지 않는다.

## 게시물 파일

파일 이름은 겹치지 않게 `<slug>-<번호>.json` (예: `lhx-2026-10-reels.json`).

```json
{
  "text": "공통 본문",
  "publish_at": "2026-10-14T19:30:00-04:00",
  "channels": ["threads", "instagram"],
  "media": {"type": "reels", "path": "static/social/lhx-2026-10/LHX_shorts.mp4", "cover": "static/social/lhx-2026-10/cover.jpg"},
  "channel_text": {"instagram": "인스타 캡션(링크가 눌리지 않으므로 'drkimworld.com 에서 검색' 안내)"},
  "poll": ["11월 3일 해제 뒤 오른다", "내린다", "보합"],
  "replies": [{"text": "Threads 이어지는 댓글(리포트 링크)", "link_attachment": "https://drkimworld.com/r/..."}]
}
```

- `publish_at`: 시간대를 빼면 미국 동부시간. 예약 실행은 몇 분 늦을 수 있다.
- `channels`: `threads`, `instagram` 가운데 하나 이상.
- **Threads**: TEXT 게시(본문·댓글 각 500자, 이모지는 4자로 셈). `replies`로 이어지는 댓글, `link_attachment`로 링크 카드. `poll`(보기 2~4개, 각 25바이트 이하 = 한글 약 8자)은 본문에 투표로 붙고(24시간), 본문의 `link_attachment`와 함께 쓸 수 없다.
- **Instagram**: 미디어가 있어야 게시한다(없으면 건너뜀). `media.type`
  - `image`: `path` 1장(JPEG 권장)
  - `carousel`: `paths` 2~10장
  - `reels`: `path` MP4(세로 9:16, 3~90초 권장), 선택 `cover`
  - 캡션 2,200자 이내. 캡션의 링크는 눌리지 않는다.
- `channel_text`: 채널마다 본문을 따로 쓸 때.
- 미리 검사: `python scripts/social_publish.py --check`

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

이미 만료됐다면 갱신이 안 되므로 Meta 개발자 앱에서 단기 토큰을 다시 받아 장기 토큰으로 교환한 뒤 같은 방법으로 넣는다.
