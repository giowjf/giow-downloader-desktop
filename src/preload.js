const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  // Abre dialog de salvar arquivo e grava no disco
  saveFile: (filename, buffer) =>
    ipcRenderer.invoke("show-save-dialog", { filename, buffer }),

  // Retorna a URL da API local
  getApiUrl: () => ipcRenderer.invoke("get-api-url"),

  // Indica que está rodando no Electron (não no browser)
  isDesktop: true,
});
