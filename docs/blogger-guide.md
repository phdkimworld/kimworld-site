# 블로거(김박사 월드 노트) 게시 지침 — 다른 Claude 세션·에이전트용

이 문서 하나만 읽고도 어느 세션이든 블로거에 글을 올리고, 결과를 확인하고, 고장을 고칠 수 있게 쓴 것이다.
처음 연결 확인: 2026-10-25 21:02 ET, 첫 글 https://phdkimworld.blogspot.com/2026/10/8.html (아이렌 iren-2026-10-3)

---

## 0. 먼저 알아 둘 것 (요약)

| 항목 | 값 |
| --- | --- |
| 블로그 이름 / 주소 | 김박사 월드 노트 / https://phdkimworld.blogspot.com |
| 블로그 ID (공개값) | `7073807355015585186` |
| 블로그 주인 계정 | 운영자 구글 계정 중 하나(운영자 휴대폰 크롬에서 `/u/2/`로 열리는 계정). 이메일은 문서에 적지 않는다 |
| 게시 방법 | GitHub Actions 워크플로 `Blogger (새 리포트 소개 글)` (`.github/workflows/blogger.yml`) **만** 쓴다 |
| 게시 코드 | `scripts/blogger_post.py` |
| 게시 기록 | `social/blogger/posted.json` — `{slug: {"url": 글 주소, "at": ET 시각}}`, 워크플로가 커밋 |
| 자동 실행 | 매일 UTC 01:20·13:20 (동부 밤 9:20·아침 9:20, 서머타임 해제 뒤엔 한 시간 앞당겨짐) |
| 자동 규칙 | 공개 7일 이내 + 아직 안 올린 리포트, 최신 순, **하루 최대 2건**(동부 날짜 기준) |
| 인증 | OAuth 클라이언트 `drkimworld web`(사이트 구글 로그인과 같은 것) + 갱신 토큰 |

세션(이 컨테이너)은 구글 API를 직접 부르지 않는다. 비밀값은 GitHub 비밀값에만 있고 세션은 그 값을 읽을 수 없다(비밀값 API도 프록시가 막는다). 세션이 할 수 있는 일은 **워크플로를 실행하고, 주석(annotation)으로 결과를 읽는 것**뿐이다.

---

## 1. 준비 (세션에 저장소가 없을 때)

1. `mcp__claude-code-remote__add_repo`로 `phdkimworld/kimworld-site`를 붙인다(`access: "push"` — 워크플로 실행에 쓰기 권한이 필요).
2. 도구가 알려 준 명령으로 복제한다(예: `/home/claude/kimworld-site`). 이미 있으면 `git pull --rebase origin main`.
3. `gh`는 REST만 된다(`gh api ...`). `gh run`·`gh workflow` 같은 편의 명령 대신 아래 `gh api` 예시를 그대로 쓴다.

---

## 2. 자주 하는 일

### 2-1. 특정 리포트 하나를 지금 올리기
```bash
gh api -X POST repos/phdkimworld/kimworld-site/actions/workflows/blogger.yml/dispatches \
  -f ref=main -f 'inputs[slug]=iren-2026-10-3'
```
- `slug`는 `content/reports/<slug>.md`의 파일 이름(확장자 없이).
- slug를 주면 공개 7일 제한과 하루 2건 제한을 무시하고 그 리포트 하나만 올린다.
- 이미 `posted.json`에 있으면 아무것도 안 하고 성공으로 끝난다(같은 글이 두 번 생기지 않게).
- 사이트에서 그 리포트 주소가 아직 200으로 안 열리면 건너뛴다. **새 리포트는 `Build and deploy` 성공을 확인한 뒤에** 실행한다.

### 2-2. 올리기 전에 미리보기 (실제로 올리지 않음)
```bash
gh api -X POST repos/phdkimworld/kimworld-site/actions/workflows/blogger.yml/dispatches \
  -f ref=main -f 'inputs[slug]=mbot-2026-10' -f 'inputs[dry]=1'
```
결과 주석 `미리보기 <slug>`에 제목·라벨·본문 앞 500자가 나온다. 세션 안에서도 같은 미리보기를 볼 수 있다(인증 불필요):
```bash
DRY=1 SLUG=mbot-2026-10 python3 scripts/blogger_post.py
```

