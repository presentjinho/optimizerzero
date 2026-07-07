const CACHE_NAME = "optimizerzero-web-lite-v21";
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
  "./vendor/pdfjs/pdf.min.js",
  "./vendor/pdfjs/pdf.worker.min.js",
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
  // cache: "reload" bypasses the browser HTTP cache -- without it a new
  // service worker version can faithfully re-cache STALE bytes the HTTP
  // cache is still holding, and no amount of SW cache clearing fixes that.
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_ASSETS.map((url) => new Request(url, { cache: "reload" })))),
  );
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
    // ignoreSearch: app scripts are requested with a ?vNN cache-buster (so
    // uncontrolled/raced worker importScripts can't revive stale HTTP-cache
    // bytes); inside the SW cache the version is already CACHE_NAME's job.
    caches.match(event.request, { ignoreSearch: true }).then((cached) => {
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
