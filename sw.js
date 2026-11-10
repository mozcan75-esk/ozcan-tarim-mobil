// V3.1.3: network-first navigation and stale-while-revalidate assets.
const CACHE = 'ozcan-test-v414';
const FILES = ['./index.html', './style.css?v=414', './app.js?v=414', './combined318.js?v=414', './extended.js?v=414', './dashboard.js?v=414', './ui314.js?v=414', './ui315.js?v=414', './harvest319.js?v=414', './crop320.js?v=414', './season322.js?v=414', './harvest323.js?v=414', './bales324.js?v=414', './profit325.js?v=414', './records357.js?v=414', './depot358.js?v=414', './mobile359.js?v=414', './mobile406.js?v=414', './settings407.js?v=414', './catalog409.js?v=414', './catalog411.js?v=414', './purchase413.js?v=414', './equivalent414.js?v=414', './manifest.webmanifest'];
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
