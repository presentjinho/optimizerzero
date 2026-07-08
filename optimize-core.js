// Pure compression logic shared by the main thread (app.js) and the worker
// pool (worker.js). No DOM assumptions except an optional `document`-based
// canvas fallback — everything else works identically in a Worker.
const archiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"]);
const imageExts = new Set(["png", "jpg", "jpeg", "webp", "bmp", "gif"]);
const pdfExts = new Set(["pdf"]);
const archiveImageExts = new Set(["jpg", "jpeg", "webp", "bmp", "gif", "png"]);
const imageOptimizableArchiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"]);
const RECOMPRESSABLE_PDF_COLORSPACES = new Set(["DeviceRGB", "DeviceGray"]);
const IGNORABLE_ZIP_ENTRY_NAMES = new Set([".ds_store", "thumbs.db", "desktop.ini"]);

function extOfName(name) {
  return (name.split(".").pop() || "").toLowerCase();
}

function extOf(file) {
  return extOfName(file.name);
}

function formatBytes(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let value = Math.max(0, bytes);
  for (const unit of units) {
    if (value < 1024 || unit === units[units.length - 1]) return `${value.toFixed(2)} ${unit}`;
    value /= 1024;
  }
  return `${bytes} B`;
}

function imageMimeForExt(ext) {
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  return "image/webp";
}

// createImageBitmap only ever decodes the first frame of an animated image.
// Silently "recompressing" an animated GIF/WebP/PNG would delete every frame
// but the first, so we detect real animation by walking each format's actual
// container structure (not a naive byte scan, which false-positives inside
// compressed pixel data) and skip recompression when in doubt.
async function isAnimatedGif(blob) {
  try {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (bytes.length < 13 || String.fromCharCode(bytes[0], bytes[1], bytes[2]) !== "GIF") return true;
    let pos = 6;
    const flags = bytes[pos + 4];
    const hasGlobalColorTable = (flags & 0x80) !== 0;
    const globalColorTableSize = hasGlobalColorTable ? 3 * 2 ** ((flags & 0x07) + 1) : 0;
    pos += 7 + globalColorTableSize;
    let imageCount = 0;
    while (pos < bytes.length) {
      const marker = bytes[pos];
      if (marker === 0x3b) break;
      if (marker === 0x21) {
        pos += 2;
        while (pos < bytes.length && bytes[pos] !== 0x00) pos += bytes[pos] + 1;
        pos += 1;
        continue;
      }
      if (marker === 0x2c) {
        imageCount += 1;
        if (imageCount > 1) return true;
        const localFlags = bytes[pos + 9];
        const hasLocalColorTable = (localFlags & 0x80) !== 0;
        const localColorTableSize = hasLocalColorTable ? 3 * 2 ** ((localFlags & 0x07) + 1) : 0;
        pos += 10 + localColorTableSize;
        pos += 1;
        while (pos < bytes.length && bytes[pos] !== 0x00) pos += bytes[pos] + 1;
        pos += 1;
        continue;
      }
      return true;
    }
    return false;
  } catch {
    return true;
  }
}

async function isAnimatedWebp(blob) {
  try {
    const head = new Uint8Array(await blob.slice(0, 4096).arrayBuffer());
    if (head.length < 12) return true;
    if (String.fromCharCode(head[0], head[1], head[2], head[3]) !== "RIFF") return true;
    if (String.fromCharCode(head[8], head[9], head[10], head[11]) !== "WEBP") return true;
    let pos = 12;
    while (pos + 8 <= head.length) {
      const fourCC = String.fromCharCode(head[pos], head[pos + 1], head[pos + 2], head[pos + 3]);
      if (fourCC === "ANIM") return true;
      if (fourCC === "VP8 " || fourCC === "VP8L") return false;
      const size = head[pos + 4] | (head[pos + 5] << 8) | (head[pos + 6] << 16) | (head[pos + 7] << 24);
      pos += 8 + size + (size % 2);
    }
    return false;
  } catch {
    return true;
  }
}

