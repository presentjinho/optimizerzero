// UI state and rendering only — the actual compression logic lives in
// optimize-core.js (shared with worker.js) so it can run on either the main
// thread or in a worker pool without duplication.
// Kept in lockstep with service-worker.js CACHE_NAME and the ?vNN worker
// URL busters by a regression test. Shown in the status pill so "which
// version are you actually running" stops being a support question.
const APP_VERSION = "v25";
const state = { files: [], rejected: [], results: [], running: false };
const el = {
  dropZone: document.querySelector("#dropZone"),
  fileInput: document.querySelector("#fileInput"),
  folderInput: document.querySelector("#folderInput"),
  folderButton: document.querySelector("#folderButton"),
  fileList: document.querySelector("#fileList"),
  emptyState: document.querySelector("#emptyState"),
  totals: document.querySelector("#totals"),
  appStatus: document.querySelector("#appStatus"),
  strength: document.querySelector("#strength"),
  strengthLabel: document.querySelector("#strengthLabel"),
  strengthTicks: Array.from(document.querySelectorAll(".strength-ticks span")),
  targetSize: document.querySelector("#targetSize"),
  minSavings: document.querySelector("#minSavings"),
  limit: document.querySelector("#limit"),
  codec: document.querySelector("#codec"),
  codecHint: document.querySelector("#codecHint"),
  concurrency: document.querySelector("#concurrency"),
  concurrencyHint: document.querySelector("#concurrencyHint"),
  etaText: document.querySelector("#etaText"),
  runButton: document.querySelector("#runButton"),
  clearButton: document.querySelector("#clearButton"),
  reportButton: document.querySelector("#reportButton"),
  bundleButton: document.querySelector("#bundleButton"),
  meterFill: document.querySelector("#meterFill"),
  rowTemplate: document.querySelector("#fileRowTemplate"),
  previewModal: document.querySelector("#previewModal"),
  previewTitle: document.querySelector("#previewTitle"),
  previewClose: document.querySelector("#previewClose"),
  previewSlider: document.querySelector("#previewSlider"),
  previewBefore: document.querySelector("#previewBefore"),
  previewAfter: document.querySelector("#previewAfter"),
  previewBeforeWrap: document.querySelector("#previewBeforeWrap"),
  previewHandle: document.querySelector("#previewHandle"),
};

// 7-point drag scale from barely-touched to as-small-as-possible. Index 0 is
// level 1 (나노 압축), index 6 is level 7 (최대 압축); el.strength.value is 1-7.
// The curve is deliberately wide: 나노 stays visually indistinguishable from
// the original, 최대 trades visible quality for the smallest usable output.
const STRENGTH_LEVELS = [
  { label: "나노 압축", profile: "safe", lossBudget: "low", quality: 97, targetSize: 0, minSavings: 0, limit: 150, maxDimension: 0, message: "나노 압축: 화질 손실이 거의 안 보이는 선에서 최소한으로 압축." },
  { label: "살짝 압축", profile: "safe", lossBudget: "low", quality: 94, targetSize: 0, minSavings: 0, limit: 150, maxDimension: 0, message: "살짝 압축: 화질 손실 거의 없이 아주 조금만 줄임." },
  { label: "가벼운 압축", profile: "balanced", lossBudget: "low", quality: 90, targetSize: 0, minSavings: 1, limit: 100, maxDimension: 0, message: "가벼운 압축: 화질 우선, 절감은 보너스." },
  { label: "기본 압축", profile: "balanced", lossBudget: "medium", quality: 85, targetSize: 0, minSavings: 1, limit: 150, maxDimension: 0, message: "기본 압축: 화질과 용량의 균형 (추천)." },
  { label: "강한 압축", profile: "balanced", lossBudget: "medium", quality: 75, targetSize: 25, minSavings: 1, limit: 150, maxDimension: 2800, message: "강한 압축: 용량을 더 줄이고 화질은 약간 양보. 과도하게 큰 이미지는 2800px로 축소." },
  { label: "강력 압축", profile: "strong", lossBudget: "high", quality: 62, targetSize: 10, minSavings: 3, limit: 150, maxDimension: 2000, message: "강력 압축: 용량 우선, 결과 확인 후 사용. 큰 이미지는 2000px로 축소." },
  { label: "최대 압축", profile: "strong", lossBudget: "high", quality: 45, targetSize: 5, minSavings: 3, limit: 150, maxDimension: 1280, message: "최대 압축: 용량 최우선. 화질을 크게 양보하고 큰 이미지는 1280px로 축소. 결과 꼭 확인." },
];

