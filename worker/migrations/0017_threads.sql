-- 0017: 쓰레드 구조 — 답글도 원글과 같은 '글'
-- · 답글은 바로 위 글(parent_id)에 달린다(예전처럼 원글 아래로 모으지 않음). 답글에도 답글·좋아요·리포스트·인용·공유·조회수
-- · 조회수: 글이 화면에 보이면(피드·글 상세) 한 번. 같은 사람(그날의 IP 해시)·같은 글은 하루 한 번만 센다(리포트 조회수와 같은 방식)
ALTER TABLE comments ADD COLUMN views INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS post_seen (day TEXT NOT NULL, cid INTEGER NOT NULL, ih TEXT NOT NULL, PRIMARY KEY (day, cid, ih));
