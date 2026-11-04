-- 구글 블로거 글 아래 쿠팡 배너(하위 ID blogger) 클릭·수수료(2026-11-04)
ALTER TABLE coupang_daily ADD COLUMN clicks_blogger INTEGER;
ALTER TABLE coupang_daily ADD COLUMN commission_blogger INTEGER;