function currentLevel() {
  const index = Math.min(STRENGTH_LEVELS.length, Math.max(1, Number(el.strength.value))) - 1;
  return STRENGTH_LEVELS[index];
}

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

// Queue grouping + result-ZIP folder names. Fixed display order.
const FILE_CATEGORIES = ["이미지", "PDF", "압축·문서", "기타"];
function fileCategory(file) {
  const ext = extOf(file);
  if (imageExts.has(ext)) return "이미지";
  if (pdfExts.has(ext)) return "PDF";
  if (archiveExts.has(ext)) return "압축·문서";
  return "기타";
}

function supported(file) {
  const ext = extOf(file);
  return archiveExts.has(ext) || imageExts.has(ext) || (pdfExts.has(ext) && Boolean(window.JSZip)) || Boolean(window.JSZip);
}

function setFiles(files) {
  const maxBytes = Number(el.limit.value) * 1024 * 1024;
  const incoming = [];
  state.rejected = [];
  for (const file of files) {
    if (!supported(file)) {
      state.rejected.push({ name: file.name, reason: "압축 엔진을 사용할 수 없음" });
    } else if (file.size > maxBytes) {
      state.rejected.push({ name: file.name, reason: `최대 ${el.limit.value}MB 초과` });
    } else {
      incoming.push(file);
    }
  }
  const known = new Set(state.files.map(fileKey));
  for (const file of incoming) {
    const key = fileKey(file);
    if (!known.has(key)) state.files.push(file);
  }
  render();
}

function removeFile(key) {
  state.files = state.files.filter((file) => fileKey(file) !== key);
  state.results = state.results.filter((result) => result.key !== key);
  render();
}

function resultForKey(key) {
  return state.results.find((result) => result.key === key);
}

function percentSaved(originalSize, outputSize) {
  if (!originalSize) return 0;
  return Math.max(0, ((originalSize - outputSize) / originalSize) * 100);
}

function resultLabel(result) {
  if (result.status === "optimized") {
    const pct = percentSaved(result.originalSize, result.outputSize);
    return `${pct.toFixed(0)}% 절감 (${formatBytes(result.savedBytes)})`;
  }
  return result.message || result.status;
}

function resultClass(result) {
  if (result.status === "optimized") return "done";
  if (result.status === "error") return "error";
  return "";
}

// Object URLs are created once per result (in recordResult/recordError) and
// tracked here so they can be revoked together -- render() rebuilds every
// row from scratch on each add/remove, and re-creating a fresh URL each time
// would leak one per row per re-render for as long as the tab stays open.
const activeBlobUrls = new Set();

function revokeTrackedBlobUrls() {
  for (const url of activeBlobUrls) URL.revokeObjectURL(url);
  activeBlobUrls.clear();
}

function configureDownloadButton(button, url, name) {
  button.hidden = false;
  button.onclick = () => {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
  };
}

