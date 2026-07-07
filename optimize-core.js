// Pure compression logic shared by the main thread (app.js) and the worker
// pool (worker.js). No DOM assumptions except an optional `document`-based
// canvas fallback — everything else works identically in a Worker.
const archiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"]);
const imageExts = new Set(["png", "jpg", "jpeg", "webp", "bmp", "gif"]);
const pdfExts = new Set(["pdf"]);
const archiveImageExts = new Set(["jpg", "jpeg", "webp", "bmp", "gif", "png"]);
const imageOptimizableArchiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"]);
const RECOMPRESSABLE_PDF_COLORSPACES = new Set(["DeviceRGB", "DeviceGray"]);

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

async function optimizeImageFile(file, opts) {
  if (opts.lossBudget === "none") return { status: "skipped", message: "손실 없음 설정이라 원본 유지" };
  const ext = extOf(file);
  if (await isUnsafeToRecompress(ext, file)) {
    return { status: "skipped", message: "움직이는 이미지라 프레임 보존을 위해 원본 유지" };
  }
  let blob;
  try {
    ({ blob } = await recompressImage(file, "image/webp", opts.quality, opts.maxDimension));
  } catch {
    return { status: "skipped", message: "이미지 변환 실패" };
  }
  if (!blob) return { status: "skipped", message: "이미지 변환 실패" };
  const accepted = outputAccepted(file.size, blob.size, opts);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.webp");
  return { status: "optimized", blob, outName, saved: accepted.saved };
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

async function maybeOptimizeArchiveEntry(fileExt, cleanName, data, opts) {
  const entryExt = extOfName(cleanName);
  if (!canRecompressArchiveImages(fileExt, opts) || !archiveImageExts.has(entryExt)) {
    return { blob: data, changed: false };
  }
  if (await isUnsafeToRecompress(entryExt, data)) {
    return { blob: data, changed: false, skipped: true };
  }
  const mimeType = imageMimeForExt(entryExt);
  let optimized;
  try {
    ({ blob: optimized } = await recompressImage(data, mimeType, opts.quality, opts.maxDimension));
  } catch {
    return { blob: data, changed: false, skipped: true };
  }
  if (!optimized || optimized.size >= data.size) return { blob: data, changed: false };
  return { blob: optimized, changed: true };
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
    const compression = fileExt === "epub" && cleanName === "mimetype" ? "STORE" : "DEFLATE";
    output.file(cleanName, entryResult.blob, { compression });
  }
  const blob = await output.generateAsync({
    type: "blob",
    compression: "DEFLATE",
    compressionOptions: { level: 9 },
    mimeType: file.type || "application/octet-stream",
  });
  const accepted = outputAccepted(file.size, blob.size, opts);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)$/, ".ozero$1");
  const detailParts = imageEntriesOptimized ? [`이미지 ${imageEntriesOptimized}개 재압축`] : ["컨테이너만 재압축"];
  if (imageEntriesSkipped) detailParts.push(`이미지 ${imageEntriesSkipped}개는 원본 유지`);
  return { status: "optimized", blob, outName, saved: accepted.saved, message: detailParts.join(" / ") };
}

async function optimizeGenericFile(file, opts) {
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
    if (dict.lookup(PDFName.of("Filter")) !== filterDct) continue;
    if (dict.lookup(PDFName.of("Decode"))) continue;
    const colorSpace = dict.lookup(PDFName.of("ColorSpace"));
    if (!(colorSpace instanceof PDFName) || !RECOMPRESSABLE_PDF_COLORSPACES.has(colorSpace.asString().slice(1))) continue;
    const sourceBytes = obj.getContents();
    let recompressed;
    try {
      recompressed = await recompressImage(
        new Blob([sourceBytes], { type: "image/jpeg" }),
        "image/jpeg",
        opts.quality,
        opts.maxDimension
      );
    } catch {
      continue;
    }
    if (!recompressed.blob || recompressed.blob.size >= sourceBytes.byteLength) continue;
    const newBytes = new Uint8Array(await recompressed.blob.arrayBuffer());
    dict.set(PDFName.of("Length"), PDFNumber.of(newBytes.length));
    // Must match the resized pixel data — a stale /Width or /Height here
    // makes viewers decode the JPEG against the wrong sample count.
    dict.set(PDFName.of("Width"), PDFNumber.of(recompressed.width));
    dict.set(PDFName.of("Height"), PDFNumber.of(recompressed.height));
    pdfDoc.context.assign(ref, PDFRawStream.of(dict, newBytes));
    recompressedCount += 1;
  }
  return recompressedCount;
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
  const blob = new Blob([outputBytes], { type: "application/pdf" });
  const accepted = outputAccepted(file.size, blob.size, opts);
  const detail = recompressedImages ? `${pageCount}페이지 / 이미지 ${recompressedImages}개 재압축` : `${pageCount}페이지`;
  if (!accepted.ok) {
    return { status: "skipped", message: `${accepted.message} (${detail})` };
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
