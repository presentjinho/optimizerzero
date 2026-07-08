// One worker per pool slot. Loaded classic (not module) so the vendored
// UMD builds and optimize-core.js attach their globals to this scope exactly
// like they do to `window` on the main thread.
importScripts("./vendor/jszip.min.js?v23", "./vendor/pdf-lib.min.js?v23", "./vendor/pdfjs/pdf.min.js?v23");

// pdf.js cannot spawn its own nested worker from inside a worker, and its
// fake-worker fallback needs `document` -- unless globalThis.pdfjsWorker
// already exists. Loading pdf.worker.min.js into this same scope provides
// that. Its load-time "ready" handshake posts to our parent though, which
// would leak a junk message into the pool protocol -- swallow postMessage
// for the duration of the import.
{
  const realPostMessage = self.postMessage.bind(self);
  self.postMessage = () => {};
  importScripts("./vendor/pdfjs/pdf.worker.min.js?v23");
  self.postMessage = realPostMessage;
}

importScripts("./optimize-core.js?v23");

self.onmessage = async (event) => {
  const { file, opts } = event.data;
  try {
    const result = await optimizeFile(file, opts);
    self.postMessage({ ok: true, result });
  } catch (error) {
    self.postMessage({ ok: false, error: error.message || String(error) });
  }
};
