// Service worker for 02680 stock tracker
const CACHE_NAME = 'stock-02680-v4';
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
    ).then(() => self.clients.claim()).then(() => {
      // Notify all clients to reload so they get fresh HTML
      return self.clients.matchAll({ type: 'window' }).then((clients) => {
        clients.forEach((client) => client.postMessage({ type: 'SW_UPDATED' }));
      });
    })
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Only handle same-origin requests; let external APIs fail naturally
  if (url.origin !== self.location.origin) return;

  // Always bypass cache for HTML — force fresh fetch
  const isHtml = url.pathname.endsWith('.html');
  const isQuote = url.pathname.includes('stock_02680_quote.json');

  if (isHtml) {
    // Network-only for HTML to avoid any stale version
    event.respondWith(
      fetch(event.request, { cache: 'no-store' })
        .then((resp) => {
          if (resp && resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return resp;
        })
        .catch(() => caches.match(event.request).then((c) => c || new Response('offline', { status: 503 })))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (isQuote) {
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
      // Cache-first for static assets
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
