-- 0016: 댓글·종토방·라운지를 '커뮤니티' 하나로 합친다
-- 리포트에 달린 댓글(slug = 리포트 주소)은 그 리포트를 공유한 커뮤니티 글로 바꾼다:
--   원글 → 그 종목 묶음(b-티커)의 글 + 리포트 첨부(q_kind 'r', q_ref 리포트, q_text ''= 문장 인용 없이 리포트 공유)
--   답글 → 같은 묶음으로(원글 아래 그대로)
-- 리포트 주소는 항상 '티커-연-월' 꼴이라 첫 '-' 앞이 티커다.
UPDATE comments SET q_kind = 'r', q_ref = slug, q_text = ''
  WHERE slug NOT LIKE 'b-%' AND parent_id IS NULL AND q_kind IS NULL;
UPDATE notifs SET slug = 'b-' || substr(slug, 1, instr(slug, '-') - 1)
  WHERE type IN ('reply', 'like', 'mention', 'quote', 'repost') AND slug != '' AND slug NOT LIKE 'b-%' AND instr(slug, '-') > 1;
UPDATE comments SET slug = 'b-' || substr(slug, 1, instr(slug, '-') - 1)
  WHERE slug NOT LIKE 'b-%' AND instr(slug, '-') > 1;
-- 종목 묶음 공지의 이름도 바꾼다
UPDATE comments SET body = replace(replace(body, '종토방을 엽니다.', '커뮤니티를 엽니다.'), '종토방 규칙', '커뮤니티 규칙') WHERE pinned = 1;
CREATE INDEX IF NOT EXISTS comments_quote ON comments (q_kind, q_ref, status);
