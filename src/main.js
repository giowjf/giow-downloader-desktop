const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");
const os = require("os");

let mainWindow = null;
let pythonProcess = null;
const API_PORT = 5001;
const API_URL = `http://localhost:${API_PORT}`;
const LOG_PATH = path.join(os.tmpdir(), "giow-server.log");

// ── Localiza o executável Python bundled ────────────────────────────────────

function getPythonExe() {
  const isWin = process.platform === "win32";
  const exeName = isWin ? "server.exe" : "server";

  // extraResources copia server/ → resources/server/
  const candidates = [
    path.join(process.resourcesPath, "server", exeName),
    path.join(process.resourcesPath, "app.asar.unpacked", "server", exeName),
    path.join(__dirname, "..", "server", exeName),
    path.join(__dirname, "..", "python-dist", "server", exeName),
  ];

  console.log(`[electron] Plataforma: ${process.platform}`);
  console.log(`[electron] Procurando ${exeName} em:`);
  for (const p of candidates) {
    const exists = fs.existsSync(p);
    console.log("  ", p, "->", exists ? "EXISTE" : "nao encontrado");
    if (exists) return p;
  }
  return null;
}

// ── Lê o log do servidor Python (para debug no dialog de erro) ──────────────

function readServerLog() {
  try {
    if (fs.existsSync(LOG_PATH)) {
      const content = fs.readFileSync(LOG_PATH, "utf-8");
      // Retorna as últimas 30 linhas
      const lines = content.trim().split("\n");
      return lines.slice(-30).join("\n");
    }
  } catch (e) {}
  return "(log não disponível)";
}

// ── Inicia o servidor Python local ─────────────────────────────────────────

function startPythonServer() {
  return new Promise((resolve, reject) => {
    // Limpa log anterior
    try { fs.unlinkSync(LOG_PATH); } catch (e) {}

    const exe = getPythonExe();
    if (!exe) {
      let info = [`resourcesPath: ${process.resourcesPath}`];
      try {
        info.push("resources/ contém:");
        fs.readdirSync(process.resourcesPath).forEach(f => info.push("  " + f));
        const s = path.join(process.resourcesPath, "server");
        if (fs.existsSync(s)) {
          info.push("resources/server/ contém:");
          fs.readdirSync(s).forEach(f => info.push("  " + f));
        } else {
          info.push("resources/server/ NÃO existe");
        }
      } catch (e) { info.push("erro: " + e.message); }
      reject(new Error("server.exe não encontrado\n\n" + info.join("\n")));
      return;
    }

    console.log("[electron] Iniciando servidor:", exe);

    if (process.platform !== "win32") {
      try { fs.chmodSync(exe, 0o755); } catch (e) {}
    }

    pythonProcess = spawn(exe, [], {
      env: { ...process.env, GIOW_PORT: String(API_PORT), GIOW_MODE: "desktop" },
      windowsHide: false,
    });

    let crashed = false;
    let stdoutBuf = "";
    let stderrBuf = "";

    pythonProcess.stdout.on("data", (d) => {
      const s = d.toString();
      stdoutBuf += s;
      console.log("[python]", s.trim());
    });
    pythonProcess.stderr.on("data", (d) => {
      const s = d.toString();
      stderrBuf += s;
      console.error("[python-err]", s.trim());
    });

    // Rejeita imediatamente se o processo morrer antes do servidor subir
    pythonProcess.on("exit", (code) => {
      console.log("[python] encerrado com código", code);
      if (!crashed) {
        crashed = true;
        clearInterval(checkInterval);
        const log = readServerLog();
        reject(new Error(
          `Servidor Python encerrou com código ${code}\n\n` +
          `Log (${LOG_PATH}):\n${log}\n\n` +
          `stderr:\n${stderrBuf.slice(-500) || "(vazio)"}`
        ));
      }
    });

    // Aguarda o servidor ficar disponível (até 30s)
    const start = Date.now();
    const checkInterval = setInterval(() => {
      if (crashed) return;
      http.get(`${API_URL}/`, (res) => {
        if (res.statusCode === 200) {
          clearInterval(checkInterval);
          console.log("[electron] Servidor Python pronto");
          resolve();
        }
      }).on("error", () => {
        if (Date.now() - start > 30000) {
          clearInterval(checkInterval);
          if (!crashed) {
            crashed = true;
            const log = readServerLog();
            reject(new Error(
              `Servidor Python não respondeu em 30s\n\n` +
              `Log (${LOG_PATH}):\n${log}`
            ));
          }
        }
      });
    }, 500);
  });
}

// ── Cria a janela principal ─────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 780,
    height: 680,
    minWidth: 600,
    minHeight: 500,
    title: "GIOW Downloader",
    backgroundColor: "#0a0a0a",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
    autoHideMenuBar: true,
    frame: true,
  });

  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.on("closed", () => { mainWindow = null; });
}

// ── IPC ────────────────────────────────────────────────────────────────────

ipcMain.handle("show-save-dialog", async (event, { filename, buffer }) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: filename,
    filters: [
      { name: "Vídeo MP4", extensions: ["mp4"] },
      { name: "Áudio MP3", extensions: ["mp3"] },
      { name: "Todos os arquivos", extensions: ["*"] },
    ],
  });
  if (result.canceled || !result.filePath) return { success: false, canceled: true };
  try {
    fs.writeFileSync(result.filePath, Buffer.from(buffer));
    return { success: true, path: result.filePath };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle("get-api-url", () => API_URL);

// ── Lifecycle ────────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  try {
    await startPythonServer();
    createWindow();
  } catch (err) {
    console.error("[electron] Erro ao iniciar:", err.message);
    dialog.showErrorBox("Erro ao iniciar GIOW Downloader", err.message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (pythonProcess) { pythonProcess.kill(); pythonProcess = null; }
  app.quit();
});

app.on("before-quit", () => {
  if (pythonProcess) { pythonProcess.kill(); }
});
