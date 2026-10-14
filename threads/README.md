# Threads 예약 게시

`threads/queue/`에 글 파일(JSON)을 넣고 `main`에 올리면, GitHub Actions `Threads (예약 게시)` 워크플로가 15분마다 확인해 `publish_at`이 지난 글을 Threads에 올리고 `threads/posted/`로 옮겨 커밋한다. 이 폴더만 바뀐 커밋은 사이트를 다시 빌드·배포하지 않는다.

## 글 파일

파일 이름은 `<리포트 slug>-<번호>.json`처럼 겹치지 않게 짓는다(예: `xtia-2026-10-1.json`).

```json
{
  "text": "본문. 줄바꿈은 \n. 500자 이내.",
  "publish_at": "2026-10-14T19:30:00-04:00",
  "link_attachment": "https://drkimworld.com/r/xtia-2026-10/?utm_source=threads&utm_medium=social&utm_campaign=xtia-2026-10&utm_content=post"
}
```

- `publish_at`: ISO 8601. 시간대를 빼면 미국 동부시간(America/New_York)으로 본다. 예약 실행은 몇 분 늦을 수 있다.
- `link_attachment`(선택): 링크 미리보기 카드. 리포트 링크에는 UTM(`utm_source=threads&utm_medium=social&utm_campaign=<slug>&utm_content=post`)을 붙인다.
- 500자 제한: 이모지는 UTF-8 바이트 수(보통 4자)로 세어 보수적으로 검사한다. 넘거나 형식이 틀리면 워크플로가 실패로 표시되고 그 글은 게시하지 않는다.
- 미리 검사: `python scripts/threads_publish.py --check`

게시되면 `threads/posted/`의 파일에 `posted_at`, `threads_id`, `permalink`가 더해진다. 게시에 실패한 글은 대기열에 남고 다음 실행에서 다시 시도한다.

## 비밀값

GitHub 저장소 비밀값 `THREADS_ACCESS_TOKEN`(장기 토큰), `THREADS_USER_ID`. 값은 로그·파일 어디에도 남기지 않는다. 매주 월요일 워크플로가 토큰이 살아 있는지 확인하고, 죽었으면 실패로 표시한다(Actions 화면에서 mode=`ping`으로 손으로 확인할 수도 있다).

## 토큰 갱신 (60일마다)

Threads 장기 토큰은 60일 동안 유효하다. 발급 후 24시간이 지났고 아직 만료되지 않았다면, 같은 토큰으로 새 60일 토큰을 받을 수 있다. 만료 전에(50일 무렵 권장) 아래를 실행한다.

```sh
# 1) 새 토큰 받기 (응답의 access_token 이 새 토큰, expires_in 은 초 단위 약 60일)
curl -s "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=<지금 토큰>"

# 2) GitHub 비밀값 바꾸기 (값은 붙여넣기 프롬프트로 입력)
gh secret set THREADS_ACCESS_TOKEN -R phdkimworld/kimworld-site
```

또는 GitHub 저장소 → Settings → Secrets and variables → Actions → `THREADS_ACCESS_TOKEN` → Update. 이미 만료됐다면 갱신이 안 되므로 Meta 개발자 앱에서 단기 토큰을 다시 받아 장기 토큰으로 교환(`GET /access_token?grant_type=th_exchange_token&client_secret=...&access_token=<단기 토큰>`)한 뒤 같은 방법으로 넣는다.