function applyResultToRow(row, result, file) {
  const statusEl = row.querySelector(".file-status");
  statusEl.textContent = resultLabel(result);
  statusEl.className = `file-status ${resultClass(result)}`;
  const barWrap = row.querySelector(".file-bar");
  const barFill = row.querySelector(".file-bar-fill");
  if (result.status === "optimized") {
    barWrap.hidden = false;
    barFill.style.width = `${percentSaved(result.originalSize, result.outputSize).toFixed(0)}%`;
  } else {
    barWrap.hidden = true;
  }
  if (result.blobUrl) configureDownloadButton(row.querySelector(".download-button"), result.blobUrl, result.outName || result.name);
  const previewButton = row.querySelector(".preview-button");
  if (previewButton) {
    const canPreview = file && result.status === "optimized" && result.blobUrl && imageExts.has(extOf(file));
    previewButton.hidden = !canPreview;
    if (canPreview) previewButton.onclick = () => openPreview(file, result);
  }
}

function render() {
  el.fileList.innerHTML = "";
  el.emptyState.hidden = state.files.length > 0;
  const totalSize = state.files.reduce((sum, file) => sum + file.size, 0);
  const rejected = state.rejected.length ? ` / 제외 ${state.rejected.length}` : "";
  el.totals.textContent = `${state.files.length}개 파일 / ${formatBytes(totalSize)}${rejected}`;
  const groups = new Map(FILE_CATEGORIES.map((c) => [c, []]));
  for (const file of state.files) groups.get(fileCategory(file)).push(file);
  const usedCategories = FILE_CATEGORIES.filter((c) => groups.get(c).length);
  const orderedFiles = usedCategories.flatMap((c) => groups.get(c));
  let lastCategory = null;
  for (const file of orderedFiles) {
    // group headers only earn their space when there's actual variety
    const category = fileCategory(file);
    if (usedCategories.length > 1 && category !== lastCategory) {
      lastCategory = category;
      const groupFiles = groups.get(category);
      const groupSize = groupFiles.reduce((sum, f) => sum + f.size, 0);
      const header = document.createElement("div");
      header.className = "file-group-header";
      header.textContent = `${category} · ${groupFiles.length}개 · ${formatBytes(groupSize)}`;
      el.fileList.appendChild(header);
    }
    const row = el.rowTemplate.content.firstElementChild.cloneNode(true);
    const key = fileKey(file);
    row.dataset.key = key;
    row.querySelector(".file-name").textContent = file.name;
    row.querySelector(".file-meta").textContent = `${extOf(file).toUpperCase()} / ${formatBytes(file.size)}`;
    row.querySelector(".file-status").textContent = "대기중";
    row.querySelector(".file-bar").hidden = true;
    row.querySelector(".remove-button").addEventListener("click", () => removeFile(key));
    el.fileList.append(row);
    const result = resultForKey(key);
    if (result) applyResultToRow(row, result, file);
  }
  for (const item of state.rejected) {
    const row = el.rowTemplate.content.firstElementChild.cloneNode(true);
    row.querySelector(".file-name").textContent = item.name;
    row.querySelector(".file-meta").textContent = "대기열 제외";
    row.querySelector(".file-status").textContent = item.reason;
    row.querySelector(".file-status").className = "file-status error";
    row.querySelector(".file-bar").hidden = true;
    row.querySelector(".remove-button").hidden = true;
    el.fileList.append(row);
  }
}

function applyStrength() {
  const level = currentLevel();
  el.targetSize.value = String(level.targetSize);
  el.minSavings.value = String(level.minSavings);
  el.limit.value = String(level.limit);
  el.strengthLabel.textContent = level.label;
  el.strengthTicks.forEach((tick, index) => {
    tick.classList.toggle("active", index === Number(el.strength.value) - 1);
  });
  document.querySelector("#recommendation").textContent = level.message;
  render();
}

function findRow(file) {
  return [...document.querySelectorAll(".file-row")].find((item) => item.dataset.key === fileKey(file));
}

function updateRow(file, status, className = "") {
  const row = findRow(file);
  if (!row) return;
  const statusEl = row.querySelector(".file-status");
  statusEl.textContent = status;
  statusEl.className = `file-status ${className}`;
  row.querySelector(".file-bar").hidden = true;
}

