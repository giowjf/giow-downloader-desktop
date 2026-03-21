const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

let mainWindow = null;
let pythonProcess = null;
const API_PORT = 5001;
const API_URL = `http://localhost:${API_PORT}`;

// ── Localiza o executável Python bundled ────────────────────────────────────

function getPythonExe() {
  // Em Windows o binário é server.exe, em macOS/Linux é apenas server
  const isWin = process.platform === "win32";
  const exeName = isWin ? "server.exe" : "server";

  // extraResources copia de dist/server/ para resources/server/
  // O executável fica em resources/server/<exeName>
  const candidates = [
    // Produção: resources/server/server[.exe]  ← extraResources
    path.join(process.resourcesPath, "server", exeName),
    // Fallback legado: app.asar.unpacked/server/
    path.join(process.resourcesPath, "app.asar.unpacked", "server", exeName),
    // Desenvolvimento local
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

  // Debug: lista o que existe em resources/
  console.log("[electron] FALHA — listando resources/:");
  try {
    fs.readdirSync(process.resourcesPath).forEach(f =>
      console.log("  resources/", f)
    );
  } catch (e) { console.log("  erro:", e.message); }

  return null;
}

// ── Inicia o servidor Python local ─────────────────────────────────────────

function startPythonServer() {
  return new Promise((resolve, reject) => {
    const exe = getPythonExe();
    if (!exe) {
      // Monta mensagem de debug para o dialog de erro
      let info = [];
      try {
        info.push("resources/ contém:");
        fs.readdirSync(process.resourcesPath).forEach(f => info.push("  " + f));
        const serverDir = path.join(process.resourcesPath, "server");
        if (fs.existsSync(serverDir)) {
          info.push("resources/server/ contém:");
          fs.readdirSync(serverDir).forEach(f => info.push("  " + f));
        } else {
          info.push("resources/server/ NÃO existe");
        }
      } catch (e) {
        info.push("erro ao listar: " + e.message);
      }
      reject(new Error(
        "Servidor Python não encontrado. Reinstale o aplicativo.\n\n" +
        `resourcesPath: ${process.resourcesPath}\n` +
        info.join("\n")
      ));
      return;
    }

    console.log("[electron] Iniciando servidor:", exe);

    // Em macOS/Linux, garante permissão de execução
    if (process.platform !== "win32") {
      try { fs.chmodSync(exe, 0o755); } catch (e) {}
    }

    pythonProcess = spawn(exe, [], {
      env: { ...process.env, GIOW_PORT: String(API_PORT), GIOW_MODE: "desktop" },
      windowsHide: false,
    });

    pythonProcess.stdout.on("data", (d) => console.log("[python]", d.toString().trim()));
    pythonProcess.stderr.on("data", (d) => console.error("[python-err]", d.toString().trim()));
    pythonProcess.on("exit", (code) => console.log("[python] encerrado com código", code));

    // Aguarda o servidor ficar disponível (até 30s)
    const start = Date.now();
    const check = setInterval(() => {
      http.get(`${API_URL}/`, (res) => {
        if (res.statusCode === 200) {
          clearInterval(check);
          console.log("[electron] Servidor Python pronto");
          resolve();
        }
      }).on("error", () => {
        if (Date.now() - start > 30000) {
          clearInterval(check);
          reject(new Error("Servidor Python não respondeu em 30s"));
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
      webSecurity: false, // permite fetch para localhost
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
    console.error("[electron] Erro ao iniciar:", err);
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
