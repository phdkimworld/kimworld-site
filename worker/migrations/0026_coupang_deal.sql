-- 쿠팡 '오늘의 특가'(골드박스, 하위 ID deal) 클릭·수수료를 따로 센다(2026-10-30)
ALTER TABLE coupang_daily ADD COLUMN clicks_deal INTEGER;
ALTER TABLE coupang_daily ADD COLUMN commission_deal INTEGER;