async function isAnimatedPng(blob) {
  try {
    const head = new Uint8Array(await blob.slice(0, 8192).arrayBuffer());
    let pos = 8;
    while (pos + 8 <= head.length) {
      const length = (head[pos] << 24) | (head[pos + 1] << 16) | (head[pos + 2] << 8) | head[pos + 3];
      const type = String.fromCharCode(head[pos + 4], head[pos + 5], head[pos + 6], head[pos + 7]);
      if (type === "acTL") return true;
      if (type === "IDAT") return false;
      pos += 8 + length + 4;
    }
    return false;
  } catch {
    return true;
  }
}

async function isUnsafeToRecompress(ext, blob) {
  if (ext === "gif") return isAnimatedGif(blob);
  if (ext === "webp") return isAnimatedWebp(blob);
  if (ext === "png") return isAnimatedPng(blob);
  return false;
}

function outputAccepted(originalSize, outputSize, opts) {
  if (outputSize >= originalSize) return { ok: false, message: "원본보다 커져서 건너뜀" };
  const saved = originalSize - outputSize;
  const pct = originalSize ? (saved / originalSize) * 100 : 0;
  if (pct < opts.minSavingsPercent) {
    return { ok: false, message: `절감률 ${pct.toFixed(1)}%로 기준(${opts.minSavingsPercent}%) 미달` };
  }
  if (opts.targetSizeBytes > 0 && outputSize > opts.targetSizeBytes) {
    return { ok: false, message: `목표 용량(${formatBytes(opts.targetSizeBytes)}) 초과` };
  }
  return { ok: true, saved };
}

// Dimension reduction beats a lower quality knob on oversized photos, but must
// never upscale and never touch images already within the cap.
function computeResizedDimensions(width, height, maxDimension) {
  if (!maxDimension || maxDimension <= 0) return { width, height };
  const longestSide = Math.max(width, height);
  if (longestSide <= maxDimension) return { width, height };
  const scale = maxDimension / longestSide;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

// Returns { blob, width, height } — callers that embed raw dimensions
// alongside pixel data (PDF image XObjects) need the actual output size,
// not just the blob, to keep their dict in sync with what got drawn.
async function recompressImage(blob, mimeType, quality, maxDimension = 0) {
  const image = await createImageBitmap(blob);
  const { width, height } = computeResizedDimensions(image.width, image.height, maxDimension);
  const useOffscreen = typeof document === "undefined" && typeof OffscreenCanvas !== "undefined";
  let outBlob;
  if (useOffscreen) {
    const canvas = new OffscreenCanvas(width, height);
    const ctx = canvas.getContext("2d", { alpha: mimeType === "image/png" });
    ctx.drawImage(image, 0, 0, width, height);
    outBlob = await canvas.convertToBlob({ type: mimeType, quality });
  } else {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { alpha: mimeType === "image/png" });
    ctx.drawImage(image, 0, 0, width, height);
    outBlob = await new Promise((resolve) => canvas.toBlob(resolve, mimeType, quality));
  }
  return { blob: outBlob, width, height };
}

// Mirrors desktop core.py's quality_ladder(): the strength slider's chosen
// quality is a single predictable knob and stays that way when there's no
// target size. Once a target size is set, a single miss shouldn't be the
// end of it -- step down toward a floor so the target actually gets chased
// instead of the first attempt just giving up.
function qualityLadder(opts) {
  if (opts.lossBudget === "none") return [];
  const chosen = opts.quality;
  if (!opts.targetSizeBytes || opts.targetSizeBytes <= 0) return [chosen];
  const floor = 0.35;
  const steps = [chosen];
  for (let quality = chosen - 0.12; quality > floor; quality -= 0.12) {
    steps.push(Math.round(quality * 100) / 100);
  }
  if (steps[steps.length - 1] > floor) steps.push(floor);
  return steps;
}

