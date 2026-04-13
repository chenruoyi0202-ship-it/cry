// Service worker for 02680 stock tracker
const CACHE_NAME = 'stock-02680-v1';
const CORE_ASSETS = [
  './02680.html',
  './02680-apple-icon.png',
  './02680-icon.png',
  './02680-icon.svg',
  './data/stock_02680_quote.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Only handle same-origin requests; let external APIs fail naturally
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      // Network-first for the HTML page and quote JSON (always try fresh)
      const isHtml = url.pathname.endsWith('.html');
      const isQuote = url.pathname.includes('stock_02680_quote.json');
      if (isHtml || isQuote) {
        return fetch(event.request)
          .then((resp) => {
            if (resp && resp.ok) {
              const clone = resp.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return resp;
          })
          .catch(() => cached || new Response('offline', { status: 503 }));
      }
      // Cache-first for static assets (icons, etc.)
      return cached || fetch(event.request).then((resp) => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return resp;
      });
    })
  );
});
