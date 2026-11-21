-- 2026-11-22 KST: 건강몰 추적 점검용 방문(캠페인 qa-test, 운영 세션이 크롬으로 확인)을 지운다.
-- 이때까지 건강몰 실제 방문은 0건이었으므로 그날 오메가3 페이지 줄도 모두 점검 방문이다.
DELETE FROM hm_acq WHERE camp LIKE 'qa-test%';
DELETE FROM hm_page WHERE day = '2026-11-22' AND path = '/guide/omega3/';
DELETE FROM hm_click WHERE day = '2026-11-22' AND path = '/guide/omega3/';
