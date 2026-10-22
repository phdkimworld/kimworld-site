-- 네이버 로그인 별명을 첫 닉네임 값으로 쓰기 위해 로그인 직후 10분만 보관(가입하면 지움). 2026-10-22 네이버 검수 대응
CREATE TABLE IF NOT EXISTS oauth_nick (actor TEXT PRIMARY KEY, nick TEXT NOT NULL, exp INTEGER NOT NULL);
