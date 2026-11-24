// www.drkimworld.com → https://drkimworld.com 301(경로·쿼리 유지). 2026-11-24 SEO 점검: www가 522로 끊기던 것.
// 워커 라우트(www.drkimworld.com/*)가 원 서버보다 먼저 받으므로 www DNS가 어디를 가리키든 넘겨준다.
export default {
  fetch(req) {
    const u = new URL(req.url);
    return Response.redirect("https://drkimworld.com" + u.pathname + u.search, 301);
  },
};
