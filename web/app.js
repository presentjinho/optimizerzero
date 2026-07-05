const archiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"]);
const imageExts = new Set(["png", "jpg", "jpeg", "webp"]);
const archiveImageExts = new Set(["jpg", "jpeg", "webp"]);
const imageOptimizableArchiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx", "odt", "ods", "odp", "jar"]);
const state = { files: [], rejected: [], results: [] };
const el = {
  dropZone: document.querySelector("#dropZone"),
  fileInput: document.querySelector("#fileInput"),
  fileList: document.querySelector("#fileList"),
  emptyState: document.querySelector("#emptyState"),
  totals: document.querySelector("#totals"),
  appStatus: document.querySelector("#appStatus"),
  intent: document.querySelector("#intent"),
  profile: document.querySelector("#profile"),
  lossBudget: document.querySelector("#lossBudget"),
  quality: document.querySelector("#quality"),
  qualityLabel: document.querySelector("#qualityLabel"),
  targetSize: document.querySelector("#targetSize"),
  minSavings: document.querySelector("#minSavings"),
  limit: document.querySelector("#limit"),
  runButton: document.querySelector("#runButton"),
  clearButton: document.querySelector("#clearButton"),
  reportButton: document.querySelector("#reportButton"),
  bundleButton: document.querySelector("#bundleButton"),
  meterFill: document.querySelector("#meterFill"),
  rowTemplate: document.querySelector("#fileRowTemplate"),
};

const intentPresets = {
  archive: {
    profile: "safe",
    lossBudget: "none",
    quality: 96,
    targetSize: 0,
    minSavings: 0,
    limit: 150,
    message: "Archive: preserve originals, lossless-first, larger input allowed.",
  },
  share: {
    profile: "balanced",
    lossBudget: "low",
    quality: 88,
    targetSize: 0,
    minSavings: 1,
    limit: 75,
    message: "Share: balanced compression, low visual loss, quality 88.",
  },
  messenger: {
    profile: "strong",
    lossBudget: "high",
    quality: 70,
    targetSize: 10,
    minSavings: 3,
    limit: 25,
    message: "Messenger: size first. Check the result before sharing.",
  },
  email: {
    profile: "balanced",
    lossBudget: "medium",
    quality: 82,
    targetSize: 25,
    minSavings: 1,
    limit: 25,
    message: "Email: fit attachment limits with moderate visual loss.",
  },
  quality: {
    profile: "balanced",
    lossBudget: "low",
    quality: 92,
    targetSize: 0,
    minSavings: 1,
    limit: 150,
    message: "Quality: near-original look. Skip tiny savings.",
  },
};

function extOfName(name) {
  return (name.split(".").pop() || "").toLowerCase();
}

function extOf(file) {
  return extOfName(file.name);
}

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
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

function supported(file) {
  const ext = extOf(file);
  return archiveExts.has(ext) || imageExts.has(ext) || Boolean(window.JSZip);
}