### 2-3. 자동 규칙대로 한 번 돌리기
```bash
gh api -X POST repos/phdkimworld/kimworld-site/actions/workflows/blogger.yml/dispatches -f ref=main
```
오늘 이미 2건 올렸으면 `올릴 글 없음(후보 n, 오늘 2/2)`으로 끝난다.

### 2-4. 결과 확인 (반드시 한다)
워크플로 로그 내려받기는 프록시가 막는다(Forbidden). 대신 **주석**을 읽는다.
```bash
sleep 15   # 실행이 목록에 나타날 때까지
R=$(gh api "repos/phdkimworld/kimworld-site/actions/workflows/blogger.yml/runs?per_page=1" --jq '.workflow_runs[0].id')
# 끝날 때까지 기다리기(보통 30초~1분)
until [ "$(gh api repos/phdkimworld/kimworld-site/actions/runs/$R --jq .status)" = completed ]; do sleep 10; done
gh api repos/phdkimworld/kimworld-site/actions/runs/$R --jq .conclusion
J=$(gh api repos/phdkimworld/kimworld-site/actions/runs/$R/jobs --jq '.jobs[0].id')
gh api repos/phdkimworld/kimworld-site/check-runs/$J/annotations --jq '.[]|.message' | grep -v -i "node\|ubuntu"
```
주석 읽는 법:
- `BLOGGER_REFRESH_TOKEN 설정함` 등: 비밀값이 있는지(값은 안 나온다)
- `블로거 인증` — `GOOGLE_CLIENT_SECRET + 클라이언트 385980026755… 로 성공`: 어떤 조합으로 통했는지
- `블로거 인증 실패` — 조합별 구글 응답(오류 코드). 4장 참고
- `블로거 게시` — `<slug> → https://phdkimworld.blogspot.com/...`: **성공. 이 주소를 운영자에게 알린다**
- `블로거 HTTP nnn` — 게시 단계 오류와 구글 응답 본문
- 주석이 하나도 없고 성공이면: 올릴 글이 없었던 것(이미 올렸거나 7일 지난 리포트)

글 화면은 세션에서 확인할 수 없다(셸은 blogspot.com에 못 닿고, WebFetch는 사용자가 준 주소만 연다). 운영자에게 주소를 주고 확인을 부탁한다.

### 2-5. 리포트 제작(김박사 월드 스튜디오) 뒤에 붙여 쓰기
새 리포트를 발행하고 `Build and deploy` 성공 → 리포트 주소가 열리는 것까지 확인했다면, 다음 자동 실행(하루 두 번)을 기다려도 되고 2-1로 바로 올려도 된다. 바로 올릴 때도 **그날 이미 2건 올렸는지** `social/blogger/posted.json`의 `at` 날짜로 먼저 확인한다(수동 실행은 하루 제한을 무시하므로 에이전트가 스스로 지킨다).

---

## 3. 글 내용 (바꾸려면 `scripts/blogger_post.py`의 `body()`와 `short_title()`만)

- **제목**: 리포트 `title`에서 ` | 주가 내러티브와 패턴 투자전략` 앞부분만(140자 이내)
- **본문 순서**
  1. 대표 이미지 `https://drkimworld.com/og/<slug>.png` (누르면 리포트로)
  2. 리포트 `summary`
  3. `핵심 3줄` — `key_points` 앞 3개
  4. 주황 버튼 "이벤트 카드·반복 패턴·체크리스트까지 전체 리포트 무료로 보기 →"
     링크: `https://drkimworld.com/r/<slug>/?utm_source=blogger&utm_medium=post&utm_campaign=<slug>` (사이트 통계에서 블로거 유입으로 잡힌다)
  5. 유튜브 영상 임베드(`youtube_id`가 11자일 때만)
  6. 회색 작은 글씨: 숫자 기준일, 교육용·매매 권유 아님, 김박사 월드 홈 링크
