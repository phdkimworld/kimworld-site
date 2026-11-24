// www.drkimworld.com → https://drkimworld.com 301(경로·쿼리 유지). 2026-11-24 SEO 점검: www가 522로 끊기던 것.
// 워커 사용자 지정 도메인(www.drkimworld.com)으로 붙인다(토큰에 영역 라우트 권한이 없어서, 김박사 몰과 같은 방식).
export default {
  fetch(req) {
    const u = new URL(req.url);
    return Response.redirect("https://drkimworld.com" + u.pathname + u.search, 301);
  },
};
