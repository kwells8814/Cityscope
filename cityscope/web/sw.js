/* CityScope service worker.
   Strategy:
   - HTML pages: NETWORK-FIRST so the app always loads the latest version when
     online (falls back to cached shell only when offline). This prevents the
     "stuck on an old cached page" problem.
   - Static assets (icons, manifest): cache-first for speed.
   - API calls (/happenings, /resolve, /health): network-first, never cached.
   Bump CACHE_VERSION when the shell list changes. */

const CACHE_VERSION = "cityscope-v9";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("message", (event) => {
  if (event.data === "skipWaiting") self.skipWaiting();
});

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
  return /\/(happenings|resolve|status|health|ics|map|feed-health)\b/.test(url.pathname);
}

function isHTML(req, url) {
  return req.mode === "navigate" ||
         req.destination === "document" ||
         url.pathname === "/" ||
         url.pathname.endsWith("/index.html");
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // API: network-first, never cached
  if (isApi(url)) {
    event.respondWith(fetch(req).catch(() => new Response("", { status: 503 })));
    return;
  }

  // HTML shell: network-first so updates always show; cache fallback offline
  if (isHTML(req, url)) {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_VERSION).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match(req).then((c) => c || caches.match("./index.html")))
    );
    return;
  }

  // Static assets: cache-first for speed
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_VERSION).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      });
    })
  );
});