// Mirrors desktop core.py's dimension_ladder(): a strength level's maxDimension
// is a single predictable cap and stays that way without a target size. Once a
// target size is set and quality alone can't reach it, step the cap down
// further instead of giving up -- same idea as the quality ladder, applied to
// dimension. Never escalates past the level's own cap (only tighter).
const DIMENSION_LADDER = [1600, 1200, 900, 700, 500, 350];

function dimensionLadder(opts) {
  const cap = opts.maxDimension || 0;
  if (!opts.targetSizeBytes || opts.targetSizeBytes <= 0 || opts.lossBudget === "none") {
    return [cap];
  }
  const rungs = cap > 0 ? DIMENSION_LADDER.filter((step) => step < cap) : DIMENSION_LADDER;
  return [cap, ...rungs];
}

// Tries each dimension cap, and within it each quality rung, keeping the
// smallest candidate seen and returning as soon as one fits
// opts.targetSizeBytes (or, with no target size, returning the first/only
// combination immediately -- unchanged behavior). Returns null if every
// combination fails or none shrinks the input at all.
async function recompressImageWithLadder(blob, opts, mimeType) {
  let best = null;
  for (const maxDimension of dimensionLadder(opts)) {
    for (const quality of qualityLadder(opts)) {
      let candidate;
      try {
        candidate = await recompressImage(blob, mimeType, quality, maxDimension);
      } catch {
        continue;
      }
      if (!candidate.blob || candidate.blob.size >= blob.size) continue;
      if (!best || candidate.blob.size < best.blob.size) best = candidate;
      if (!opts.targetSizeBytes || candidate.blob.size <= opts.targetSizeBytes) return candidate;
    }
  }
  return best;
}

async function optimizeImageFile(file, opts) {
  if (opts.lossBudget === "none") return { status: "skipped", message: "손실 없음 설정이라 원본 유지" };
  const ext = extOf(file);
  if (await isUnsafeToRecompress(ext, file)) {
    return { status: "skipped", message: "움직이는 이미지라 프레임 보존을 위해 원본 유지" };
  }
  const result = await recompressImageWithLadder(file, opts, "image/webp");
  if (!result || !result.blob) return { status: "skipped", message: "이미지 변환 실패" };
  const accepted = outputAccepted(file.size, result.blob.size, opts);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.webp");
  return { status: "optimized", blob: result.blob, outName, saved: accepted.saved };
}

function safeArchiveName(name) {
  const cleanName = name.replaceAll("\\", "/").replace(/^\/+/, "");
  if (!cleanName || cleanName.includes("../") || cleanName.startsWith("..")) {
    throw new Error(`안전하지 않은 경로: ${name}`);
  }
  return cleanName;
}

function canRecompressArchiveImages(fileExt, opts) {
  return opts.lossBudget !== "none" && imageOptimizableArchiveExts.has(fileExt);
}

// Plain zip/cbz entries are referenced by nothing but the reader's eyes, so
// they can be CONVERTED to WebP (extension renamed to match) -- the same
// trick comic-archive optimizers use, and a far bigger win than re-encoding
// a JPEG as a JPEG. DOCX/EPUB/Office are excluded: their internal XML
// manifests reference images by exact filename, so entries there keep their
// original format and name.
const RENAMEABLE_ARCHIVE_EXTS = new Set(["zip", "cbz"]);

async function maybeOptimizeArchiveEntry(fileExt, cleanName, data, opts) {
  const entryExt = extOfName(cleanName);
  if (!canRecompressArchiveImages(fileExt, opts) || !archiveImageExts.has(entryExt)) {
    return { blob: data, name: cleanName, changed: false };
  }
  if (await isUnsafeToRecompress(entryExt, data)) {
    return { blob: data, name: cleanName, changed: false, skipped: true };
  }
  const canRename = RENAMEABLE_ARCHIVE_EXTS.has(fileExt) && entryExt !== "webp";
  const mimeType = canRename ? "image/webp" : imageMimeForExt(entryExt);
  const result = await recompressImageWithLadder(data, opts, mimeType);
  if (!result || !result.blob) return { blob: data, name: cleanName, changed: false, skipped: true };
  const name = canRename ? cleanName.replace(/\.[^.]+$/, ".webp") : cleanName;
  return { blob: result.blob, name, changed: true };
}

