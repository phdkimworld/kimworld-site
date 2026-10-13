-- 0015: 프로필 사진·차단·쪽지(DM)·이용자 신고 + 유입 분석 세분화

-- 프로필 사진: 브라우저가 정사각형 256px(webp/jpeg)으로 줄여 올린 것만. base64 문자열로 저장(64KB 이하)
ALTER TABLE users ADD COLUMN av INTEGER NOT NULL DEFAULT 0;          -- 사진 버전(0이면 없음). 주소 ?v= 에 붙여 캐시를 바꾼다
ALTER TABLE users ADD COLUMN dm_pref TEXT NOT NULL DEFAULT 'all';    -- all(누구나, 처음은 요청함) | following(내가 팔로우한 사람만) | none
CREATE TABLE IF NOT EXISTS avatars (
  uid INTEGER PRIMARY KEY,
  mime TEXT NOT NULL,
  data TEXT NOT NULL,
  v INTEGER NOT NULL,
  reports INTEGER NOT NULL DEFAULT 0
);

-- 차단: 서로 쪽지·팔로우 불가, 화면에서 그 사람 글 숨김
CREATE TABLE IF NOT EXISTS blocks (blocker INTEGER NOT NULL, blocked INTEGER NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (blocker, blocked));
CREATE INDEX IF NOT EXISTS blocks_blocked ON blocks (blocked);

-- 이용자 신고(프로필 사진·닉네임·소개). 같은 사람이 같은 대상·항목은 한 번
CREATE TABLE IF NOT EXISTS user_reports (uid INTEGER NOT NULL, by_actor TEXT NOT NULL, what TEXT NOT NULL, created INTEGER NOT NULL, PRIMARY KEY (uid, by_actor, what));

-- 쪽지: 두 사람 사이 대화방 하나(a < b). 처음 보낸 사람(starter)의 첫 쪽지는 상대가 수락하기 전까지 '요청'
CREATE TABLE IF NOT EXISTS dm_threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  a INTEGER NOT NULL, b INTEGER NOT NULL,
  starter INTEGER NOT NULL,
  accepted INTEGER NOT NULL DEFAULT 0,
  created INTEGER NOT NULL,
  last_at INTEGER NOT NULL,
  last_id INTEGER NOT NULL DEFAULT 0,
  last_from INTEGER NOT NULL DEFAULT 0,
  last_body TEXT NOT NULL DEFAULT '',
  a_read INTEGER NOT NULL DEFAULT 0, b_read INTEGER NOT NULL DEFAULT 0,   -- 마지막으로 읽은 쪽지 번호
  a_del INTEGER NOT NULL DEFAULT 0, b_del INTEGER NOT NULL DEFAULT 0,     -- 이 번호까지는 내 화면에서 지움(대화 삭제)
  UNIQUE (a, b)
);
CREATE INDEX IF NOT EXISTS dm_threads_a ON dm_threads (a, last_at);
CREATE INDEX IF NOT EXISTS dm_threads_b ON dm_threads (b, last_at);
CREATE TABLE IF NOT EXISTS dm_msgs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tid INTEGER NOT NULL,
  sender INTEGER NOT NULL,
  body TEXT NOT NULL,
  created INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'ok'   -- ok | deleted(보낸 사람이 지움) | hidden(운영자)
);
CREATE INDEX IF NOT EXISTS dm_msgs_tid ON dm_msgs (tid, id);
CREATE INDEX IF NOT EXISTS dm_msgs_sender ON dm_msgs (sender, created);
CREATE TABLE IF NOT EXISTS dm_reports (mid INTEGER NOT NULL, by_uid INTEGER NOT NULL, created INTEGER NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (mid, by_uid));

-- 유입 분석(합계만): 채널·세부 출처·매체·캠페인별 세션·페이지·체류·2페이지 이상·신규·휴대폰
CREATE TABLE IF NOT EXISTS an_acq (
  day TEXT NOT NULL, ch TEXT NOT NULL, src TEXT NOT NULL,
  pv INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0,
  sess INTEGER NOT NULL DEFAULT 0, multi INTEGER NOT NULL DEFAULT 0, deep INTEGER NOT NULL DEFAULT 0,
  newv INTEGER NOT NULL DEFAULT 0, mob INTEGER NOT NULL DEFAULT 0, app INTEGER NOT NULL DEFAULT 0,
  engaged INTEGER NOT NULL DEFAULT 0,   -- 30초 이상 읽은 페이지 수
  PRIMARY KEY (day, ch, src)
);
-- 리퍼러 호스트(주소의 도메인만) — 출처 분류가 맞는지, 처음 보는 사이트가 있는지 확인용
CREATE TABLE IF NOT EXISTS an_ref (day TEXT NOT NULL, host TEXT NOT NULL, sess INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, host));
-- 캠페인(UTM): 출처·매체·캠페인·내용별
CREATE TABLE IF NOT EXISTS an_camp (
  day TEXT NOT NULL, src TEXT NOT NULL, med TEXT NOT NULL, camp TEXT NOT NULL, cont TEXT NOT NULL,
  sess INTEGER NOT NULL DEFAULT 0, pv INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0, multi INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, src, med, camp, cont)
);
-- 출처별 전환 행동(가입·설치·로그인 시작·공유 등)
CREATE TABLE IF NOT EXISTS an_srcev (day TEXT NOT NULL, src TEXT NOT NULL, ev TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, src, ev));
-- 랜딩 페이지 × 세부 출처: 들어온 세션, 그 세션이 2페이지 이상 봤는지, 세션 전체 체류(유튜브 영상별 성과 = 리포트 랜딩 × youtube)
CREATE TABLE IF NOT EXISTS an_land (day TEXT NOT NULL, path TEXT NOT NULL, src TEXT NOT NULL, sess INTEGER NOT NULL DEFAULT 0, multi INTEGER NOT NULL DEFAULT 0, pv INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, path, src));