- **라벨**: 티커, 테마, `미국주식`
- 블로거 글 주소는 제목이 한글이라 블로거가 정한다(`/2026/10/8.html`처럼). 바꿀 수 없고 바꿀 필요도 없다

**지켜야 할 규칙**
- 리포트 본문을 옮기지 않는다. 같은 내용이 두 곳에 있으면 구글이 블로거 쪽을 원본으로 골라 사이트 리포트가 밀릴 수 있다
- 하루 2건을 넘기지 않는다. 짧은 글을 몰아 올리면 스팸 패턴으로 보인다
- 사이트 규칙과 같다: 매수·매도 지시, 수익 암시, 긴급성 압박, 운영자 종목 보유 여부, AI 작성 언급 금지
- 리포트가 아닌 홍보글은 이 워크플로로 올리지 않는다(필요하면 운영자에게 먼저 묻는다)

---

## 4. 오류별 대처

| 주석에 보이는 것 | 뜻 | 할 일 |
| --- | --- | --- |
| `invalid_client` / "The provided client secret is invalid" | 보안 비밀번호가 클라이언트와 안 맞음 | 다른 조합이 성공했으면 무시. 모두 실패면 운영자에게 5-2를 부탁 |
| `invalid_grant` / "Token has been expired or revoked" | 갱신 토큰 만료·철회(운영자가 구글 계정 보안 화면에서 앱 연결을 끊었거나, 비밀번호 변경 등) | 운영자에게 5-3을 부탁 |
| `unauthorized_client` | 갱신 토큰이 다른 클라이언트(예: Playground 기본 클라이언트)로 발급됨 | 5-3을 다시. Playground에서 "Use your own OAuth credentials" 체크를 꼭 |
| 게시 단계 `403` | 토큰 발급 계정이 블로그 주인이 아님 | 5-3에서 블로그 주인 계정을 고르게 안내(운영자는 계정이 여러 개) |
| 게시 단계 `404` | 블로그 ID가 틀림 | 워크플로 `BLOGGER_BLOG_ID` 확인(블로거 관리 화면 주소의 `blog/posts/<숫자>`) |
| `429` / quota | 구글 API 쿼터 | 다음 날 다시. 재시도를 반복하지 않는다 |
| `갱신 토큰 또는 보안 비밀번호가 없어 건너뜀` | 비밀값 없음 | 5-3(토큰) 또는 5-2(비밀번호) |
| `<slug>: 아직 사이트에 안 열림, 건너뜀` | 배포 전 | `Build and deploy` 성공 뒤 다시 실행 |

오류 원인을 좁힐 때 비밀값 **내용**은 절대 출력하지 않는다. 필요하면 길이와 접두어만 본다(보안 비밀번호는 `GOCSPX-`로 시작하는 35자 안팎, 갱신 토큰은 `1//`로 시작하는 100자 안팎).

---

## 5. 운영자에게 부탁할 때 쓸 안내 (운영자는 휴대폰으로 한다. 링크와 순서를 짧게)

### 5-1. 콘솔 위치
- 클라이언트 목록: https://console.cloud.google.com/auth/clients (프로젝트 `drkimworld`) → **drkimworld web**
- 클라이언트 ID(공개값): `385980026755-sdef5j26m2kk509tuiec56s3099jc8av.apps.googleusercontent.com`
- 승인된 리디렉션 URI: `https://api.drkimworld.com/v1/auth/google/callback`(사이트 로그인 — 지우면 안 됨), `https://developers.google.com/oauthplayground`(토큰 발급용, 2026-10-25 추가)
- GitHub 비밀값: https://github.com/phdkimworld/kimworld-site/settings/secrets/actions

### 5-2. 보안 비밀번호 다시 넣기
1. drkimworld web 화면 오른쪽 위 ⓘ → Client secrets → **+ Add secret** → `GOCSPX-…` 복사(한 번만 보인다)
2. GitHub 비밀값 `BLOGGER_CLIENT_SECRET`을 그 값으로 바꾸기(연필 아이콘)
3. **기존 비밀번호는 삭제·사용 중지하지 말 것** — 사이트 구글 로그인(`GOOGLE_CLIENT_SECRET`)이 쓴다
(2026-10-25 현재 `BLOGGER_CLIENT_SECRET`은 invalid이고 `GOOGLE_CLIENT_SECRET`으로 게시가 된다. 스크립트가 둘 다 시도하므로 하나만 맞으면 된다)

