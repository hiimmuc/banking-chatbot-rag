// Pass-through proxy: keeps a Cloudflare-hosted address in front of the Funnel origin. Nothing is stored here.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const target = new URL(url.pathname + url.search, env.ORIGIN);
    const headers = new Headers(request.headers);
    headers.set("x-forwarded-for", request.headers.get("cf-connecting-ip") || "");
    headers.delete("cf-connecting-ip");
    return fetch(new Request(target, { method: request.method, headers, body: request.body, redirect: "manual" }));
  },
};
