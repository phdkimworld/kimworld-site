-- 소셜 로그인(구글·카카오) 세션, 로그인 중간 확인값, 종토방 공지(고정 글)
CREATE TABLE IF NOT EXISTS sessions (th TEXT PRIMARY KEY, actor TEXT NOT NULL, created INTEGER NOT NULL, exp INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_actor ON sessions (actor);
CREATE TABLE IF NOT EXISTS oauth_state (state TEXT PRIMARY KEY, provider TEXT NOT NULL, ret TEXT NOT NULL, exp INTEGER NOT NULL);
ALTER TABLE comments ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
-- 계정 키로 만든 계정은 더 이상 로그인할 수 없으므로 정리한다(글은 '탈퇴한 사용자'로 남김)
UPDATE comments SET uid = NULL, nick = '탈퇴한 사용자' WHERE uid IN (SELECT id FROM users WHERE actor NOT LIKE 'o-%');
DELETE FROM follows WHERE follower IN (SELECT id FROM users WHERE actor NOT LIKE 'o-%') OR followee IN (SELECT id FROM users WHERE actor NOT LIKE 'o-%');
DELETE FROM notifs WHERE uid IN (SELECT id FROM users WHERE actor NOT LIKE 'o-%');
DELETE FROM users WHERE actor NOT LIKE 'o-%';
