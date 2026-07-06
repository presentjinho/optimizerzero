# OptimizerZero Web Lite Privacy

OptimizerZero Web Lite is designed to run locally in your browser.

## What Happens

- Selected files are processed in the browser.
- Files are not uploaded to an OptimizerZero server.
- The app does not include analytics, tracking pixels, or remote logging.
- JSZip and pdf-lib are bundled in `vendor/`, so archive and PDF support do not require a CDN after deploy.
- Reports are generated only when you click the report button.

## Browser Storage

- The service worker caches the app files so it can reopen faster and work offline after the first load.
- Optimized output files are created as temporary browser downloads.
- OptimizerZero does not intentionally store your selected files in persistent app storage.

## Limits

- Very large files can still fail if the browser runs out of memory.
- If you deploy behind Cloudflare Access or another login layer, that provider may keep access logs.
- If you edit the app to add analytics or server upload features, this privacy note must be updated.