// A plain ZIP that's nothing but images is functionally a comic/photo
// archive already -- mirrors desktop's is_image_only_zip().
function isImageOnlyZipEntries(files) {
  const names = Object.keys(files)
    .filter((name) => !files[name].dir)
    .filter((name) => !IGNORABLE_ZIP_ENTRY_NAMES.has(name.split("/").pop().toLowerCase()));
  if (!names.length) return false;
  return names.every((name) => archiveImageExts.has(extOfName(name)));
}

async function optimizeArchive(file, opts) {
  if (typeof JSZip === "undefined") throw new Error("압축 엔진을 불러오지 못했습니다.");
  const fileExt = extOf(file);
  const source = await JSZip.loadAsync(file);
  const output = new JSZip();
  let imageEntriesOptimized = 0;
  let imageEntriesSkipped = 0;
  for (const [name, entry] of Object.entries(source.files)) {
    if (entry.dir) continue;
    const cleanName = safeArchiveName(name);
    const data = await entry.async("blob");
    const entryResult = await maybeOptimizeArchiveEntry(fileExt, cleanName, data, opts);
    imageEntriesOptimized += entryResult.changed ? 1 : 0;
    imageEntriesSkipped += entryResult.skipped ? 1 : 0;
    // Image entries are already compressed (webp/jpg/png) -- deflating them
    // again wastes CPU on every entry and usually ADDS bytes. STORE them.
    const entryIsImage = archiveImageExts.has(extOfName(entryResult.name));
    const compression = (fileExt === "epub" && cleanName === "mimetype") || entryIsImage ? "STORE" : "DEFLATE";
    output.file(entryResult.name, entryResult.blob, { compression });
  }
  const blob = await output.generateAsync({
    type: "blob",
    compression: "DEFLATE",
    compressionOptions: { level: 9 },
    mimeType: file.type || "application/octet-stream",
  });
  const accepted = outputAccepted(file.size, blob.size, opts);
  if (!accepted.ok) {
    // Say what's inside so a 0% result diagnoses itself: a ZIP of mp4s
    // can't shrink, a ZIP of JPEGs that didn't shrink means they're
    // already heavily compressed.
    const counts = {};
    for (const [name, entry] of Object.entries(source.files)) {
      if (entry.dir) continue;
      const ext = extOfName(name) || "기타";
      counts[ext] = (counts[ext] || 0) + 1;
    }
    const topEntries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 3)
      .map(([ext, n]) => `${ext} ${n}개`).join(", ");
    const mostlyPrecompressed = Object.entries(counts)
      .filter(([ext]) => ALREADY_COMPRESSED_EXTS.has(ext))
      .reduce((sum, [, n]) => sum + n, 0) > Object.values(counts).reduce((a, b) => a + b, 0) / 2;
    const hint = mostlyPrecompressed
      ? " · 안의 파일들이 이미 압축된 형식(영상 등)이라 재압축으로는 줄지 않습니다."
      : opts.lossBudget === "high"
        ? " · 내용물이 이미 강하게 압축된 상태입니다."
        : " · 강력/최대 레벨이면 안의 이미지를 더 줄일 수 있습니다.";
    return { status: "skipped", message: `${accepted.message} (내용: ${topEntries})${hint}` };
  }
  const outName = fileExt === "zip" && isImageOnlyZipEntries(source.files)
    ? file.name.replace(/\.[^.]+$/, ".ozero.cbz")
    : file.name.replace(/(\.[^.]+)$/, ".ozero$1");
  const detailParts = imageEntriesOptimized ? [`이미지 ${imageEntriesOptimized}개 재압축`] : ["컨테이너만 재압축"];
  if (imageEntriesSkipped) detailParts.push(`이미지 ${imageEntriesSkipped}개는 원본 유지`);
  return { status: "optimized", blob, outName, saved: accepted.saved, message: detailParts.join(" / ") };
}

