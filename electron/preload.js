/**
 * electron/preload.js
 * ─────────────────────────────────────────────
 * Runs in the renderer before any page scripts.
 * Exposes a minimal API via contextBridge so the React app can detect
 * that it's running inside Electron.
 */

const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("electron", {
  isDesktop: true,
});
