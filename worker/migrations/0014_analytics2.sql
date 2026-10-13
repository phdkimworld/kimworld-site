-- 운영 통계 확장(모두 날짜별 합계, 사람 정보 없음)
-- 앱(홈 화면에 설치한 웹앱)으로 연 방문
ALTER TABLE an_seen ADD COLUMN app INTEGER NOT NULL DEFAULT 0;
ALTER TABLE an_page ADD COLUMN app INTEGER NOT NULL DEFAULT 0;
-- 행동 이벤트(공유·저장·설치·로그인 시작 등) 날짜별 횟수
CREATE TABLE IF NOT EXISTS an_event (day TEXT NOT NULL, ev TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, ev));
-- 첫 페이지 × 유입 경로(어느 영상·검색이 어느 리포트로 데려왔나)
CREATE TABLE IF NOT EXISTS an_entry (day TEXT NOT NULL, path TEXT NOT NULL, src TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, path, src));
-- 운영체제 × 브라우저(카카오톡·네이버·유튜브 앱 안 브라우저 포함)
CREATE TABLE IF NOT EXISTS an_tech (day TEXT NOT NULL, os TEXT NOT NULL, br TEXT NOT NULL, pv INTEGER NOT NULL DEFAULT 0, sess INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, os, br));
-- 사이트 검색에서 결과가 없던 검색어(만들 리포트 후보)
CREATE TABLE IF NOT EXISTS search_miss (day TEXT NOT NULL, q TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, q));