function optimizedResults() {
  return state.results.filter((result) => result.status === "optimized" && result.blob);
}

function lossBudget() {
  return currentLevel().lossBudget;
}

function selectedQuality() {
  return currentLevel().quality / 100;
}

function targetSizeBytes() {
  return Number(el.targetSize.value || 0) * 1024 * 1024;
}

function minSavingsPercent() {
  return Number(el.minSavings.value || 0);
}

function selectedCodec() {
  return el.codec ? el.codec.value : "webp";
}

const CODEC_HINTS = {
  webp: "빠르고 어떤 기기에서도 잘 열립니다. 추가 다운로드가 없어 가볍습니다.",
  auto: "AVIF로 먼저 시도하고, 안 되면 WebP로 자동 대체합니다. 인코더를 새로 내려받아 처음 실행이 조금 느립니다.",
  avif: "같은 화질에서 WebP보다 더 작지만, 최신 뷰어에서만 열리고 인코더를 내려받습니다.",
  jxl: "제일 작지만 실험적입니다 — 여는 프로그램이 지원하는지 먼저 확인하세요.",
};

function applyCodecHint() {
  if (el.codecHint) el.codecHint.textContent = CODEC_HINTS[selectedCodec()] || "";
}

function buildOptions() {
  const level = currentLevel();
  return {
    lossBudget: level.lossBudget,
    quality: level.quality / 100,
    minSavingsPercent: minSavingsPercent(),
    targetSizeBytes: targetSizeBytes(),
    maxDimension: level.maxDimension,
    codec: selectedCodec(),
  };
}

function setAppStatus(text) {
  if (el.appStatus) el.appStatus.textContent = text;
}

function dependencyStatus() {
  const archive = window.JSZip ? "압축 엔진 준비됨" : "압축 엔진 불가";
  const pdf = window.PDFLib ? "PDF 엔진 준비됨" : "PDF 엔진 불가";
  return `${archive} / ${pdf}`;
}

function refreshAppStatus() {
  const network = navigator.onLine ? "온라인" : "오프라인";
  setAppStatus(`${network} · 캐시됨 · ${dependencyStatus()} · ${APP_VERSION}`);
}

function recordResult(file, result) {
  const blobUrl = result.blob ? URL.createObjectURL(result.blob) : null;
  if (blobUrl) activeBlobUrls.add(blobUrl);
  const record = {
    key: fileKey(file),
    name: file.name,
    category: fileCategory(file),
    status: result.status,
    originalSize: file.size,
    outputSize: result.blob?.size || file.size,
    savedBytes: result.saved || 0,
    message: result.message || result.status,
    outName: result.outName || null,
    blob: result.blob || null,
    blobUrl,
  };
  state.results.push(record);
  const row = findRow(file);
  if (row) applyResultToRow(row, record, file);
}

function recordError(file, message) {
  const record = { key: fileKey(file), name: file.name, status: "error", message, originalSize: file.size, outputSize: file.size, savedBytes: 0 };
  state.results.push(record);
  const row = findRow(file);
  if (row) applyResultToRow(row, record, file);
}

// The "before" object URL is only created while the modal is open (no point
// holding one per row for files that never get previewed) and revoked on
// close. The "after" URL already lives on the result record.
let previewBeforeUrl = null;
let previewDragging = false;

function setPreviewPosition(percent) {
  const clamped = Math.min(100, Math.max(0, percent));
  el.previewBeforeWrap.style.width = `${clamped}%`;
  el.previewHandle.style.left = `${clamped}%`;
  el.previewHandle.setAttribute("aria-valuenow", String(Math.round(clamped)));
}

function previewPercentFromEvent(event) {
  const rect = el.previewSlider.getBoundingClientRect();
  const x = (event.touches ? event.touches[0].clientX : event.clientX) - rect.left;
  return (x / rect.width) * 100;
}

