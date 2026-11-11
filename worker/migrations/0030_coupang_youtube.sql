-- 유튜브 영상 설명란·고정댓글 쿠팡 링크(하위 ID yt+카테고리+티커) 클릭·수수료(2026-11-10 카테고리 실험)
ALTER TABLE coupang_daily ADD COLUMN clicks_youtube INTEGER;
ALTER TABLE coupang_daily ADD COLUMN commission_youtube INTEGER;
