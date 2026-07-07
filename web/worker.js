// One worker per pool slot. Loaded classic (not module) so the vendored
// UMD builds and optimize-core.js attach their globals to this scope exactly
// like they do to `window` on the main thread.
importScripts("./vendor/jszip.min.js", "./vendor/pdf-lib.min.js", "./optimize-core.js");

self.onmessage = async (event) => {
  const { file, opts } = event.data;
  try {
    const result = await optimizeFile(file, opts);
    self.postMessage({ ok: true, result });
  } catch (error) {
    self.postMessage({ ok: false, error: error.message || String(error) });
  }
};