function setFiles(files) {
  const maxBytes = Number(el.limit.value) * 1024 * 1024;
  const incoming = [];
  state.rejected = [];
  for (const file of files) {
    if (!supported(file)) {
      state.rejected.push({ name: file.name, reason: "archive engine unavailable" });
    } else if (file.size > maxBytes) {
      state.rejected.push({ name: file.name, reason: `over ${el.limit.value} MB` });
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

function resultLabel(result) {
  if (result.status === "optimized") return `saved ${formatBytes(result.savedBytes)}`;
  return result.message || result.status;
}

function resultClass(result) {
  if (result.status === "optimized") return "done";
  if (result.status === "error") return "error";
  return "";
}

function configureDownloadButton(button, blob, name) {
  const url = URL.createObjectURL(blob);
  button.hidden = false;
  button.onclick = () => {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
  };
}

function render() {
  el.fileList.innerHTML = "";
  el.emptyState.hidden = state.files.length > 0;
  const totalSize = state.files.reduce((sum, file) => sum + file.size, 0);
  const rejected = state.rejected.length ? ` / rejected ${state.rejected.length}` : "";
  el.totals.textContent = `${state.files.length} files / ${formatBytes(totalSize)}${rejected}`;
  for (const file of state.files) {
    const row = el.rowTemplate.content.firstElementChild.cloneNode(true);
    const key = fileKey(file);
    row.dataset.key = key;
    row.querySelector(".file-name").textContent = file.name;
    row.querySelector(".file-meta").textContent = `${extOf(file).toUpperCase()} / ${formatBytes(file.size)}`;
    row.querySelector(".file-status").textContent = "ready";
    row.querySelector(".remove-button").addEventListener("click", () => removeFile(key));
    const result = resultForKey(key);
    if (result) {
      const statusEl = row.querySelector(".file-status");
      statusEl.textContent = resultLabel(result);
      statusEl.className = `file-status ${resultClass(result)}`;
      if (result.blob) configureDownloadButton(row.querySelector(".download-button"), result.blob, result.outName || result.name);
    }
    el.fileList.append(row);
  }
  for (const item of state.rejected) {
    const row = el.rowTemplate.content.firstElementChild.cloneNode(true);
    row.querySelector(".file-name").textContent = item.name;
    row.querySelector(".file-meta").textContent = "not queued";
    row.querySelector(".file-status").textContent = item.reason;
    row.querySelector(".file-status").className = "file-status error";
    row.querySelector(".remove-button").hidden = true;
    el.fileList.append(row);
  }
}

function applyIntent() {
  const preset = intentPresets[el.intent.value] || intentPresets.share;
  const selectedIntent = el.intent.selectedOptions[0];
  el.profile.value = preset.profile;
  el.lossBudget.value = preset.lossBudget;
  el.quality.value = String(preset.quality);
  el.targetSize.value = String(preset.targetSize);
  el.minSavings.value = String(preset.minSavings);
  el.limit.value = String(preset.limit);
  el.qualityLabel.textContent = String(preset.quality);
  document.querySelector("#recommendation").textContent = selectedIntent?.dataset.message || preset.message;
  render();
}

function updateRow(file, status, className = "") {
  const row = [...document.querySelectorAll(".file-row")].find((item) => item.dataset.key === fileKey(file));
  if (!row) return;
  const statusEl = row.querySelector(".file-status");
  statusEl.textContent = status;
  statusEl.className = `file-status ${className}`;
}

function attachDownload(file, blob, name) {
  const row = [...document.querySelectorAll(".file-row")].find((item) => item.dataset.key === fileKey(file));
  if (!row) return;
  const button = row.querySelector(".download-button");
  configureDownloadButton(button, blob, name);
}

function optimizedResults() {
  return state.results.filter((result) => result.status === "optimized" && result.blob);
}

function lossBudget() {
  if (el.lossBudget.value) return el.lossBudget.value;
  if (el.profile.value === "safe") return "none";
  if (el.profile.value === "balanced") return "low";
  return "medium";
}

function selectedQuality() {
  const explicit = Number(el.quality.value) / 100;
  if (lossBudget() === "high") return Math.min(explicit, 0.72);
  if (lossBudget() === "medium") return Math.min(explicit, 0.82);
  if (lossBudget() === "low") return Math.min(explicit, 0.92);
  return explicit;
}

function targetSizeBytes() {
  return Number(el.targetSize.value || 0) * 1024 * 1024;
}

function minSavingsPercent() {
  return Number(el.minSavings.value || 0);
}

function outputAccepted(originalSize, outputSize) {
  if (outputSize >= originalSize) return { ok: false, message: "not smaller" };
  const saved = originalSize - outputSize;
  const pct = originalSize ? (saved / originalSize) * 100 : 0;
  if (pct < minSavingsPercent()) {
    return { ok: false, message: `saved ${pct.toFixed(2)}%, below ${minSavingsPercent()}%` };
  }
  const target = targetSizeBytes();
  if (target > 0 && outputSize > target) {
    return { ok: false, message: `over target ${formatBytes(target)}` };
  }
  return { ok: true, saved };
}

function setAppStatus(text) {
  if (el.appStatus) el.appStatus.textContent = text;
}

function dependencyStatus() {
  return window.JSZip ? "archive engine ready" : "image-only / archive engine unavailable";
}

function refreshAppStatus() {
  const network = navigator.onLine ? "online" : "offline";
  setAppStatus(`${network} / cached / ${dependencyStatus()}`);
}

function imageMimeForExt(ext) {
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  if (ext === "webp") return "image/webp";
  return "image/webp";
}

async function recompressImage(blob, mimeType = "image/webp") {
  const image = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d", { alpha: mimeType === "image/png" });
  ctx.drawImage(image, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, mimeType, selectedQuality()));
}

async function optimizeImageFile(file) {
  if (lossBudget() === "none") return { status: "skipped", message: "loss budget is none" };
  const blob = await recompressImage(file, "image/webp");
  if (!blob) return { status: "skipped", message: "conversion failed" };
  const accepted = outputAccepted(file.size, blob.size);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.webp");
  return { status: "optimized", blob, outName, saved: accepted.saved };
}

function safeArchiveName(name) {
  const cleanName = name.replaceAll("\\", "/").replace(/^\/+/, "");
  if (!cleanName || cleanName.includes("../") || cleanName.startsWith("..")) {
    throw new Error(`unsafe path: ${name}`);
  }
  return cleanName;
}

function canRecompressArchiveImages(fileExt) {
  return lossBudget() !== "none" && imageOptimizableArchiveExts.has(fileExt);
}

async function maybeOptimizeArchiveEntry(fileExt, cleanName, data) {
  const entryExt = extOfName(cleanName);
  if (!canRecompressArchiveImages(fileExt) || !archiveImageExts.has(entryExt)) {
    return { blob: data, changed: false };
  }
  const mimeType = imageMimeForExt(entryExt);
  let optimized;
  try {
    optimized = await recompressImage(data, mimeType);
  } catch {
    return { blob: data, changed: false, skipped: true };
  }
  if (!optimized || optimized.size >= data.size) return { blob: data, changed: false };
  return { blob: optimized, changed: true };
}

async function optimizeArchive(file) {
  if (!window.JSZip) throw new Error("Archive engine unavailable. Standalone images still work.");
  const fileExt = extOf(file);
  const source = await JSZip.loadAsync(file);
  const output = new JSZip();
  let imageEntriesOptimized = 0;
  let imageEntriesSkipped = 0;
  for (const [name, entry] of Object.entries(source.files)) {
    if (entry.dir) continue;
    const cleanName = safeArchiveName(name);
    const data = await entry.async("blob");
    const entryResult = await maybeOptimizeArchiveEntry(fileExt, cleanName, data);
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
  const accepted = outputAccepted(file.size, blob.size);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)$/, ".ozero$1");
  const detailParts = imageEntriesOptimized ? [`container + ${imageEntriesOptimized} image entries`] : ["container recompressed"];
  if (imageEntriesSkipped) detailParts.push(`${imageEntriesSkipped} image entries kept original`);
  const detail = detailParts.join(" / ");
  return { status: "optimized", blob, outName, saved: accepted.saved, message: detail };
}

async function optimizeGenericFile(file) {
  if (!window.JSZip) throw new Error("Archive engine unavailable.");
  const output = new JSZip();
  output.file(safeArchiveName(file.name), file);
  const blob = await output.generateAsync({
    type: "blob",
    compression: "DEFLATE",
    compressionOptions: { level: 9 },
    mimeType: "application/zip",
  });
  const accepted = outputAccepted(file.size, blob.size);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.zip");
  return { status: "optimized", blob, outName, saved: accepted.saved, message: "generic ZIP fallback" };
}

async function optimizeFile(file) {
  const ext = extOf(file);
  if (imageExts.has(ext)) return optimizeImageFile(file);
  if (archiveExts.has(ext)) return optimizeArchive(file);
  return optimizeGenericFile(file);
}

async function run() {
  if (!state.files.length) return;
  state.results = [];
  el.runButton.disabled = true;
  el.reportButton.disabled = true;
  el.bundleButton.disabled = true;
  for (const [index, file] of state.files.entries()) {
    updateRow(file, "working...");
    try {
      const result = await optimizeFile(file);
      const record = {
        key: fileKey(file),
        name: file.name,
        status: result.status,
        originalSize: file.size,
        outputSize: result.blob?.size || file.size,
        savedBytes: result.saved || 0,
        message: result.message || result.status,
        outName: result.outName || null,
        blob: result.blob || null,
      };
      state.results.push(record);
      if (result.blob) attachDownload(file, result.blob, result.outName);
      const label = result.status === "optimized" ? `saved ${formatBytes(result.saved)}` : result.message;
      updateRow(file, label, result.status === "optimized" ? "done" : "");
    } catch (error) {
      state.results.push({ key: fileKey(file), name: file.name, status: "error", message: error.message, originalSize: file.size });
      updateRow(file, error.message, "error");
    }
    el.meterFill.style.width = `${Math.round(((index + 1) / state.files.length) * 100)}%`;
  }
  el.runButton.disabled = false;
  el.reportButton.disabled = state.results.length === 0;
  el.bundleButton.disabled = optimizedResults().length === 0;
  const saved = state.results.reduce((sum, result) => sum + (result.savedBytes || 0), 0);
  const original = state.results.reduce((sum, result) => sum + (result.originalSize || 0), 0);
  const pct = original ? ((saved / original) * 100).toFixed(2) : "0.00";
  el.totals.textContent = `${state.results.length} processed / saved ${formatBytes(saved)} (${pct}%)`;
}

function saveReport() {
  const cleanResults = state.results.map(({ blob, ...result }) => result);
  const blob = new Blob([JSON.stringify({
    generatedAt: new Date().toISOString(),
    app: "OptimizerZero Web Lite",
    options: {
      intent: el.intent.value,
      profile: el.profile.value,
      lossBudget: lossBudget(),
      quality: Number(el.quality.value),
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
    setAppStatus("archive engine unavailable / bundle disabled");
    return;
  }
  const zip = new JSZip();
  for (const result of optimizedResults()) {
    zip.file(result.outName || result.name, result.blob);
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
el.intent.addEventListener("change", applyIntent);
el.quality.addEventListener("input", () => {
  el.qualityLabel.textContent = el.quality.value;
});
el.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  el.dropZone.classList.add("dragging");
});
el.dropZone.addEventListener("dragleave", () => el.dropZone.classList.remove("dragging"));
el.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  el.dropZone.classList.remove("dragging");
  setFiles(event.dataTransfer.files);
});
el.runButton.addEventListener("click", run);
el.clearButton.addEventListener("click", () => {
  state.files = [];
  state.rejected = [];
  state.results = [];
  el.meterFill.style.width = "0%";
  el.reportButton.disabled = true;
  el.bundleButton.disabled = true;
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
  optimizeGenericFile,
  optimizeImageFile,
  outputAccepted,
  dependencyStatus,
};

refreshAppStatus();
applyIntent();
render();
