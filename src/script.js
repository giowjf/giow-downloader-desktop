// API local — servidor Python rodando em localhost
let API = "http://localhost:5001";

// Detecta se está no Electron e pega a URL real da API
if (window.electronAPI) {
  window.electronAPI.getApiUrl().then(url => { API = url; });
}

let currentUrl = null;
let currentTitle = null;
let downloading = false;

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("analyzeBtn");
  const input = document.getElementById("url");

  btn.addEventListener("click", analyze);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") analyze(); });

  function updateBtn() {
    btn.classList.toggle("enabled", input.value.trim().length > 0);
  }
  input.addEventListener("input", updateBtn);
  updateBtn();

  input.addEventListener("focus", async () => {
    if (input.value.trim()) return;
    try {
      const text = await navigator.clipboard.readText();
      if (text.startsWith("http")) { input.value = text; updateBtn(); }
    } catch (_) {}
  });
});

function formatDuration(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}

function formatFilesize(b) {
  if (!b) return null;
  if (b >= 1_073_741_824) return `${(b/1_073_741_824).toFixed(1)} GB`;
  if (b >= 1_048_576) return `${(b/1_048_576).toFixed(0)} MB`;
  return `${(b/1024).toFixed(0)} KB`;
}

function badgeClass(ext) {
  if (ext === "mp4") return "badge-mp4";
  if (ext === "webm") return "badge-webm";
  if (ext === "mp3") return "badge-mp3";
  return "badge-other";
}

function setLoading(on) {
  const btn = document.getElementById("analyzeBtn");
  btn.disabled = on;
  btn.textContent = on ? "[ ... ]" : "[ SCAN ]";
}

function lockAllButtons(except) {
  document.querySelectorAll(".format-btn").forEach(b => {
    if (b !== except) { b.disabled = true; b.classList.add("dl-locked"); }
  });
}

function unlockAllButtons() {
  document.querySelectorAll(".format-btn").forEach(b => {
    b.disabled = false; b.classList.remove("dl-locked");
  });
}

function renderBtnPhase(btn, phase, pct = null) {
  const phases = {
    connecting:   { icon: "◈", label: "CONECTANDO...",   pulse: true,  bar: false },
    processing:   { icon: "◧", label: "PROCESSANDO...",  pulse: true,  bar: false },
    downloading:  { icon: "▶", label: "BAIXANDO",        pulse: false, bar: true  },
    done:         { icon: "■", label: "CONCLUIDO!",      pulse: false, bar: true  },
    error:        { icon: "✖", label: "ERRO",            pulse: false, bar: false },
  };
  const p = phases[phase] || phases.connecting;
  const pctVal = pct !== null ? Math.round(pct) : 0;

  btn.innerHTML = `
    <span class="progress-wrap">
      <span class="progress-icon ${p.pulse ? "phase-pulse" : ""}">${p.icon}</span>
      <span class="progress-col">
        <span class="progress-label">${p.label}</span>
        ${p.bar
          ? `<span class="progress-bar-outer"><span class="progress-bar-fill" style="width:${pctVal}%"></span></span>`
          : `<span class="progress-dots"><span></span><span></span><span></span></span>`
        }
      </span>
      ${p.bar ? `<span class="progress-pct">${pctVal}%</span>` : ""}
    </span>`;
}

// ── Download via yt-dlp local ────────────────────────────────────────────────
// No desktop: yt-dlp baixa diretamente do YouTube para o disco
// Sem proxy, sem CORS, velocidade total da internet

