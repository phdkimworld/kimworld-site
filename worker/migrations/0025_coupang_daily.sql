-- 쿠팡 파트너스 일별 실적(쿠팡 API 보고서, coupang-stats.yml이 매일 넣음). 공개 저장소 대신 여기에만 둔다(2026-10-28)
CREATE TABLE IF NOT EXISTS coupang_daily (
  day TEXT PRIMARY KEY,
  clicks INTEGER, clicks_banner INTEGER, clicks_boxes INTEGER, clicks_other INTEGER,
  orders INTEGER, gmv INTEGER, commission INTEGER, commission_banner INTEGER, commission_boxes INTEGER, commission_other INTEGER,
  click_addtags TEXT,
  updated INTEGER NOT NULL
);
