const CACHE = "mosaika-sopralluogo-v1";
const SHELL = [
  "/sopralluogo/",
  "/sopralluogo/index.html",
  "/sopralluogo/css/app.css",
  "/sopralluogo/js/app.js",
  "/sopralluogo/js/coda.js",
  "/sopralluogo/manifest.webmanifest",
  "/css/app.css",
  "/icons/icon-192.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.method !== "GET") return;
  if (url.pathname.includes("/export") || url.pathname.includes("/file/")) return;
  const api = url.pathname.startsWith("/api/sopralluogo");
  const shell = url.pathname.startsWith("/sopralluogo")
    || url.pathname.startsWith("/css/")
    || url.pathname.startsWith("/icons/");
  if (!api && !shell) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copia = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copia));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
