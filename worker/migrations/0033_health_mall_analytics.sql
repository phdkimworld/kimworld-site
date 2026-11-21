-- 몰 방문·클릭 기록(2026-11-20 운영자 "몰 페이지 트래픽좀 다각화해서 체계적으로 잘 추적해서 저장해놓고 인사이트로 활용해").
-- 김박사 건강몰(site='health', health.drkimworld.com) 전용. 김박사 몰은 0032 mall_ev(/v1/mall)가 맡는다(다른 세션, 같은 날).
-- 본 사이트 an_* 표와 섞지 않는다(본 사이트 세션 수가 애드센스 재신청 기준이라 부풀리면 안 됨). 날짜별 합계만, 개인 식별값 없음. 영구 보관.
CREATE TABLE IF NOT EXISTS hm_page (day TEXT NOT NULL, site TEXT NOT NULL, path TEXT NOT NULL,
  pv INTEGER NOT NULL DEFAULT 0, sess INTEGER NOT NULL DEFAULT 0, secs INTEGER NOT NULL DEFAULT 0, engaged INTEGER NOT NULL DEFAULT 0,
  scroll INTEGER NOT NULL DEFAULT 0, scroll_n INTEGER NOT NULL DEFAULT 0, mob INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, site, path));
-- 세션 첫 페이지 기준 유입: 채널 > 세부 출처 > 캠페인(utm_campaign) > 랜딩
CREATE TABLE IF NOT EXISTS hm_acq (day TEXT NOT NULL, site TEXT NOT NULL, ch TEXT NOT NULL, src TEXT NOT NULL, camp TEXT NOT NULL, lp TEXT NOT NULL,
  sess INTEGER NOT NULL DEFAULT 0, engaged INTEGER NOT NULL DEFAULT 0, deep INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, site, ch, src, camp, lp));
-- 바깥으로 나간 클릭: kind = coupang(쿠팡 상품, sub = 쿠팡 하위 ID) · guide(가이드로 이동) · youtube · site(본 사이트) · mall(다른 몰) · other
CREATE TABLE IF NOT EXISTS hm_click (day TEXT NOT NULL, site TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL, sub TEXT NOT NULL, ch TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, site, path, kind, sub, ch));
