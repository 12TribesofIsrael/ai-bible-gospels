export default {
  async fetch(request) {
    const ORIGIN = 'tribesofisrael--ai-bible-gospels-web.modal.run';
    const url = new URL(request.url);
    url.hostname = ORIGIN;
    const proxied = new Request(url.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'manual',
    });
    return fetch(proxied);
  },
};
