// Service Worker para PWA da agenda escolar.
const CACHE_NAME = 'agenda-v4-static-only';
const urlsToCache = [
  '/static/css/professor.css',
  '/static/css/dashboard.css',
  '/static/css/login.css',
  '/static/image/logo_escola.png',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  const isApi = url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/');
  const isNavigation = event.request.mode === 'navigate';

  if (isApi || isNavigation) {
    // HTML autenticado e formulários com CSRF nunca devem vir do cache.
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

