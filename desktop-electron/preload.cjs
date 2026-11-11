"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("gtmcDesktop", {
  connect: (address) => ipcRenderer.invoke("gtmc:connect", address)
});
