const CACHE_NAME = 'mediaflow-v2';
const ASSETS = [
  '/',
  '/static/css/custom.css',
  '/static/js/app.js',
  '/static/js/youtube.js',
  '/static/js/books.js',
  '/static/js/downloads.js',
  '/static/favicon.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  var url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) return;
  if (url.origin !== location.origin) return;

  e.respondWith(
    fetch(e.request)
      .then(function (resp) {
        if (resp.ok) {
          var clone = resp.clone();
          caches.open(CACHE_NAME).then(function (c) { c.put(e.request, clone); });
        }
        return resp;
      })
      .catch(function () {
        return caches.match(e.request);
      })
  );
});
