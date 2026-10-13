-- 인용 글: 리포트(q_kind 'r', q_ref = 리포트 주소 이름) 또는 남의 글(q_kind 'p', q_ref = 글 번호)의 일부(q_text, 300자까지)를 인용
ALTER TABLE comments ADD COLUMN q_kind TEXT;
ALTER TABLE comments ADD COLUMN q_ref TEXT;
ALTER TABLE comments ADD COLUMN q_text TEXT;
