-- 쿠팡 상자 성과(학습용): 날짜·상품 묶음(sub_id)·자리·이용 환경별 노출·클릭 수. 사람을 알아볼 정보는 없다
CREATE TABLE IF NOT EXISTS ad_stats (
  day TEXT NOT NULL, g TEXT NOT NULL, slot TEXT NOT NULL, seg TEXT NOT NULL,
  imps INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, g, slot, seg)
);