function onPreviewDragStart(event) {
  previewDragging = true;
  setPreviewPosition(previewPercentFromEvent(event));
}

function onPreviewDragMove(event) {
  if (!previewDragging) return;
  setPreviewPosition(previewPercentFromEvent(event));
}

function onPreviewDragEnd() {
  previewDragging = false;
}

function onPreviewKeydown(event) {
  const current = parseFloat(el.previewHandle.style.left) || 50;
  if (event.key === "ArrowLeft") setPreviewPosition(current - 5);
  else if (event.key === "ArrowRight") setPreviewPosition(current + 5);
}

function openPreview(file, result) {
  if (previewBeforeUrl) URL.revokeObjectURL(previewBeforeUrl);
  previewBeforeUrl = URL.createObjectURL(file);
  el.previewBefore.src = previewBeforeUrl;
  el.previewAfter.src = result.blobUrl;
  el.previewTitle.textContent = `${file.name} -- ${formatBytes(result.originalSize)} -> ${formatBytes(result.outputSize)}`;
  setPreviewPosition(50);
  el.previewModal.hidden = false;
}

function closePreview() {
  el.previewModal.hidden = true;
  if (previewBeforeUrl) {
    URL.revokeObjectURL(previewBeforeUrl);
    previewBeforeUrl = null;
  }
  el.previewBefore.src = "";
  el.previewAfter.src = "";
}

el.previewClose.addEventListener("click", closePreview);
el.previewModal.addEventListener("click", (event) => {
  if (event.target === el.previewModal) closePreview();
});
el.previewHandle.addEventListener("pointerdown", onPreviewDragStart);
el.previewSlider.addEventListener("pointerdown", onPreviewDragStart);
window.addEventListener("pointermove", onPreviewDragMove);
window.addEventListener("pointerup", onPreviewDragEnd);
el.previewHandle.addEventListener("keydown", onPreviewKeydown);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !el.previewModal.hidden) closePreview();
});

// Multiple files at once are handed to a pool of Web Workers, so several
// files compress in parallel instead of one at a time. "auto" sizes the pool
// to the device rather than just the core count: each worker loads its own
// copy of JSZip/pdf-lib, so a phone reporting 8 cores but little RAM still
// shouldn't spin up 8 of them. Touch devices (phones/tablets, via a coarse
// pointer) and browsers reporting low deviceMemory get a lower cap -- still
// multi-file, just not maxed out -- while the concurrency picker lets anyone
// override it either way.
function detectAutoPoolSize() {
  const cores = navigator.hardwareConcurrency || 4;
  const isTouchDevice = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
  let cap = isTouchDevice ? 4 : 8;
  if (typeof navigator.deviceMemory === "number" && navigator.deviceMemory <= 4) {
    cap = Math.min(cap, 2);
  }
  return Math.max(1, Math.min(cores, cap));
}

const AUTO_POOL_SIZE = detectAutoPoolSize();

function selectedPoolSize() {
  const raw = el.concurrency ? el.concurrency.value : "auto";
  if (raw === "auto") return AUTO_POOL_SIZE;
  return Math.max(1, Number(raw) || AUTO_POOL_SIZE);
}

const CONCURRENCY_HINTS = {
  auto: `이 PC 코어 수에 맞춰 자동으로 정해집니다 (지금은 ${AUTO_POOL_SIZE}개).`,
  1: "한 번에 하나씩만 처리합니다. 가장 안정적이지만 가장 느립니다.",
  2: "두 파일을 동시에 처리합니다.",
  4: "네 파일을 동시에 처리합니다.",
  8: "여덟 파일을 동시에 처리합니다. 저사양 PC에서는 버벅일 수 있습니다.",
};

function applyConcurrencyHint() {
  if (!el.concurrency || !el.concurrencyHint) return;
  el.concurrencyHint.textContent = CONCURRENCY_HINTS[el.concurrency.value] || "";
}