async function startDownload(btn, format) {
  if (downloading) return;
  downloading = true;
  lockAllButtons(btn);
  renderBtnPhase(btn, "connecting");

  try {
    await new Promise(r => setTimeout(r, 80));

    const ext = format.ext || "mp4";
    const safeTitle = currentTitle
      ? currentTitle.replace(/[\\/:*?"<>|]/g, "").replace(/\s+/g, " ").trim().slice(0, 100)
      : "video";
    const filename = `${safeTitle}.${ext}`;

    renderBtnPhase(btn, "processing");

    // Pede ao usuário onde salvar (dialog nativo do Windows)
    let outputPath;
    if (window.electronAPI) {
      // Electron: abre dialog nativo de "Salvar como"
      const result = await window.electronAPI.saveFile(filename);
      if (!result || result.canceled) {
        throw new Error("canceled");
      }
      outputPath = result.path;
    } else {
      // Fallback browser: usa pasta Downloads padrão
      outputPath = filename;
    }

    renderBtnPhase(btn, "downloading", 0);

    // Inicia o download via API local
    // O yt-dlp baixa direto do YouTube para o outputPath escolhido
    const res = await fetch(`${API}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: currentUrl,
        format_id: format.format_id,
        mode: format.is_audio_only ? "mp3" : "mp4",
        output_path: outputPath,
      }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || "Falha no download");
    }

    renderBtnPhase(btn, "done", 100);
    await new Promise(r => setTimeout(r, 800));

  } catch (err) {
    if (err.message === "canceled") {
      // Usuário cancelou o dialog — não mostra erro
    } else {
      console.error("Download error:", err);
      renderBtnPhase(btn, "error");
      await new Promise(r => setTimeout(r, 800));
      alert("Erro no download: " + err.message);
    }
  } finally {
    unlockAllButtons();
    btn.innerHTML = btn._original;
    btn.disabled = false;
    downloading = false;
  }
}

// ── Analyze ──────────────────────────────────────────────────────────────────

async function analyze() {
  const input = document.getElementById("url");
  const url = input.value.trim();
  const resultDiv = document.getElementById("result");

  if (!url) {
    resultDiv.innerHTML = `<div class="error-box">URL NAO ENCONTRADA. INSIRA UM LINK VALIDO.</div>`;
    return;
  }

  currentUrl = url;
  setLoading(true);
  resultDiv.innerHTML = `
    <div class="loading">
      <div class="pixel-loader">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <p>ANALISANDO...</p>
    </div>`;

  try {
    const res = await fetch(`${API}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      resultDiv.innerHTML = `<div class="error-box">${escapeHtml(data.error || "ERRO")}</div>`;
      return;
    }

    currentTitle = data.title || null;
    renderResult(data);

  } catch (err) {
    resultDiv.innerHTML = `<div class="error-box">FALHA DE CONEXAO COM O SERVIDOR LOCAL.</div>`;
  } finally {
    setLoading(false);
  }
}

function renderResult(data) {
  const resultDiv = document.getElementById("result");
  const duration = formatDuration(data.duration);
  const uploader = data.uploader ? `[ ${escapeHtml(data.uploader)} ]` : "";
  const details = [duration, uploader].filter(Boolean).join("  ");

  const formatsHtml = data.formats.map((f, idx) => {
    const size = formatFilesize(f.filesize);
    const fps = f.fps ? ` ${f.fps}FPS` : "";
    const label = `${f.resolution || "AUTO"}${fps}`;
    const sizeHtml = size ? `<span class="format-size">${size}</span>` : "";

    return `
      <button class="format-btn" data-format-idx="${idx}">
        <span class="format-label">
          <span class="format-badge ${badgeClass(f.ext)}">${f.ext.toUpperCase()}</span>
          <span class="format-resolution">${escapeHtml(label)}</span>
          ${sizeHtml}
        </span>
        <span class="dl-icon">▼</span>
      </button>`;
  }).join("");

  window._currentFormats = data.formats;

  resultDiv.innerHTML = `
    <div class="video-card">
      <div class="video-info">
        ${data.thumbnail ? `<img class="video-thumb" src="${escapeHtml(data.thumbnail)}" alt="thumb" loading="lazy" />` : ""}
        <div class="video-meta">
          <div class="video-title">${escapeHtml(data.title || "SEM TITULO")}</div>
          <div class="video-details">${details}</div>
        </div>
      </div>
      <div class="formats-header">&gt;&gt; SELECT FORMAT TO DOWNLOAD</div>
      <div class="formats-list">${formatsHtml}</div>
    </div>`;

  resultDiv.querySelectorAll(".format-btn").forEach((btn) => {
    btn._original = btn.innerHTML;
    btn.addEventListener("click", () => {
      const format = window._currentFormats[parseInt(btn.dataset.formatIdx)];
      startDownload(btn, format);
    });
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
