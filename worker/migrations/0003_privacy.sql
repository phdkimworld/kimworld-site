-- 개인정보 줄이기·같은 IP 공유 문제 해결
-- 1) IP 해시는 '그날의 무작위 값'으로 만들고 이틀 뒤 그 값을 지운다 → 지난 기록은 운영자도 되돌릴 수 없다
-- 2) 내 댓글·좋아요의 주인은 IP가 아니라 기기에 저장한 무작위 번호로 정한다(통신사 공용 IP를 쓰는 사람끼리 섞이지 않게)
CREATE TABLE IF NOT EXISTS peppers (day TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rate (k TEXT PRIMARY KEY, n INTEGER NOT NULL, exp INTEGER NOT NULL);
ALTER TABLE comments ADD COLUMN did TEXT;
CREATE INDEX IF NOT EXISTS comments_did ON comments (did);
-- 예전 방식(고정 비밀값) IP 해시는 지운다. 좋아요·신고 수는 그대로 두고 누가 눌렀는지 연결만 끊는다
UPDATE comments SET ih = 'legacy';
UPDATE comment_likes SET ih = 'legacy-' || rowid;
UPDATE comment_reports SET ih = 'legacy-' || rowid;
UPDATE post_likes SET ih = 'legacy-' || rowid;
DELETE FROM view_seen;
DELETE FROM search_seen;