// onFailure lets a caller recover from a hard encode error (e.g. AVIF wasm
// failing to load) by re-running that one file through a different path
// instead of recording it as an error. It must NOT fire for legitimate
// skip outcomes (animated image, savings threshold not met) -- those come
// back as `ok: true` with a "skipped" status and are recorded as-is.
function runWithWorkerPool(files, opts, onDone, workerScript = "./worker.js?v25", workerOptions, onFailure) {
  if (!files.length) return Promise.resolve();
  return new Promise((resolve) => {
    const queue = files.slice();
    const poolSize = Math.min(selectedPoolSize(), files.length);
    let activeWorkers = poolSize;

    function dispatchNext(worker) {
      const file = queue.shift();
      if (!file) {
        worker.terminate();
        activeWorkers -= 1;
        if (activeWorkers === 0) resolve();
        return;
      }
      updateRow(file, "처리 중...");
      const handleFailure = async (message) => {
        if (!onFailure) {
          recordError(file, message);
          onDone();
          dispatchNext(worker);
          return;
        }
        try {
          recordResult(file, await onFailure(file));
        } catch (error) {
          recordError(file, error.message || message);
        }
        onDone();
        dispatchNext(worker);
      };
      worker.onmessage = (event) => {
        // pdf.js internals loaded inside the worker can emit their own
        // handshake messages (targetName: "main") -- not pool protocol.
        if (event.data && event.data.targetName) return;
        const { ok, result, error } = event.data;
        if (ok) {
          recordResult(file, result);
          onDone();
          dispatchNext(worker);
        } else {
          handleFailure(error);
        }
      };
      worker.onerror = (event) => {
        handleFailure(event.message || "작업 스레드 오류");
      };
      worker.postMessage({ file, opts });
    }

    for (let i = 0; i < poolSize; i++) {
      const worker = new Worker(workerScript, workerOptions);
      dispatchNext(worker);
    }
  });
}

// The AVIF/JXL worker needs OffscreenCanvas + module workers. Older or
// budget mobile browsers (older iOS Safari especially) can be missing one
// of these -- checking up front and routing everything through the classic
// WebP worker pool in that case means multi-file processing still runs
// (just at WebP quality) instead of every image failing one at a time.
const SUPPORTS_AVIF_JXL_WORKER = typeof OffscreenCanvas !== "undefined" && typeof Worker !== "undefined";

// AVIF/JXL only apply to standalone image files (archives/PDF stay WebP --
// see avif-jxl-worker.js for why), so a non-webp codec splits the batch
// across two worker pools running concurrently: the plain-image subset goes
// to the module-worker AVIF/JXL path, everything else stays on the classic
// WebP worker regardless of the codec picker. "auto" runs the image subset
// through AVIF for the best size-at-quality, but falls a single file back
// to WebP (main-thread, via optimize-core.js) if AVIF hard-fails -- e.g. the
// wasm encoder can't load on this browser/device.
function runWithCodecRouting(files, opts, onDone) {
  if (opts.codec === "webp" || !SUPPORTS_AVIF_JXL_WORKER) {
    return runWithWorkerPool(files, opts, onDone, "./worker.js?v25");
  }
  const imageFiles = files.filter((f) => imageExts.has(extOf(f)));
  const otherFiles = files.filter((f) => !imageExts.has(extOf(f)));
  const isAuto = opts.codec === "auto";
  const engineOpts = isAuto ? { ...opts, codec: "avif" } : opts;
  const fallbackToWebp = isAuto ? (file) => optimizeFile(file, { ...opts, codec: "webp" }) : null;
  return Promise.all([
    runWithWorkerPool(imageFiles, engineOpts, onDone, "./avif-jxl-worker.js?v25", { type: "module" }, fallbackToWebp),
    runWithWorkerPool(otherFiles, { ...opts, codec: "webp" }, onDone, "./worker.js?v25"),
  ]);
}

