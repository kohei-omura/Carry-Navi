// Carry Navi ライブ価格プロキシ（Cloudflare Workers・無料枠でOK）
// GMOコイン外国為替FXの公開API(ticker/klines)はブラウザから直接呼べない(CORS不可)ため、これを経由します。
// すでにFX Navi用のWorkerがあれば、それのURLをアプリの設定に貼るだけでOK（この仕様と互換）。
//   GET  /                      → ticker(全ペアのbid/ask)
//   GET  /?path=/public/v1/...  → 公開APIの中継（klinesは &last=N で末尾N本に間引き）
const API = "https://forex-api.coin.z.com";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Cache-Control": "no-store",
};
export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const u = new URL(req.url);
    const path = u.searchParams.get("path") || "/public/v1/ticker";
    if (!path.startsWith("/public/v1/")) return new Response("forbidden", { status: 403, headers: CORS });
    const r = await fetch(API + path, { cf: { cacheTtl: 0 } });
    let body = await r.text();
    const last = parseInt(u.searchParams.get("last") || "0", 10);
    if (last > 0) {
      try { const j = JSON.parse(body); if (Array.isArray(j.data)) { j.data = j.data.slice(-last); body = JSON.stringify(j); } } catch (_) {}
    }
    return new Response(body, { status: r.status, headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" } });
  },
};
