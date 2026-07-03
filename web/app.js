const archiveExts = new Set(["zip", "cbz", "epub", "docx", "pptx", "xlsx"]);
const imageExts = new Set(["png", "jpg", "jpeg", "webp"]);
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
    message: "보관용 추천: 원본 보존, 무손실 중심, 큰 파일 허용.",
  },
  share: {
    profile: "balanced",
    lossBudget: "low",
    quality: 88,
    targetSize: 0,
    minSavings: 1,
    limit: 75,
    message: "공유용 추천: 균형 압축, 낮은 손실, 화질 88.",
  },
  messenger: {
    profile: "strong",
    lossBudget: "high",
    quality: 70,
    targetSize: 10,
    minSavings: 3,
    limit: 25,
    message: "메신저용 추천: 용량 우선, 결과 확인 후 사용.",
  },
  email: {
    profile: "balanced",
    lossBudget: "medium",
    quality: 82,
    targetSize: 25,
    minSavings: 1,
    limit: 25,
    message: "이메일 추천: 첨부 제한에 맞추고 중간 손실 압축.",
  },
  quality: {
    profile: "balanced",
    lossBudget: "low",
    quality: 92,
    targetSize: 0,
    minSavings: 1,
    limit: 150,
    message: "화질 우선 추천: 거의 티 안 나게, 절감이 작으면 스킵.",
  },
};

function extOf(file) {
  return (file.name.split(".").pop() || "").toLowerCase();
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
  return archiveExts.has(ext) || imageExts.has(ext);
}

