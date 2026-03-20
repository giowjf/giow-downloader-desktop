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
  // electron-builder copia python-dist/server/ para resources/python-dist/server/
  const candidates = [
    // Produção (portable .exe)
    path.join(process.resourcesPath, "python-dist", "server", "server.exe"),
    path.join(process.resourcesPath, "python-dist", "server.exe"),
    // Desenvolvimento
    path.join(__dirname, "..", "python-dist", "server", "server.exe"),
    path.join(__dirname, "..", "python-dist", "server.exe"),
  ];

  console.log("[electron] Procurando server.exe em:");
  for (const p of candidates) {
    console.log("  ", p, "->", fs.existsSync(p) ? "EXISTE" : "nao encontrado");
    if (fs.existsSync(p)) return p;
  }
  return null;
}

// ── Inicia o servidor Python local ─────────────────────────────────────────

function startPythonServer() {
  return new Promise((resolve, reject) => {
    const exe = getPythonExe();
    if (!exe) {
      reject(new Error("Servidor Python não encontrado. Reinstale o aplicativo."));
      return;
    }

    console.log("[electron] Iniciando servidor:", exe);
    console.log("[electron] Existe?", fs.existsSync(exe));
    console.log("[electron] resourcesPath:", process.resourcesPath);
    console.log("[electron] __dirname:", __dirname);

    // Lista o conteúdo de python-dist para debug
    const pythonDistPath = path.join(process.resourcesPath, "python-dist");
    if (fs.existsSync(pythonDistPath)) {
      console.log("[electron] python-dist existe:", fs.readdirSync(pythonDistPath));
    } else {
      console.log("[electron] python-dist NÃO existe em:", pythonDistPath);
      // Tenta listar resources
      if (fs.existsSync(process.resourcesPath)) {
        console.log("[electron] resources contém:", fs.readdirSync(process.resourcesPath));
      }
    }

    pythonProcess = spawn(exe, [], {
      env: {
        ...process.env,
        GIOW_PORT: String(API_PORT),
        GIOW_MODE: "desktop",
      },
      windowsHide: false, // mostra console para debug
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
      // Permite fetch para localhost sem CORS
      webSecurity: false,
    },
    autoHideMenuBar: true,
    frame: true,
  });

  mainWindow.loadFile(path.join(__dirname, "index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── IPC — comunicação front ↔ main ────────────────────────────────────────

// Salvar arquivo com dialog nativo do sistema
ipcMain.handle("show-save-dialog", async (event, { filename, buffer }) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: filename,
    filters: [
      { name: "Vídeo MP4", extensions: ["mp4"] },
      { name: "Áudio MP3", extensions: ["mp3"] },
      { name: "Todos os arquivos", extensions: ["*"] },
    ],
  });

  if (result.canceled || !result.filePath) {
    return { success: false, canceled: true };
  }

  try {
    fs.writeFileSync(result.filePath, Buffer.from(buffer));
    return { success: true, path: result.filePath };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

// Retorna a URL da API local
ipcMain.handle("get-api-url", () => API_URL);

// ── Lifecycle ────────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  try {
    await startPythonServer();
    createWindow();
  } catch (err) {
    console.error("[electron] Erro ao iniciar:", err);
    const { dialog } = require("electron");
    const debugInfo = [
      `Erro: ${err.message}`,
      `resourcesPath: ${process.resourcesPath}`,
      `__dirname: ${__dirname}`,
      `Tentou: ${path.join(process.resourcesPath, "python-dist", "server", "server.exe")}`,
    ].join("\n");
    dialog.showErrorBox("Erro ao iniciar GIOW Downloader", debugInfo);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  // Encerra o servidor Python ao fechar
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
  app.quit();
});

app.on("before-quit", () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});
