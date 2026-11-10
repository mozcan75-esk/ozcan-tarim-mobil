// V5.3.3 - reliable GitHub Pages update, offline fallback. Does not modify user data.
const CACHE = 'ozcan-mobile-v533';
const FILES = ['./index.html', './style.css?v=533', './manifest.webmanifest', './app.js?v=533', './combined318.js?v=533', './extended.js?v=533', './dashboard.js?v=533', './ui314.js?v=533', './ui315.js?v=533', './harvest319.js?v=533', './crop320.js?v=533', './season322.js?v=533', './harvest323.js?v=533', './bales324.js?v=533', './profit325.js?v=533', './records357.js?v=533', './depot358.js?v=533', './mobile359.js?v=533', './mobile406.js?v=533', './settings407.js?v=533', './catalog409.js?v=533', './catalog411.js?v=533', './purchase413.js?v=533', './field510.js?v=533', './field520.js?v=533', './stock530.js?v=533', './backup533.js?v=533'];
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