### 5-3. 갱신 토큰 다시 받기
1. https://developers.google.com/oauthplayground
2. 오른쪽 위 ⚙ → **Use your own OAuth credentials** 체크 → 5-1의 클라이언트 ID + 그 클라이언트의 보안 비밀번호 → Close
3. 왼쪽 Step 1 입력칸에 `https://www.googleapis.com/auth/blogger` → **Authorize APIs**
4. **블로그 주인 계정**을 고른다. "확인되지 않은 앱" 경고면 고급 → 이동 → 허용
5. Step 2 **Exchange authorization code for tokens** → **Refresh token** 복사
6. GitHub 비밀값 `BLOGGER_REFRESH_TOKEN`을 그 값으로 바꾸기
7. 끝나면 세션이 2-1(또는 2-2 미리보기 없이 실제)로 시험 게시하고 2-4로 확인

---

## 6. 동작 원리 (코드를 고칠 때)

`scripts/blogger_post.py`
1. `social/blogger/posted.json`을 읽어 이미 올린 slug를 뺀다
2. `content/reports/*.md` 머리말을 읽어 후보를 고른다: `draft`가 아니고, `date`가 오늘(동부) 이전이며, 자동 모드면 7일 이내
3. 인증 `token()`: 클라이언트 ID(워크플로의 공개값, 그다음 비밀값 `GOOGLE_CLIENT_ID`) × 보안 비밀번호(`BLOGGER_CLIENT_SECRET`, 그다음 `GOOGLE_CLIENT_SECRET`) 조합을 차례로 `https://oauth2.googleapis.com/token`(grant_type=refresh_token)에 보내 첫 성공의 access token을 쓴다
4. `live()`: `https://drkimworld.com/r/<slug>/`가 200인지 HEAD로 확인
5. `publish()`: `POST https://www.googleapis.com/blogger/v3/blogs/<블로그 ID>/posts/` (`title`, `content`(HTML), `labels`)
6. 성공하면 `posted.json`에 기록하고 워크플로의 Commit 단계가 `social/blogger/`만 커밋·푸시(4번 재시도)

워크플로 `blogger.yml`
- `concurrency: social` — SNS 게시 워크플로들과 동시에 돌지 않는다
- `social/blogger/**`, 이 워크플로, 이 스크립트만 바뀐 커밋은 사이트를 다시 배포하지 않는다(`deploy.yml` paths-ignore)
- 입력: `slug`(하나만), `dry`(1이면 미리보기)
- 환경: `BLOGGER_DAILY`(기본 2)로 하루 한도를 바꿀 수 있지만, 운영자 동의 없이 올리지 않는다

**고친 뒤 확인 순서**: `python3 -c "import ast;ast.parse(open('scripts/blogger_post.py').read())"` → 세션에서 `DRY=1 SLUG=<slug> python3 scripts/blogger_post.py` → 커밋·푸시 → 2-2 미리보기 실행 → (필요하면) 2-1 실제 게시 → 2-4 확인. 사이트 규칙상 `python3 tests/test_build.py`·`python3 build.py --strict`도 통과해야 한다(로컬 디스크가 모자라면 푸시 뒤 `Build and deploy`의 테스트 단계 성공으로 확인).

---

## 7. 하지 말 것
- 비밀값을 출력·커밋·채팅에 붙여 넣기, 운영자에게 채팅으로 보내 달라고 하기(GitHub 비밀값 화면에 직접 넣게 한다)
- 세션에서 OAuth 동의 화면을 열거나 토큰을 직접 발급받으려 하기
- 같은 리포트를 다시 올리려고 `posted.json`을 지우기(운영자가 원할 때만)
- 블로거 글을 지우거나 고치기(API로 가능하지만 이 워크플로에는 없다. 필요하면 운영자에게 블로거 관리 화면에서 하도록 안내)
- 하루 2건을 넘겨 몰아 올리기, 리포트가 아닌 글 대량 게시
