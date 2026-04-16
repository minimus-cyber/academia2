const CACHE = "academia-v2";
const STATIC = ["/academia/", "/academia/index.html", "/academia/style.css",
                "/academia/app.js", "/academia/wiki.js", "/academia/lab.js"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  if (e.request.url.includes("/api/")) return; // never cache API calls
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
