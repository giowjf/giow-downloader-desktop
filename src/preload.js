const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  // Abre dialog de "Salvar como" e retorna o path escolhido pelo usuário.
  // O Flask é quem grava o arquivo nesse path via yt-dlp.
  saveFile: (filename) =>
    ipcRenderer.invoke("show-save-dialog", { filename }),

  // Retorna a URL da API local (http://127.0.0.1:5001)
  getApiUrl: () => ipcRenderer.invoke("get-api-url"),

  // Indica que está rodando no Electron (não no browser)
  isDesktop: true,
});
