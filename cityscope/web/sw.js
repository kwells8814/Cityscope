/* CityScope service worker.
   Strategy:
   - App shell (HTML/manifest/icons): cache-first so the app launches instantly
     and works offline (shows the last-cached shell).
   - API calls (/happenings, /resolve, /health): network-first, because data
     should be fresh; falls back to nothing if offline (the app then uses its
     embedded sample data).
   Bump CACHE_VERSION to force clients to pick up new files. */

const CACHE_VERSION = "cityscope-v1";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isApi(url) {
  return /\/(happenings|resolve|health|ics)\b/.test(url.pathname);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // network-first for the API (fresh data), no caching of dynamic results
  if (isApi(url)) {
    event.respondWith(fetch(req).catch(() => new Response("", { status: 503 })));
    return;
  }

  // cache-first for the app shell / static assets
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        // cache new static assets opportunistically
        const copy = res.clone();
        caches.open(CACHE_VERSION).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match("./index.html"));
    })
  );
});