function formatDuration(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return `${seconds}초`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes < 60) return `${minutes}분 ${rest}초`;
  const hours = Math.floor(minutes / 60);
  return `${hours}시간 ${minutes % 60}분`;
}

function updateEta(startedAt, completed, total) {
  if (!el.etaText) return;
  if (completed <= 0 || completed >= total) {
    el.etaText.textContent = "";
    return;
  }
  const elapsedSeconds = (performance.now() - startedAt) / 1000;
  const avgPerFile = elapsedSeconds / completed;
  const remaining = total - completed;
  el.etaText.textContent = `${completed}/${total} 처리 중 · 남은 시간 약 ${formatDuration(avgPerFile * remaining)}`;
}

async function runSequentialFallback(files, opts, onDone) {
  for (const file of files) {
    updateRow(file, "처리 중...");
    try {
      const result = await optimizeFile(file, opts);
      recordResult(file, result);
    } catch (error) {
      recordError(file, error.message);
    }
    onDone();
  }
}

function setRunning(running) {
  state.running = running;
  el.runButton.disabled = running;
  el.clearButton.disabled = running;
  el.fileInput.disabled = running;
  el.dropZone.classList.toggle("busy", running);
  el.dropZone.setAttribute("aria-disabled", String(running));
}

async function run() {
  if (!state.files.length || state.running) return;
  closePreview();
  revokeTrackedBlobUrls();
  state.results = [];
  setRunning(true);
  el.reportButton.disabled = true;
  el.bundleButton.disabled = true;
  el.meterFill.style.width = "0%";

  const opts = buildOptions();
  const files = state.files.slice();
  const startedAt = performance.now();
  let completed = 0;
  if (el.etaText) {
    el.etaText.textContent = opts.codec !== "webp" && !SUPPORTS_AVIF_JXL_WORKER
      ? "이 브라우저는 AVIF/JPEG XL을 지원하지 않아 WebP로 처리합니다."
      : files.length > 1 ? "예상 시간 계산 중…" : "";
  }
  const onDone = () => {
    completed += 1;
    el.meterFill.style.width = `${Math.round((completed / files.length) * 100)}%`;
    updateEta(startedAt, completed, files.length);
  };

  try {
    if (typeof Worker !== "undefined") {
      await runWithCodecRouting(files, opts, onDone);
    } else {
      // No Worker support (very rare today) -- optimize-core.js's sequential
      // path only knows WebP, so fall back to that regardless of the picker.
      await runSequentialFallback(files, { ...opts, codec: "webp" }, onDone);
    }
  } catch (error) {
    setAppStatus(`처리 중 오류: ${error.message || error}`);
  }

  setRunning(false);
  el.reportButton.disabled = state.results.length === 0;
  el.bundleButton.disabled = optimizedResults().length === 0;
  const saved = state.results.reduce((sum, result) => sum + (result.savedBytes || 0), 0);
  const original = state.results.reduce((sum, result) => sum + (result.originalSize || 0), 0);
  const pct = original ? ((saved / original) * 100).toFixed(2) : "0.00";
  const totalSeconds = (performance.now() - startedAt) / 1000;
  el.totals.textContent = `${state.results.length}개 처리 완료 / ${formatBytes(saved)} 절감 (${pct}%)`;
  if (el.etaText) el.etaText.textContent = `총 ${formatDuration(totalSeconds)} 걸림`;
}

