const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("evidenceCopilot", {
  pingSidecar: () => ipcRenderer.invoke("sidecar:ping"),
  getSettings: () => ipcRenderer.invoke("sidecar:get-settings"),
  saveSettings: (params) => ipcRenderer.invoke("sidecar:save-settings", params),
  proposeSearch: (params) => ipcRenderer.invoke("sidecar:propose", params),
  runPubmedSearch: (params) => ipcRenderer.invoke("sidecar:run-pubmed", params),
  updateScreening: (params) => ipcRenderer.invoke("sidecar:update-screening", params),
  exportProject: (params) => ipcRenderer.invoke("sidecar:export", params),
  saveFile: (params) => ipcRenderer.invoke("file:save", params),
  sendPiPrompt: (message) => ipcRenderer.invoke("pi:prompt", message),
  sendPiUiResponse: (payload) => ipcRenderer.invoke("pi:ui-response", payload),
  onPiEvent: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("pi:event", listener);
    return () => ipcRenderer.removeListener("pi:event", listener);
  },
  getPaths: () => ipcRenderer.invoke("app:paths"),
});
