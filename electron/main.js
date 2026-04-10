/**
 * electron/main.js
 * ─────────────────────────────────────────────
 * Electron main process for PakuPaku desktop app.
 *
 * Responsibilities:
 *   1. Spawn the PyInstaller backend executable
 *   2. Read PAKUPAKU_PORT=<port> from its stdout
 *   3. Wait until the HTTP server is ready
 *   4. Open a BrowserWindow pointing at http://127.0.0.1:<port>
 *   5. Kill the backend when the app quits
 */

const { app, BrowserWindow, dialog } = require("electron");
const path   = require("path");
const { spawn } = require("child_process");
const http   = require("http");
const fs     = require("fs");

// ── Globals ───────────────────────────────────────────────────────────────────
let mainWindow  = null;
let backendProc = null;
let backendPort = null;

// ── Paths ─────────────────────────────────────────────────────────────────────
// In a packaged app, extraResources are copied to <app>/Contents/Resources (mac)
// or <app>/resources (win/linux).
function getBackendExecutable() {
  const resourcesPath = process.resourcesPath || path.join(__dirname, "..");
  const execName = process.platform === "win32"
    ? "pakupaku-backend.exe"
    : "pakupaku-backend";
  return path.join(resourcesPath, "backend", "pakupaku-backend", execName);
}

// ── Wait for server to accept connections ─────────────────────────────────────
function waitForServer(port, retries = 40, delayMs = 250) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/docs`, (res) => {
        resolve(port);
      });
      req.on("error", () => {
        attempts++;
        if (attempts >= retries) {
          reject(new Error(`Backend did not start on port ${port} after ${retries} attempts`));
        } else {
          setTimeout(check, delayMs);
        }
      });
      req.setTimeout(200, () => req.destroy());
    };
    check();
  });
}

// ── Spawn backend ─────────────────────────────────────────────────────────────
function spawnBackend() {
  return new Promise((resolve, reject) => {
    const exePath  = getBackendExecutable();
    const userData = app.getPath("userData");

    if (!fs.existsSync(exePath)) {
      reject(new Error(`Backend executable not found:\n${exePath}`));
      return;
    }

    backendProc = spawn(exePath, [], {
      env: {
        ...process.env,
        PAKUPAKU_USER_DATA: userData,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    backendProc.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      const match = text.match(/PAKUPAKU_PORT=(\d+)/);
      if (match && !backendPort) {
        backendPort = parseInt(match[1], 10);
        resolve(backendPort);
      }
    });

    backendProc.stderr.on("data", (chunk) => {
      console.error("[backend stderr]", chunk.toString());
    });

    backendProc.on("error", reject);

    backendProc.on("exit", (code) => {
      console.log(`[backend] exited with code ${code}`);
      if (!backendPort) reject(new Error("Backend exited before printing port"));
    });

    // Timeout safety: reject after 15 seconds
    setTimeout(() => {
      if (!backendPort) reject(new Error("Backend startup timed out (no port printed)"));
    }, 15_000);
  });
}

// ── Create window ─────────────────────────────────────────────────────────────
function createWindow(port) {
  mainWindow = new BrowserWindow({
    width:  1200,
    height: 800,
    minWidth:  800,
    minHeight: 600,
    title: "PakuPaku",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,
    },
    // Show window icon on Windows/Linux
    // icon: path.join(__dirname, "resources", "icon.png"),
  });

  mainWindow.loadURL(`http://127.0.0.1:${port}`);

  // Remove default menu bar in production
  if (!process.env.PAKU_DEV) mainWindow.setMenuBarVisibility(false);

  mainWindow.on("closed", () => { mainWindow = null; });
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  try {
    const port = await spawnBackend();
    await waitForServer(port);
    createWindow(port);
  } catch (err) {
    dialog.showErrorBox("PakuPaku failed to start", err.message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (!mainWindow && backendPort) createWindow(backendPort);
});

app.on("will-quit", () => {
  if (backendProc) {
    backendProc.kill();
    backendProc = null;
  }
});
