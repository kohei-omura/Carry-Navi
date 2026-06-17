// FX Carry Navi Service Worker — シェルはcache-first、データは常に最新(network-first)
const C='carrynavi-v2';
const SHELL=['index.html','carry.webmanifest','carry-icon-180.png','carry-icon-192.png','carry-icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.mode==='navigate'){e.respondWith(fetch(e.request).catch(()=>caches.match('index.html')));return;}
  if(u.pathname.endsWith('carry_status.json')||u.search.includes('action=')||u.hostname.includes('workers.dev')||u.hostname.includes('coin.z.com')){
    e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
