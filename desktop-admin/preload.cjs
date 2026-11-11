const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("gtmcAdminDesktop", {
  connect: (address) => ipcRenderer.invoke("gtmc-admin:connect", address)
});