function saveReport() {
  const cleanResults = state.results.map(({ blob, ...result }) => result);
  const blob = new Blob([JSON.stringify({
    generatedAt: new Date().toISOString(),
    app: "OptimizerZero Web Lite",
    options: {
      strengthLevel: Number(el.strength.value),
      strengthLabel: currentLevel().label,
      profile: currentLevel().profile,
      lossBudget: lossBudget(),
      quality: Math.round(selectedQuality() * 100),
      targetSizeMB: Number(el.targetSize.value || 0),
      minSavingsPercent: minSavingsPercent(),
      maxInputMB: Number(el.limit.value),
    },
    results: cleanResults,
  }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "optimizerzero-web-report.json";
  a.click();
  URL.revokeObjectURL(url);
}

async function saveBundle() {
  if (!window.JSZip) {
    setAppStatus("압축 엔진 불가 · 결과 ZIP 비활성화");
    return;
  }
  const zip = new JSZip();
  const results = optimizedResults();
  const categories = new Set(results.map((r) => r.category || "기타"));
  for (const result of results) {
    const name = result.outName || result.name;
    // folder-per-type only when the batch actually mixes types
    zip.file(categories.size > 1 ? `${result.category || "기타"}/${name}` : name, result.blob);
  }
  const blob = await zip.generateAsync({
    type: "blob",
    compression: "DEFLATE",
    compressionOptions: { level: 9 },
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "optimizerzero-results.zip";
  a.click();
  URL.revokeObjectURL(url);
}

el.dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    el.fileInput.click();
  }
});
el.fileInput.addEventListener("change", (event) => setFiles(event.target.files));
if (el.folderInput) el.folderInput.addEventListener("change", (event) => setFiles(event.target.files));

// Dropped directories arrive as FileSystemEntry trees, not File objects --
// walk them. Entries MUST be captured synchronously during the drop event;
// after the first await the DataTransferItemList is gone.
async function filesFromDataTransfer(dataTransfer) {
  const flatFiles = dataTransfer.files;
  const entries = dataTransfer.items
    ? [...dataTransfer.items].map((item) => item.webkitGetAsEntry && item.webkitGetAsEntry()).filter(Boolean)
    : [];
  if (!entries.some((entry) => entry.isDirectory)) return flatFiles;
  const collected = [];
  const walk = async (entry) => {
    if (entry.isFile) {
      collected.push(await new Promise((resolve, reject) => entry.file(resolve, reject)));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {
        batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
        for (const child of batch) await walk(child);
      } while (batch.length);
    }
  };
  for (const entry of entries) await walk(entry);
  return collected;
}
el.strength.addEventListener("input", applyStrength);
if (el.codec) el.codec.addEventListener("change", applyCodecHint);
if (el.concurrency) el.concurrency.addEventListener("change", applyConcurrencyHint);
el.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  el.dropZone.classList.add("dragging");
});
el.dropZone.addEventListener("dragleave", () => el.dropZone.classList.remove("dragging"));
el.dropZone.addEventListener("drop", async (event) => {
  event.preventDefault();
  el.dropZone.classList.remove("dragging");
  if (state.running) return;
  setFiles(await filesFromDataTransfer(event.dataTransfer));
});
if (el.folderButton) el.folderButton.addEventListener("click", (event) => {
  event.preventDefault();
  event.stopPropagation();
  if (!state.running) el.folderInput.click();
});
el.runButton.addEventListener("click", run);
el.clearButton.addEventListener("click", () => {
  closePreview();
  revokeTrackedBlobUrls();
  state.files = [];
  state.rejected = [];
  state.results = [];
  el.meterFill.style.width = "0%";
  el.reportButton.disabled = true;
  el.bundleButton.disabled = true;
  if (el.etaText) el.etaText.textContent = "";
  render();
});
el.reportButton.addEventListener("click", saveReport);
el.bundleButton.addEventListener("click", saveBundle);
window.addEventListener("online", refreshAppStatus);
window.addEventListener("offline", refreshAppStatus);
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("./service-worker.js")
    .then(refreshAppStatus)
    .catch(refreshAppStatus);
}

window.__optimizerZeroWeb = {
  optimizeFile,
  optimizeArchive,
  optimizePdfFile,
  optimizeGenericFile,
  optimizeImageFile,
  outputAccepted,
  dependencyStatus,
};

refreshAppStatus();
applyStrength();
applyCodecHint();
applyConcurrencyHint();
render();
