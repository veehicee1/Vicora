const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const os = require("os");
const fs = require("fs");
const net = require("net");
const { spawn } = require("child_process");

let mainWindow = null;
let connectedOrigin = null;
let hostProcess = null;

function normalizeServerAddress(input) {
  const value = String(input || "").trim();
  if (!value) throw new Error("Enter the school server address.");
  let parsed;
  try {
    parsed = new URL(value.includes("://") ? value : "http://" + value);
  } catch {
    throw new Error("Enter a valid address, for example http://192.168.1.20:8000");
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
    throw new Error("For internet access, use a trusted HTTPS school address. HTTP is allowed only on a private school LAN.");
  }
  parsed.pathname = parsed.pathname.replace(/\/+$/, "") + "/";
  return parsed.toString();
}

async function verifyServer(address) {
  let response;
  try {
    response = await fetch(new URL("api/health", address), { signal: AbortSignal.timeout(6000) });
  } catch {
    throw new Error("The VICORA CBT host did not respond. Check the server computer and network.");
  }
  if (!response.ok) throw new Error("The host health check failed (HTTP " + response.status + ").");
  const payload = await response.json().catch(() => null);
  if (!payload || payload.ok !== true || payload.service !== "gtmc-cbt") {
    throw new Error("This address is not reporting a ready VICORA CBT host.");
  }
}

function serverExecutable() {
  if (app.isPackaged) return path.join(process.resourcesPath, "server", "VICORA-CBT-Server.exe");
  return path.resolve(__dirname, "../dist/VICORA-CBT-Server.exe");
}

function schoolLanLinks() {
  const links = [];
  for (const records of Object.values(os.networkInterfaces())) {
    for (const item of records || []) {
      if (item.family === "IPv4" && !item.internal && !item.address.startsWith("169.254.")) {
        links.push("http://" + item.address + ":8000/");
      }
    }
  }
  return [...new Set(links)].sort();
}

async function waitForLocalHost(logPath) {
  const address = "http://127.0.0.1:8000/";
  const deadline = Date.now() + 45000;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      await verifyServer(address);
      return address;
    } catch (error) {
      lastError = error;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }
  let detail = "";
  try { detail = fs.readFileSync(logPath, "utf8").slice(-2500); } catch {}
  throw new Error("VICORA Windows Host did not become ready. " +
    (lastError ? lastError.message : "") + (detail ? "\n\nHost log:\n" + detail : ""));
}

async function startLocalHost() {
  const address = "http://127.0.0.1:8000/";
  try {
    await verifyServer(address);
    return { address, alreadyRunning: true, studentLinks: schoolLanLinks() };
  } catch {}

  if (process.platform !== "win32") {
    throw new Error("The bundled Windows Host can only run on Windows.");
  }
  const executable = serverExecutable();
  if (!fs.existsSync(executable)) {
    throw new Error("The VICORA CBT Server component is missing. Reinstall the Admin app or use the Windows Host installer.");
  }

  const logPath = path.join(app.getPath("userData"), "windows-host.log");
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
  const logFd = fs.openSync(logPath, "a");
  try {
    hostProcess = spawn(executable, [], {
      detached: true,
      windowsHide: true,
      stdio: ["ignore", logFd, logFd],
      env: { ...process.env }
    });
    hostProcess.unref();
  } finally {
    fs.closeSync(logFd);
  }

  const readyAddress = await waitForLocalHost(logPath);
  return { address: readyAddress, alreadyRunning: false, studentLinks: schoolLanLinks() };
}

function openAdmin(address) {
  connectedOrigin = new URL(address).origin;
  return mainWindow.loadURL(new URL("admin", address).toString());
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240, height: 900, minWidth: 900, minHeight: 650,
    title: "VICORA CBT Administration",
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

ipcMain.handle("vicora-admin:host", async () => {
  try {
    const result = await startLocalHost();
    await openAdmin(result.address);
    return { ok: true, ...result };
  } catch (error) {
    return { ok: false, message: error.message || String(error) };
  }
});

ipcMain.handle("vicora-admin:connect", async (_event, rawAddress) => {
  try {
    const address = normalizeServerAddress(rawAddress);
    await verifyServer(address);
    await openAdmin(address);
    return { ok: true };
  } catch (error) {
    return { ok: false, message: error.message || String(error) };
  }
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