// Formats that are already internally compressed -- deflating them again is
// wasted CPU that always ends in "skipped". Named so the skip message can say
// WHY instead of leaving the user to ask.
const ALREADY_COMPRESSED_EXTS = new Set([
  "mp4", "mkv", "avi", "webm", "mov", "m4v", "wmv", "flv",
  "mp3", "aac", "m4a", "ogg", "opus", "flac",
  "7z", "rar", "gz", "bz2", "xz", "zst",
  "apk", "ipa", "dmg", "iso",
]);

async function optimizeGenericFile(file, opts) {
  const ext = extOf(file);
  if (ALREADY_COMPRESSED_EXTS.has(ext)) {
    const kind = /^(mp4|mkv|avi|webm|mov|m4v|wmv|flv)$/.test(ext) ? "영상"
      : /^(mp3|aac|m4a|ogg|opus|flac)$/.test(ext) ? "오디오"
      : "이미 압축된 형식";
    return {
      status: "skipped",
      message: `${kind}(${ext})은 자체 코덱으로 이미 압축되어 있어 재압축 효과가 없습니다. 영상/오디오는 전용 인코더(예: HandBrake)가 필요합니다.`,
    };
  }
  if (typeof JSZip === "undefined") throw new Error("압축 엔진을 불러오지 못했습니다.");
  const output = new JSZip();
  output.file(safeArchiveName(file.name), file);
  const blob = await output.generateAsync({
    type: "blob",
    compression: "DEFLATE",
    compressionOptions: { level: 9 },
    mimeType: "application/zip",
  });
  const accepted = outputAccepted(file.size, blob.size, opts);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.zip");
  return { status: "optimized", blob, outName, saved: accepted.saved, message: "일반 ZIP 압축" };
}

function pdfFilterIsDct(filter, filterDct) {
  if (filter === filterDct) return true;
  // /Filter [/DCTDecode] -- array spelling of the same thing. Common in
  // real-world PDFs and previously skipped for no good reason.
  return filter instanceof PDFLib.PDFArray && filter.size() === 1 && filter.lookup(0) === filterDct;
}

function pdfColorSpaceIsRecompressable(colorSpace) {
  const { PDFName, PDFArray } = PDFLib;
  if (colorSpace instanceof PDFName) {
    return RECOMPRESSABLE_PDF_COLORSPACES.has(colorSpace.asString().slice(1));
  }
  // [/ICCBased <stream>] wrapping plain RGB/Gray is how most exporters spell
  // colorspaces. The browser's JPEG decode handles the profile, and we
  // re-encode to the same channel count, so these are safe to recompress.
  if (colorSpace instanceof PDFArray && colorSpace.size() >= 2 && colorSpace.lookup(0) === PDFName.of("ICCBased")) {
    const iccStream = colorSpace.lookup(1);
    const iccDict = iccStream && iccStream.dict;
    if (!iccDict) return false;
    const alternate = iccDict.lookup(PDFName.of("Alternate"));
    if (alternate instanceof PDFName) {
      return RECOMPRESSABLE_PDF_COLORSPACES.has(alternate.asString().slice(1));
    }
    const components = iccDict.lookup(PDFName.of("N"));
    if (components && typeof components.asNumber === "function") {
      return components.asNumber() === 1 || components.asNumber() === 3;
    }
  }
  return false;
}

