-- 0018: 봇 걸러내기(2026-10-14) — 쓰레드 홍보 글 뒤 링크 검사·미리보기 봇이 방문 통계를 부풀렸다
-- 방문 통계·조회수·광고 통계에서 뺀 요청을 이유별로 합계만 남긴다(IP·주소 같은 개인 정보는 남기지 않는다)
-- why: ua(봇 이름표) · dc(데이터센터·클라우드 망) · idle(화면을 만지지도 머물지도 않음)
CREATE TABLE IF NOT EXISTS an_bot (day TEXT NOT NULL, why TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, why));
