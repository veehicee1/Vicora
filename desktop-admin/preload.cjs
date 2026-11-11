"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("vicoraAdminDesktop", {
  host: () => ipcRenderer.invoke("vicora-admin:host"),
  connect: (address) => ipcRenderer.invoke("vicora-admin:connect", address)
});