async function recompressPdfImages(pdfDoc, opts) {
  if (opts.lossBudget === "none") return 0;
  const { PDFName, PDFRawStream, PDFNumber } = PDFLib;
  const subtypeImage = PDFName.of("Image");
  const filterDct = PDFName.of("DCTDecode");
  let recompressedCount = 0;
  for (const [ref, obj] of pdfDoc.context.enumerateIndirectObjects()) {
    if (!(obj instanceof PDFRawStream)) continue;
    const dict = obj.dict;
    if (dict.lookup(PDFName.of("Subtype")) !== subtypeImage) continue;
    if (!pdfFilterIsDct(dict.lookup(PDFName.of("Filter")), filterDct)) continue;
    if (dict.lookup(PDFName.of("Decode"))) continue;
    if (!pdfColorSpaceIsRecompressable(dict.lookup(PDFName.of("ColorSpace")))) continue;
    const sourceBytes = obj.getContents();
    // There's no meaningful per-image target size inside a PDF, so each
    // embedded image chases the whole file's target -- conservative, but if
    // every image fits under it the rewritten PDF almost certainly will too.
    const recompressed = await recompressImageWithLadder(
      new Blob([sourceBytes], { type: "image/jpeg" }),
      opts,
      "image/jpeg"
    );
    if (!recompressed || !recompressed.blob) continue;
    const newBytes = new Uint8Array(await recompressed.blob.arrayBuffer());
    dict.set(PDFName.of("Length"), PDFNumber.of(newBytes.length));
    // Must match the resized pixel data — a stale /Width or /Height here
    // makes viewers decode the JPEG against the wrong sample count.
    dict.set(PDFName.of("Width"), PDFNumber.of(recompressed.width));
    dict.set(PDFName.of("Height"), PDFNumber.of(recompressed.height));
    // Canvas re-encode always emits an 8-bit 3-channel sRGB JPEG, whatever
    // the source was (gray, ICC-wrapped, 16-bit). Normalize the dict to the
    // data we actually wrote, and drop params that described the old stream.
    dict.set(PDFName.of("ColorSpace"), PDFName.of("DeviceRGB"));
    dict.set(PDFName.of("BitsPerComponent"), PDFNumber.of(8));
    dict.set(PDFName.of("Filter"), filterDct);
    dict.delete(PDFName.of("DecodeParms"));
    pdfDoc.context.assign(ref, PDFRawStream.of(dict, newBytes));
    recompressedCount += 1;
  }
  return recompressedCount;
}

function pdfjsReady() {
  if (typeof pdfjsLib === "undefined" || !pdfjsLib.getDocument) return false;
  if (!pdfjsLib.GlobalWorkerOptions.workerSrc && !pdfjsLib.GlobalWorkerOptions.workerPort) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = "./vendor/pdfjs/pdf.worker.min.js";
  }
  return true;
}

// pdf.js's default canvas factory calls document.createElement for the
// temporary canvases some render ops need (patterns, masks) -- in a worker
// there is no document, so hand it OffscreenCanvas instead.
class OffscreenCanvasFactory {
  create(width, height) {
    const canvas = new OffscreenCanvas(Math.max(1, width), Math.max(1, height));
    return { canvas, context: canvas.getContext("2d") };
  }
  reset(pair, width, height) {
    pair.canvas.width = Math.max(1, width);
    pair.canvas.height = Math.max(1, height);
  }
  destroy(pair) {
    pair.canvas.width = 0;
    pair.canvas.height = 0;
    pair.canvas = null;
    pair.context = null;
  }
}

// Render every page with pdf.js and rebuild the file as JPEG page images.
// This is the only browser-side lever that reaches losslessly-stored
// (FlateDecode) scans, CCITT faxes, and over-DPI rasters -- everything the
// stream-replacement pass above can't touch. The trade is real: text stops
// being selectable, so callers gate this on the "high" loss budget and only
// keep the result when it's actually smaller.
const MAX_RASTERIZE_PAGES = 400;

