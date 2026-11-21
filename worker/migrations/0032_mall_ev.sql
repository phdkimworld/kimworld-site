-- 김박사 몰 유입·클릭 추적(2026-11-20 운영자 "몰 페이지 트래픽 다각화해서 체계적으로 추적해서 저장하고 인사이트로 활용").
-- 하루 합계만. 사람 정보 없음. k: land(사이트 /mall/ 입구) · view(몰 화면) · click(쿠팡으로 나가는 링크)
-- src: 유입 채널(utm_source, 없으면 리퍼러 묶음) · pg: 몰 화면 종류(home·deals·c-<카테고리>·search·categories·about, 입구는 entry)
-- sl: 누른 칸(hero1·entry·deals·rank·cat 등, 화면 보기는 -) · n: 횟수 · u: 그날 같은 사람(IP 해시) 첫 번만 센 수
CREATE TABLE IF NOT EXISTS mall_ev (
  day TEXT NOT NULL,
  k TEXT NOT NULL,
  src TEXT NOT NULL,
  pg TEXT NOT NULL,
  sl TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  u INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, k, src, pg, sl)
);
