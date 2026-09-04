const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");
const { spawn } = require("node:child_process");
const readline = require("node:readline");

/** @type {import('child_process').ChildProcessWithoutNullStreams | null} */
let piProcess = null;
/** @type {import('readline').Interface | null} */
let piReader = null;
/** @type {Map<string, {resolve: Function, reject: Function}>} */
const pendingPi = new Map();
let reqCounter = 0;

function repoRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "repo");
  }
  return path.resolve(__dirname, "..", "..");
}

function pythonCommand() {
  return process.env.EVIDENCE_COPILOT_PYTHON || "python3";
}

function runSidecar(command, params) {
  return new Promise((resolve, reject) => {
    const root = repoRoot();
    const args = ["-m", "src.sidecar", "--command", command, "--params", JSON.stringify(params || {})];
    const child = spawn(pythonCommand(), args, {
      cwd: root,
      env: { ...process.env, PYTHONPATH: root, EVIDENCE_COPILOT_ROOT: root },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `侧车退出码 ${code}`));
        return;
      }
      try {
        const payload = JSON.parse(stdout.trim());
        if (!payload.ok) {
          reject(new Error(payload.error || "侧车失败"));
          return;
        }
        resolve(payload.result);
      } catch (err) {
        reject(new Error(`侧车 JSON 解析失败：${String(err)}`));
      }
    });
  });
}

function ensurePiRpc() {
  if (piProcess && !piProcess.killed) {
    return;
  }
  const root = repoRoot();
  const piBin = process.env.PI_BIN || "pi";
  piProcess = spawn(
    piBin,
    ["--mode", "rpc", "--no-session", "--name", "Evidence Copilot"],
    {
      cwd: root,
      env: {
        ...process.env,
        EVIDENCE_COPILOT_ROOT: root,
        EVIDENCE_COPILOT_PYTHON: pythonCommand(),
      },
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  piReader = readline.createInterface({ input: piProcess.stdout });
  piReader.on("line", (line) => {
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      return;
    }
    if (event.type === "response" && event.id && pendingPi.has(event.id)) {
      const pending = pendingPi.get(event.id);
      pendingPi.delete(event.id);
      if (event.success) {
        pending.resolve(event);
      } else {
        pending.reject(new Error(event.error || "Pi RPC 命令失败"));
      }
      return;
    }
    const win = BrowserWindow.getAllWindows()[0];
    if (win) {
      win.webContents.send("pi:event", event);
    }
  });
  piProcess.stderr.on("data", (chunk) => {
    console.error("[pi]", chunk.toString());
  });
  piProcess.on("close", () => {
    piProcess = null;
    piReader = null;
  });
}

function sendPiRaw(payload) {
  ensurePiRpc();
  return new Promise((resolve, reject) => {
    piProcess.stdin.write(`${JSON.stringify(payload)}\n`, (err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve({ ok: true });
    });
  });
}

function sendPiCommand(payload) {
  ensurePiRpc();
  return new Promise((resolve, reject) => {
    const id = `ec-${++reqCounter}`;
    pendingPi.set(id, { resolve, reject });
    piProcess.stdin.write(`${JSON.stringify({ ...payload, id })}\n`, (err) => {
      if (err) {
        pendingPi.delete(id);
        reject(err);
      }
    });
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 820,
    title: "Evidence Copilot",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (piProcess && !piProcess.killed) {
    piProcess.kill();
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

ipcMain.handle("sidecar:ping", async () => runSidecar("ping", {}));

ipcMain.handle("sidecar:get-settings", async () => runSidecar("get_settings", {}));

ipcMain.handle("sidecar:save-settings", async (_event, params) => runSidecar("save_settings", params));

ipcMain.handle("sidecar:propose", async (_event, params) => runSidecar("propose_search", params));

ipcMain.handle("sidecar:run-pubmed", async (_event, params) =>
  runSidecar("run_pubmed_search", { ...params, approved: true }),
);

ipcMain.handle("sidecar:update-screening", async (_event, params) =>
  runSidecar("update_screening", params),
);

ipcMain.handle("sidecar:export", async (_event, params) => runSidecar("export_project", params));

ipcMain.handle("pi:prompt", async (_event, message) => {
  await sendPiCommand({ type: "prompt", message });
  return { ok: true };
});

ipcMain.handle("pi:ui-response", async (_event, payload) => sendPiRaw(payload));

ipcMain.handle("file:save", async (_event, { filename, content }) => {
  const win = BrowserWindow.getFocusedWindow();
  const result = await dialog.showSaveDialog(win, { defaultPath: filename });
  if (result.canceled || !result.filePath) {
    return { ok: false, cancelled: true };
  }
  await fs.writeFile(result.filePath, content, "utf8");
  return { ok: true, path: result.filePath };
});

ipcMain.handle("app:paths", async () => ({
  repoRoot: repoRoot(),
  dataHint: "~/Library/Application Support/EvidenceCopilot",
}));