async function rasterizePdfDocument(sourceBytes, opts) {
  if (!pdfjsReady()) return null;
  const chasing = opts.targetSizeBytes && opts.targetSizeBytes > 0;
  // 최대 압축 (quality <= 0.5) starts at a lower page DPI -- the whole point
  // of that level is trading visible quality for size.
  const baseDpi = (opts.quality || 0.7) <= 0.5 ? 110 : 150;
  const jpegQuality = Math.min(0.9, Math.max(0.35, opts.quality || 0.7));
  const inWorker = typeof document === "undefined";
  const canvasFactory = inWorker ? new OffscreenCanvasFactory() : undefined;
  // pdf.js transfers the buffer it's handed to its worker -- pass a copy so
  // the caller's bytes stay usable. canvasFactory is passed both here (v4
  // API location) and to page.render (v3 location) so either build works.
  const doc = await pdfjsLib.getDocument({ data: sourceBytes.slice(0), isEvalSupported: false, canvasFactory }).promise;
  try {
    // Rendering every page of a huge PDF can exhaust tab memory -- refuse
    // rather than crash. The structure-preserving pass still applies.
    if (doc.numPages > MAX_RASTERIZE_PAGES) {
      console.warn(`PDF 페이지 ${doc.numPages}개 > ${MAX_RASTERIZE_PAGES} -- 재구성 생략 (메모리 보호)`);
      return null;
    }
    // JPEG size scales roughly with pixel count (dpi²): after the first
    // render, jump straight to the DPI predicted to hit the target instead
    // of walking every rung -- 2 full-document renders instead of up to 4.
    let dpis = [baseDpi];
    let best = null;
    for (let attempt = 0; attempt < dpis.length; attempt++) {
      const dpi = dpis[attempt];
      const out = await PDFLib.PDFDocument.create();
      for (let pageNumber = 1; pageNumber <= doc.numPages; pageNumber++) {
        const page = await doc.getPage(pageNumber);
        const baseViewport = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: dpi / 72 });
        const width = Math.max(1, Math.floor(viewport.width));
        const height = Math.max(1, Math.floor(viewport.height));
        const useOffscreen = typeof document === "undefined" && typeof OffscreenCanvas !== "undefined";
        const canvas = useOffscreen ? new OffscreenCanvas(width, height) : document.createElement("canvas");
        if (!useOffscreen) {
          canvas.width = width;
          canvas.height = height;
        }
        const ctx = canvas.getContext("2d", { alpha: false });
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, width, height);
        await page.render({ canvasContext: ctx, viewport, canvasFactory }).promise;
        const blob = useOffscreen
          ? await canvas.convertToBlob({ type: "image/jpeg", quality: jpegQuality })
          : await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", jpegQuality));
        const jpg = await out.embedJpg(new Uint8Array(await blob.arrayBuffer()));
        const outPage = out.addPage([baseViewport.width, baseViewport.height]);
        outPage.drawImage(jpg, { x: 0, y: 0, width: baseViewport.width, height: baseViewport.height });
      }
      const bytes = await out.save({ useObjectStreams: true, addDefaultPage: false });
      if (!best || bytes.length < best.bytes.length) best = { bytes, dpi, pageCount: doc.numPages };
      if (!chasing || bytes.length <= opts.targetSizeBytes) break;
      if (attempt === 0) {
        const predicted = Math.round(dpi * Math.sqrt((opts.targetSizeBytes / bytes.length) * 0.85));
        const nextDpi = Math.max(60, Math.min(predicted, dpi - 10));
        if (nextDpi < dpi) dpis = [dpi, nextDpi];
      }
    }
    return best;
  } finally {
    doc.destroy();
  }
}

