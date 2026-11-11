"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("vicoraDesktop", {
  connect: (address) => ipcRenderer.invoke("gtmc:connect", address)
});
