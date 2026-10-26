# 블로거(김박사 월드 노트) 게시 — 다른 Claude 세션용 지침

2026-10-25 연결 확인(첫 글: https://phdkimworld.blogspot.com/2026/10/8.html). 이 문서만 읽으면 어느 세션이든 블로거에 글을 올릴 수 있다.

## 한 줄 요약
블로거 글은 **GitHub Actions 워크플로 `Blogger (새 리포트 소개 글)`** 로만 올린다. 세션 안에서 구글 API를 직접 부르지 않는다(비밀값은 GitHub 비밀값에만 있고, 세션은 그 값을 볼 수 없다).

## 무엇이 어디에 있나
- 블로그: 김박사 월드 노트, `phdkimworld.blogspot.com`, 블로그 ID `7073807355015585186`(공개값, 워크플로에 박혀 있음)
- 코드: `scripts/blogger_post.py`, 워크플로 `.github/workflows/blogger.yml`
- 게시 기록: `social/blogger/posted.json` (`{slug: {url, at}}`, 워크플로가 커밋. 배포 제외 경로)
- 자동 실행: 하루 두 번(UTC 01:20, 13:20). 공개 7일 이내 리포트 중 아직 안 올린 것, 최신 순으로 **하루 최대 2건**
- 인증: OAuth 클라이언트 `drkimworld web`(사이트 구글 로그인과 같은 것, ID `385980026755-sdef5j26m2kk509tuiec56s3099jc8av.apps.googleusercontent.com`) + 비밀값 `GOOGLE_CLIENT_SECRET` + `BLOGGER_REFRESH_TOKEN`(scope `https://www.googleapis.com/auth/blogger`, 블로그 주인 계정으로 발급). 스크립트는 `BLOGGER_CLIENT_SECRET` → `GOOGLE_CLIENT_SECRET` 순서로 시도한다(2026-10-25 기준 `BLOGGER_CLIENT_SECRET`은 invalid, `GOOGLE_CLIENT_SECRET`으로 성공)

## 특정 리포트를 지금 올리기
```bash
gh api -X POST repos/phdkimworld/kimworld-site/actions/workflows/blogger.yml/dispatches \
  -f ref=main -f 'inputs[slug]=<리포트 slug>'
```
- slug를 주면 공개 7일 제한·하루 2건 제한 없이 그 리포트 하나만 올린다. 이미 `posted.json`에 있으면 건너뛴다(다시 올리려면 기록에서 지우는 커밋 먼저 — 같은 글이 두 번 생기므로 보통 하지 않는다)
- 리포트가 사이트에서 아직 안 열리면(배포 전) 건너뛴다. 새 리포트는 배포(Build and deploy) 성공 뒤에 실행한다
- 입력 없이 실행하면 자동 규칙대로 돈다

## 결과 확인 (로그는 프록시가 막으므로 주석으로 본다)
```bash
R=$(gh api "repos/phdkimworld/kimworld-site/actions/workflows/blogger.yml/runs?per_page=1" --jq '.workflow_runs[0].id')
gh api repos/phdkimworld/kimworld-site/actions/runs/$R --jq '.status+" "+(.conclusion//"")'
J=$(gh api repos/phdkimworld/kimworld-site/actions/runs/$R/jobs --jq '.jobs[0].id')
gh api repos/phdkimworld/kimworld-site/check-runs/$J/annotations --jq '.[]|.message'
```
- 성공: `블로거 게시` 주석에 `slug → 글 주소`, `블로거 인증` 주석에 어떤 비밀번호로 통했는지
- 실패: `블로거 인증 실패` / `블로거 HTTP nnn` 주석에 구글 응답 본문(비밀값은 들어 있지 않다)
- 셸은 blogspot.com에 못 닿고, WebFetch는 사용자가 준 주소만 연다. 글 화면 확인은 운영자에게 주소를 주고 부탁한다

## 오류별 대처
- `invalid_client`(보안 비밀번호가 틀림): 운영자에게 Google Cloud → Google Auth Platform → Clients → drkimworld web 의 `GOCSPX-`로 시작하는 비밀번호를 GitHub 비밀값으로 다시 넣어 달라고 한다. 기존 비밀번호는 사이트 구글 로그인에 쓰이므로 삭제·사용 중지하지 말라고 함께 말한다
- `invalid_grant`(갱신 토큰 만료·철회): 운영자가 https://developers.google.com/oauthplayground 에서 톱니바퀴 → Use your own OAuth credentials(위 클라이언트 ID·비밀번호) → scope `https://www.googleapis.com/auth/blogger` → Authorize(블로그 주인 계정) → Exchange → Refresh token을 `BLOGGER_REFRESH_TOKEN`으로 다시 저장. 클라이언트의 승인된 리디렉션 URI에 `https://developers.google.com/oauthplayground`가 있어야 한다(2026-10-25 추가됨)
- `403`(권한 없음): 토큰을 블로그 주인이 아닌 계정으로 받은 경우. 운영자 휴대폰 크롬에는 구글 계정이 여러 개라(블로그는 `/u/2/` 계정) 계정 선택을 확인시킨다
- `429`/쿼터: 하루를 기다린다. 한 번에 여러 건 몰아서 올리지 않는다

## 글 내용 규칙 (바꾸려면 `body()`만 고친다)
- 대표 이미지(`/og/<slug>.png`) → `summary` → 핵심 3줄(`key_points`) → 전체 리포트 버튼(`utm_source=blogger&utm_medium=post&utm_campaign=<slug>`) → 유튜브 영상(있으면) → 숫자 기준일·교육용 고지
- 리포트 본문을 옮기지 않는다(중복 콘텐츠로 사이트 리포트가 밀릴 수 있다). 스팸처럼 보이지 않도록 하루 2건을 넘기지 않는다
- 사이트 규칙과 같다: 매수·매도 지시, 수익 암시, 보유 여부, AI 사용 언급 금지
- 라벨: 티커, 테마, `미국주식`

## 하지 말 것
- 비밀값을 출력·커밋·채팅에 붙여 넣기(형식 진단이 필요하면 길이·접두어만)
- 세션에서 OAuth 토큰을 직접 발급받으려 하기(운영자 계정 동의가 필요하다)
- 리포트가 아닌 홍보글을 대량으로 올리기