async function optimizePdfFile(file, opts) {
  if (typeof PDFLib === "undefined" || !PDFLib.PDFDocument) throw new Error("PDF 엔진을 불러오지 못했습니다.");
  const sourceBytes = await file.arrayBuffer();
  let pdfDoc;
  try {
    pdfDoc = await PDFLib.PDFDocument.load(sourceBytes, {
      ignoreEncryption: false,
      updateMetadata: false,
    });
  } catch {
    throw new Error("PDF를 열 수 없습니다 (암호화되었거나 손상됨).");
  }
  const pageCount = pdfDoc.getPageCount();
  if (pageCount <= 0) return { status: "skipped", message: "페이지가 없는 PDF" };
  const recompressedImages = await recompressPdfImages(pdfDoc, opts);
  const outputBytes = await pdfDoc.save({
    useObjectStreams: true,
    addDefaultPage: false,
    objectsPerTick: 100,
    updateFieldAppearances: false,
  });
  let blob = new Blob([outputBytes], { type: "application/pdf" });
  let detail = recompressedImages ? `${pageCount}페이지 / 이미지 ${recompressedImages}개 재압축` : `${pageCount}페이지`;
  let rasterState = "below-level";
  // 강력/최대 (high): rasterize whenever it wins. 기본/강함 (medium): users
  // shouldn't need to find the advanced panel to shrink a scan PDF -- try it
  // automatically too, but only adopt a DRAMATIC win (>=60% smaller), since
  // losing text selection at the default level needs real justification.
  const rasterBudget = opts.lossBudget === "high" ? "high" : opts.lossBudget === "medium" ? "medium" : null;
  if (rasterBudget) {
    try {
      const raster = await rasterizePdfDocument(sourceBytes, opts);
      const winsEnough = raster && raster.pageCount === pageCount
        && (rasterBudget === "high" ? raster.bytes.length < blob.size : raster.bytes.length < blob.size * 0.4);
      if (winsEnough) {
        blob = new Blob([raster.bytes], { type: "application/pdf" });
        detail = `${pageCount}페이지 / 스캔형 재구성 ${raster.dpi}DPI (텍스트 선택 불가)`;
        rasterState = "used";
      } else if (raster && raster.bytes.length < blob.size) {
        rasterState = "modest";
      } else {
        rasterState = raster ? "larger" : "unavailable";
      }
    } catch (error) {
      // rasterization is opportunistic -- any failure falls back to the
      // structure-preserving result computed above. Logged because a silent
      // fallback here once hid a worker-only pdf.js loading failure.
      console.warn("PDF 스캔형 재구성 실패, 구조 보존 결과 사용:", error);
      rasterState = `실패: ${String(error && error.message || error).slice(0, 120)}`;
    }
  }
  const accepted = outputAccepted(file.size, blob.size, opts);
  if (!accepted.ok) {
    // Say WHY and what to try next -- "기준 미달" alone sends users off to
    // ask a human what it means.
    const hint = rasterState === "below-level"
      ? " · 강력/최대 레벨은 페이지를 이미지로 재구성해 스캔 PDF를 크게 줄일 수 있습니다."
      : rasterState === "modest"
        ? " · 페이지 재구성으로 조금 더 줄일 수 있습니다 — 강력/최대 레벨에서는 그 결과를 그대로 채택합니다."
        : rasterState === "larger"
          ? " · 페이지를 이미지로 재구성해봤지만 오히려 커집니다(텍스트 위주 PDF). 이 파일은 이미 작게 저장되어 있습니다."
          : rasterState === "unavailable"
            ? " · 페이지 재구성 엔진을 사용할 수 없었습니다. 새로고침 후 다시 시도해보세요."
            : ` · 페이지 재구성 중 오류가 났습니다 (${rasterState}). 데스크탑 앱이 더 안정적입니다.`;
    return { status: "skipped", message: `${accepted.message} (${detail})${hint}` };
  }
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.pdf");
  return { status: "optimized", blob, outName, saved: accepted.saved, message: `PDF 재압축 / ${detail}` };
}

async function optimizeFile(file, opts) {
  const ext = extOf(file);
  if (imageExts.has(ext)) return optimizeImageFile(file, opts);
  if (archiveExts.has(ext)) return optimizeArchive(file, opts);
  if (pdfExts.has(ext)) return optimizePdfFile(file, opts);
  return optimizeGenericFile(file, opts);
}
