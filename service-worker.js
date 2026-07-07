const CACHE_NAME = "optimizerzero-web-lite-v15";
const APP_ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./optimize-core.js",
  "./worker.js",
  "./avif-jxl-worker.js",
  "./README.md",
  "./PRIVACY.md",
  "./manifest.webmanifest",
  "./icon.svg",
  "./vendor/jszip.min.js",
  "./vendor/pdf-lib.min.js",
  "./vendor/jsquash-avif/avif_enc.js",
  "./vendor/jsquash-avif/avif_enc.wasm",
  "./vendor/jsquash-avif/encode.js",
  "./vendor/jsquash-avif/meta.js",
  "./vendor/jsquash-avif/utils.js",
  "./vendor/jsquash-jxl/encode.js",
  "./vendor/jsquash-jxl/jxl_enc.js",
  "./vendor/jsquash-jxl/jxl_enc.wasm",
  "./vendor/jsquash-jxl/meta.js",
  "./vendor/jsquash-jxl/utils.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match("./index.html"));
    }),
  );
});