function setFiles(files) {
  const maxBytes = Number(el.limit.value) * 1024 * 1024;
  const incoming = [];
  state.rejected = [];
  for (const file of files) {
    if (!supported(file)) {
      state.rejected.push({ name: file.name, reason: "지원하지 않는 형식" });
    } else if (file.size > maxBytes) {
      state.rejected.push({ name: file.name, reason: `${el.limit.value} MB 초과` });
    } else {
      incoming.push(file);
    }
  }
  const known = new Set(state.files.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
  for (const file of incoming) {
    const key = `${file.name}:${file.size}:${file.lastModified}`;
    if (!known.has(key)) state.files.push(file);
  }
  render();
}

function render() {
  el.fileList.innerHTML = "";
  el.emptyState.hidden = state.files.length > 0;
  const totalSize = state.files.reduce((sum, file) => sum + file.size, 0);
  const rejected = state.rejected.length ? ` / 제외 ${state.rejected.length}` : "";
  el.totals.textContent = `${state.files.length} files / ${formatBytes(totalSize)}${rejected}`;
  for (const file of state.files) {
    const row = el.rowTemplate.content.firstElementChild.cloneNode(true);
    row.dataset.name = file.name;
    row.querySelector(".file-name").textContent = file.name;
    row.querySelector(".file-meta").textContent = `${extOf(file).toUpperCase()} / ${formatBytes(file.size)}`;
    row.querySelector(".file-status").textContent = "대기";
    el.fileList.append(row);
  }
  for (const item of state.rejected) {
    const row = el.rowTemplate.content.firstElementChild.cloneNode(true);
    row.querySelector(".file-name").textContent = item.name;
    row.querySelector(".file-meta").textContent = "목록 제외";
    row.querySelector(".file-status").textContent = item.reason;
    row.querySelector(".file-status").className = "file-status error";
    el.fileList.append(row);
  }
}

function applyIntent() {
  const preset = intentPresets[el.intent.value] || intentPresets.share;
  el.profile.value = preset.profile;
  el.lossBudget.value = preset.lossBudget;
  el.quality.value = String(preset.quality);
  el.targetSize.value = String(preset.targetSize);
  el.minSavings.value = String(preset.minSavings);
  el.limit.value = String(preset.limit);
  el.qualityLabel.textContent = String(preset.quality);
  document.querySelector("#recommendation").textContent = preset.message;
  render();
}

function updateRow(file, status, className = "") {
  const row = [...document.querySelectorAll(".file-row")].find((item) => item.dataset.name === file.name);
  if (!row) return;
  const statusEl = row.querySelector(".file-status");
  statusEl.textContent = status;
  statusEl.className = `file-status ${className}`;
}

function attachDownload(file, blob, name) {
  const row = [...document.querySelectorAll(".file-row")].find((item) => item.dataset.name === file.name);
  if (!row) return;
  const button = row.querySelector(".download-button");
  const url = URL.createObjectURL(blob);
  button.hidden = false;
  button.onclick = () => {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
  };
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
  if (outputSize >= originalSize) return { ok: false, message: "더 작아지지 않음" };
  const saved = originalSize - outputSize;
  const pct = originalSize ? (saved / originalSize) * 100 : 0;
  if (pct < minSavingsPercent()) {
    return { ok: false, message: `절감 ${pct.toFixed(2)}%, 기준 ${minSavingsPercent()}% 미만` };
  }
  const target = targetSizeBytes();
  if (target > 0 && outputSize > target) {
    return { ok: false, message: `목표 ${formatBytes(target)} 초과` };
  }
  return { ok: true, saved };
}

function setAppStatus(text) {
  if (el.appStatus) el.appStatus.textContent = text;
}

async function recompressImage(blob) {
  const image = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d", { alpha: false });
  ctx.drawImage(image, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/webp", selectedQuality()));
}

async function optimizeImageFile(file) {
  if (lossBudget() === "none") return { status: "skipped", message: "손실 허용 없음" };
  const blob = await recompressImage(file);
  if (!blob) return { status: "skipped", message: "변환 실패" };
  const accepted = outputAccepted(file.size, blob.size);
  if (!accepted.ok) return { status: "skipped", message: accepted.message };
  const outName = file.name.replace(/(\.[^.]+)?$/, ".ozero.webp");
  return { status: "optimized", blob, outName, saved: accepted.saved };
}

function safeArchiveName(name) {
  const cleanName = name.replaceAll("\\", "/").replace(/^\/+/, "");
  if (!cleanName || cleanName.includes("../") || cleanName.startsWith("..")) {
    throw new Error(`위험한 경로: ${name}`);
  }
  return cleanName;
}

async function optimizeArchive(file) {
  if (!window.JSZip) throw new Error("JSZip 로드 실패");
  const source = await JSZip.loadAsync(file);
  const output = new JSZip();
  for (const [name, entry] of Object.entries(source.files)) {
    if (entry.dir) continue;
    const cleanName = safeArchiveName(name);
    const data = await entry.async("blob");
    const compression = extOf(file) === "epub" && cleanName === "mimetype" ? "STORE" : "DEFLATE";
    output.file(cleanName, data, { compression });
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
  return { status: "optimized", blob, outName, saved: accepted.saved, message: "컨테이너 재압축" };
}

async function optimizeFile(file) {
  const ext = extOf(file);
  if (imageExts.has(ext)) return optimizeImageFile(file);
  if (archiveExts.has(ext)) return optimizeArchive(file);
  return { status: "skipped", message: "지원하지 않는 형식" };
}

async function run() {
  if (!state.files.length) return;
  state.results = [];
  el.runButton.disabled = true;
  el.reportButton.disabled = true;
  el.bundleButton.disabled = true;
  for (const [index, file] of state.files.entries()) {
    updateRow(file, "작업 중...");
    try {
      const result = await optimizeFile(file);
      const record = {
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
      const label = result.status === "optimized" ? `${formatBytes(result.saved)} 절감` : result.message;
      updateRow(file, label, result.status === "optimized" ? "done" : "");
    } catch (error) {
      state.results.push({ name: file.name, status: "error", message: error.message, originalSize: file.size });
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
  if (!window.JSZip) return;
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

el.dropZone.addEventListener("click", () => el.fileInput.click());
el.dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") el.fileInput.click();
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
window.addEventListener("online", () => setAppStatus("online / cached"));
window.addEventListener("offline", () => setAppStatus("offline / cached"));
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("./service-worker.js")
    .then(() => setAppStatus(navigator.onLine ? "online / cached" : "offline / cached"))
    .catch(() => setAppStatus("online"));
}
applyIntent();
render();
