// V5.3.2 - reliable GitHub Pages update, offline fallback. Does not modify user data.
const CACHE = 'ozcan-mobile-v532';
const FILES = ['./index.html', './style.css?v=532', './manifest.webmanifest', './app.js?v=532', './combined318.js?v=532', './extended.js?v=532', './dashboard.js?v=532', './ui314.js?v=532', './ui315.js?v=532', './harvest319.js?v=532', './crop320.js?v=532', './season322.js?v=532', './harvest323.js?v=532', './bales324.js?v=532', './profit325.js?v=532', './records357.js?v=532', './depot358.js?v=532', './mobile359.js?v=532', './mobile406.js?v=532', './settings407.js?v=532', './catalog409.js?v=532', './catalog411.js?v=532', './purchase413.js?v=532', './field510.js?v=532', './field520.js?v=532', './stock530.js?v=532'];
self.addEventListener('install', e => e.waitUntil((async()=>{
 const c=await caches.open(CACHE);
 // Partial network failure must not block new worker activation.
 await Promise.allSettled(FILES.map(f=>c.add(f)));
 await self.skipWaiting();
})()));
self.addEventListener('activate', e => e.waitUntil((async()=>{
 const keys=await caches.keys();
 await Promise.all(keys.filter(k=>k.startsWith('ozcan-test-')||k.startsWith('ozcan-mobile-')).filter(k=>k!==CACHE).map(k=>caches.delete(k)));
 await self.clients.claim();
})()));
self.addEventListener('fetch', e=>{
 const req=e.request;
 if(req.method!=='GET'||new URL(req.url).origin!==self.location.origin)return;
 e.respondWith((async()=>{
  try {
   const response=await fetch(req,{cache:'no-store'});
   if(response.ok){const c=await caches.open(CACHE);c.put(req,response.clone()).catch(()=>{});}
   return response;
  } catch(err){
   const cached=await caches.match(req);
   if(cached)return cached;
   if(req.mode==='navigate')return (await caches.match('./index.html'))||Response.error();
   return Response.error();
  }
 })());
});
