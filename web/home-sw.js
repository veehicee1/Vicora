/* GTMC Home CBT PWA shell. Never cache authenticated API traffic or answers. */
const CACHE_NAME = 'gtmc-home-shell-v1';
const SHELL_URLS = ['/home/', '/home/manifest.webmanifest', '/home/icon.svg', '/vicora-icon.svg'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(SHELL_URLS.map(url => cache.add(url)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key.startsWith('gtmc-home-shell-') && key !== CACHE_NAME)
          .map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Login, exam papers, timers, answers, messages and submissions stay network-only.
  if (url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate' && (url.pathname === '/home/' || url.pathname === '/home')) {
    event.respondWith(fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put('/home/', copy));
      }
      return response;
    }).catch(async () => {
      const cached = await caches.match('/home/');
      return cached || new Response('GTMC Home CBT needs an internet connection to sign in and retrieve examinations. Reconnect and reload this page.', {
        status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' }
      });
    }));
    return;
  }

  if (SHELL_URLS.includes(url.pathname)) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
      }
      return response;
    })));
  }
});
