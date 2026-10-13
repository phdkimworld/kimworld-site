-- 운영자 애널리틱스(합계만 저장, 사람 정보 없음)
-- an_page: 날짜·주소별 페이지뷰·활동 시간(초)·휴대폰 수·첫 페이지 수·스크롤 깊이 합
CREATE TABLE IF NOT EXISTS an_page (day TEXT NOT NULL, path TEXT NOT NULL, t TEXT NOT NULL DEFAULT 'o', pv INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0,
  mob INTEGER NOT NULL DEFAULT 0, entries INTEGER NOT NULL DEFAULT 0, scroll INTEGER NOT NULL DEFAULT 0, scroll_n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, path));
-- an_src: 날짜·유입 경로별 방문(세션)·2페이지 이상 본 세션·처음 온 기기
CREATE TABLE IF NOT EXISTS an_src (day TEXT NOT NULL, src TEXT NOT NULL, sess INTEGER NOT NULL DEFAULT 0, multi INTEGER NOT NULL DEFAULT 0, newv INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, src));
-- an_hour: 한국 시각 기준 시간대별 페이지뷰
CREATE TABLE IF NOT EXISTS an_hour (day TEXT NOT NULL, h INTEGER NOT NULL, pv INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, h));
-- an_seen: 그날 방문한 기기(기기 번호의 해시). 순방문자·주간/월간 방문자 계산용, 35일 뒤 지움
CREATE TABLE IF NOT EXISTS an_seen (day TEXT NOT NULL, vh TEXT NOT NULL, PRIMARY KEY (day, vh));
-- 운영자 계정(애널리틱스 화면을 볼 수 있는 계정). Moderate 워크플로의 owner 결정으로 넣는다
CREATE TABLE IF NOT EXISTS owners (uid INTEGER PRIMARY KEY);
