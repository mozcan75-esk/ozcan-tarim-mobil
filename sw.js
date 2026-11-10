// V3.1.3: network-first navigation and stale-while-revalidate assets.
const CACHE = 'ozcan-test-v410';
const FILES = ['./index.html', './style.css?v=410', './app.js?v=410', './combined318.js?v=410', './extended.js?v=410', './dashboard.js?v=410', './ui314.js?v=410', './ui315.js?v=410', './harvest319.js?v=410', './crop320.js?v=410', './season322.js?v=410', './harvest323.js?v=410', './bales324.js?v=410', './profit325.js?v=410', './records357.js?v=410', './depot358.js?v=410', './mobile359.js?v=410', './mobile406.js?v=410', './settings407.js?v=410', './catalog409.js?v=410', './manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('ozcan-test-') && key !== CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(req, {cache:'no-store'});
        if (response.ok) {
          const cache = await caches.open(CACHE);
          await cache.put('./index.html', response.clone());
        }
        return response;
      } catch (_) {
        return (await caches.match('./index.html')) || Response.error();
      }
    })());
    return;
  }
  event.respondWith((async () => {
    const cached = await caches.match(req);
    if (cached) return cached;
    const response = await fetch(req);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(req, response.clone()).catch(() => {});
    }
    return response;
  })());
});
