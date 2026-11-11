const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const net = require("net");

let mainWindow = null;
let connectedOrigin = null;

function normalizeServerAddress(input) {
  const value = String(input || "").trim();
  if (!value) throw new Error("Enter the school server address.");
  let parsed;
  try {
    parsed = new URL(value.includes("://") ? value : "http://" + value);
  } catch {
    throw new Error("Enter a valid address, for example http://127.0.0.1:8000");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname ||
      parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("Use a complete HTTP or HTTPS server address.");
  }
  const host = parsed.hostname.toLowerCase();
  const ipVersion = net.isIP(host);
  const loopback = host === "localhost" || host === "::1" || host === "127.0.0.1";
  const privateV4 = ipVersion === 4 && (
    host.startsWith("10.") || host.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) || host.startsWith("169.254.")
  );
  const localName = host.endsWith(".local") || host.endsWith(".lan");
  if (parsed.protocol === "http:" && !(loopback || privateV4 || localName)) {
    throw new Error("For a remote server, use HTTPS. The Admin portal is normally opened on the server computer.");
  }
  return parsed.origin;
}

async function verifyServer(origin) {
  let response;
  try {
    response = await fetch(origin + "/api/health", { signal: AbortSignal.timeout(6000) });
  } catch {
    throw new Error("The CBT server did not respond. Check that it is running on this computer.");
  }
  if (!response.ok) throw new Error("The CBT server health check failed (HTTP " + response.status + ").");
  const payload = await response.json().catch(() => null);
  if (!payload || payload.ok !== true || payload.service !== "gtmc-cbt") {
    throw new Error("This address is not reporting a ready GTMC CBT server.");
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240, height: 900, minWidth: 900, minHeight: 650,
    title: "GTMC CBT Administration",
    autoHideMenuBar: true, backgroundColor: "#f3f7fc",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true, nodeIntegration: false, sandbox: true
    }
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-navigate", (event, target) => {
    try {
      if (connectedOrigin && new URL(target).origin !== connectedOrigin) event.preventDefault();
    } catch { event.preventDefault(); }
  });
  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.on("closed", () => { mainWindow = null; connectedOrigin = null; });
}

ipcMain.handle("gtmc-admin:connect", async (_event, rawAddress) => {
  try {
    const origin = normalizeServerAddress(rawAddress);
    await verifyServer(origin);
    connectedOrigin = origin;
    await mainWindow.loadURL(origin + "/admin");
    return { ok: true };
  } catch (error) {
    return { ok: false, message: error.message || String(error) };
  }
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
