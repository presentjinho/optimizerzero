// Dedicated module worker (loaded with `{ type: "module" }`) for AVIF/JXL
// encoding. jsquash's encoders are ES modules (import.meta.url, top-level
// export) which classic workers can't reliably dynamic-import across
// browsers, so this is kept separate from worker.js's classic/importScripts
// world instead of bolted onto it.
//
// Scope: standalone image files only. Archives (zip/cbz/...) and PDFs stay
// on the WebP path in worker.js -- JSZip and pdf-lib are classic UMD builds
// that a module worker can't importScripts(), and PDF's spec only allows
// DCTDecode/JPXDecode image streams anyway (no AVIF/JXL inside a PDF).
//
// Resize math, animation detection, and the accept/reject check below are
// intentionally duplicated from optimize-core.js rather than shared, because
// optimize-core.js is a classic script (no `export`) loaded via <script src>
// and importScripts() elsewhere -- a module worker can only use `import`, so
// it can't consume that file as-is. Keep both in sync if the algorithms
// change.

function computeResizedDimensions(width, height, maxDimension) {
  if (!maxDimension || maxDimension <= 0) return { width, height };
  const longestSide = Math.max(width, height);
  if (longestSide <= maxDimension) return { width, height };
  const scale = maxDimension / longestSide;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
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

function formatBytes(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let value = Math.max(0, bytes);
  for (const unit of units) {
    if (value < 1024 || unit === units[units.length - 1]) return `${value.toFixed(2)} ${unit}`;
    value /= 1024;
  }
  return `${bytes} B`;
}

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

function extOfName(name) {
  return (name.split(".").pop() || "").toLowerCase();
}

async function encodeWith(codec, imageData, quality) {
  if (codec === "avif") {
    const { default: encode } = await import("./vendor/jsquash-avif/encode.js");
    const buffer = await encode(imageData, { quality });
    return { buffer, mime: "image/avif", ext: ".avif" };
  }
  const { default: encode } = await import("./vendor/jsquash-jxl/encode.js");
  const buffer = await encode(imageData, { quality, effort: 9 });
  return { buffer, mime: "image/jxl", ext: ".jxl" };
}

// Mirrors optimize-core.js's qualityLadder()/dimensionLadder(): without a
// target size, encode once at the strength level's own quality/cap. Once a
// target size is set and the first attempt misses, step both knobs down
// until it's hit or the rungs run out, instead of giving up on one try.
// jsquash quality options are on a 0-100 scale; OZ's internal opts.quality is 0-1.
function qualityLadder(opts) {
  const chosen = Math.round(opts.quality * 100);
  if (!opts.targetSizeBytes || opts.targetSizeBytes <= 0) return [chosen];
  const floor = 35;
  const steps = [chosen];
  for (let quality = chosen - 12; quality > floor; quality -= 12) steps.push(quality);
  if (steps[steps.length - 1] > floor) steps.push(floor);
  return steps;
}

const DIMENSION_LADDER = [1600, 1200, 900, 700, 500, 350];

function dimensionLadder(opts) {
  const cap = opts.maxDimension || 0;
  if (!opts.targetSizeBytes || opts.targetSizeBytes <= 0) return [cap];
  const rungs = cap > 0 ? DIMENSION_LADDER.filter((step) => step < cap) : DIMENSION_LADDER;
  return [cap, ...rungs];
}

async function encodeCandidate(bitmap, opts, maxDimension, quality) {
  const { width, height } = computeResizedDimensions(bitmap.width, bitmap.height, maxDimension);
  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, width, height);
  const imageData = ctx.getImageData(0, 0, width, height);
  const { buffer, mime, ext } = await encodeWith(opts.codec, imageData, quality);
  return { blob: new Blob([buffer], { type: mime }), ext };
}

async function optimizeImageFile(file, opts) {
  const ext = extOfName(file.name);
  if (await isUnsafeToRecompress(ext, file)) {
    return { status: "skipped", message: "움직이는 이미지라 프레임 보존을 위해 원본 유지" };
  }

  const bitmap = await createImageBitmap(file);
  let best = null;
  ladders: for (const maxDimension of dimensionLadder(opts)) {
    for (const quality of qualityLadder(opts)) {
      let candidate;
      try {
        candidate = await encodeCandidate(bitmap, opts, maxDimension, quality);
      } catch {
        continue;
      }
      if (!candidate.blob || candidate.blob.size >= file.size) continue;
      if (!best || candidate.blob.size < best.blob.size) best = candidate;
      if (!opts.targetSizeBytes || candidate.blob.size <= opts.targetSizeBytes) {
        best = candidate;
        break ladders;
      }
    }
  }
  if (!best) return { status: "skipped", message: "이미지 변환 실패" };

  const accepted = outputAccepted(file.size, best.blob.size, opts);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, `.ozero${best.ext}`);
  return { status: "optimized", blob: best.blob, outName, saved: accepted.saved };
}

self.onmessage = async (event) => {
  const { file, opts } = event.data;
  try {
    const result = await optimizeImageFile(file, opts);
    self.postMessage({ ok: true, result });
  } catch (error) {
    self.postMessage({ ok: false, error: error.message || String(error) });
  }
};
