const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const net = require("net");

// Fixed-purpose CBT client: disable browser background services not used by exams.
// Foreground LAN requests and normal Chromium rendering remain enabled.
app.commandLine.appendSwitch("disable-background-networking");
app.commandLine.appendSwitch("disable-component-update");
app.commandLine.appendSwitch("disable-sync");
app.commandLine.appendSwitch("disable-default-apps");
app.commandLine.appendSwitch("no-first-run");

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

  if (!["http:", "https:"].includes(parsed.protocol) ||
      !parsed.hostname || parsed.username || parsed.password ||
      parsed.search || parsed.hash) {
    throw new Error("Use a complete HTTP or HTTPS server address without a username or password.");
  }

  const host = parsed.hostname.toLowerCase();
  const ipVersion = net.isIP(host);
  const loopback = host === "localhost" || host === "::1" || host === "127.0.0.1";
  const privateV4 = ipVersion === 4 && (
    host.startsWith("10.") ||
    host.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
    host.startsWith("169.254.")
  );
  const localName = host.endsWith(".local") || host.endsWith(".lan");

  if (parsed.protocol === "http:" && !(loopback || privateV4 || localName)) {
    throw new Error("For a remote school server, use HTTPS. HTTP is allowed only on the school LAN.");
  }

  parsed.pathname = parsed.pathname.replace(/\/+$/, "") + "/";
  return parsed.toString();
}

async function verifyServer(address) {
  const healthUrl = new URL("api/health", address);
  let response;
  try {
    response = await fetch(healthUrl, { signal: AbortSignal.timeout(6000) });
  } catch (error) {
    throw new Error("The school server did not respond. Check that it is running and that the address is correct.");
  }

  if (!response.ok) throw new Error("The school server health check failed (HTTP " + response.status + ").");
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The address responded, but it is not the GTMC CBT server.");
  }
  if (payload.ok !== true || payload.service !== "gtmc-cbt") {
    throw new Error("This address is not reporting a ready GTMC CBT server.");
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 860,
    minWidth: 850,
    minHeight: 620,
    title: "GTMC CBT Examination",
    autoHideMenuBar: true,
    backgroundColor: "#f3f7fc",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // Keep Chromium background tab throttling enabled.
      backgroundThrottling: true
    }
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-navigate", (event, target) => {
    if (connectedOrigin && new URL(target).origin !== connectedOrigin) {
      event.preventDefault();
    }
  });

  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
    connectedOrigin = null;
  });
}

ipcMain.handle("gtmc:connect", async (_event, rawAddress) => {
  try {
    const address = normalizeServerAddress(rawAddress);
    await verifyServer(address);
    connectedOrigin = new URL(address).origin;
    await mainWindow.loadURL(address);
    return { ok: true };
  } catch (error) {
    return { ok: false, message: error.message || String(error) };
  }
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
