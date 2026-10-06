import { promises as fs } from "node:fs";

const workspace = "/tmp/od3b-workspace";
const shellPaths = [
  "/bin/sh",
  "/bin/bash",
  "/bin/dash",
  "/usr/bin/sh",
  "/usr/bin/bash",
  "/usr/bin/dash",
];

async function exists(path) {
  try {
    await fs.lstat(path);
    return true;
  } catch (error) {
    if (error && error.code === "ENOENT") return false;
    throw error;
  }
}

for (const path of shellPaths) {
  if (await exists(path)) throw new Error("shell_binary_present:" + path);
}

if (await exists(workspace)) throw new Error("workspace_still_present");

const procEntries = await fs.readdir("/proc", { withFileTypes: true });
const browserProcesses = [];
for (const entry of procEntries) {
  if (!entry.isDirectory() || !/^\d+$/.test(entry.name)) continue;
  try {
    const cmdline = await fs.readFile("/proc/" + entry.name + "/cmdline", "utf8");
    const normalized = cmdline.replaceAll("\0", " ").toLowerCase();
    if (
      normalized.includes("chrome-headless") ||
      normalized.includes("/chrome ") ||
      normalized.includes("/chromium")
    ) {
      browserProcesses.push({ pid: Number(entry.name), cmdline: normalized.slice(0, 240) });
    }
  } catch {}
}

if (browserProcesses.length) {
  throw new Error("browser_process_survived_stop:" + JSON.stringify(browserProcesses));
}

process.stdout.write(JSON.stringify({
  schema: "panam-ci-lab.wave10.od3b-post-stop-probe.v1",
  shell_binaries_absent: true,
  workspace_absent: true,
  browser_processes_absent: true,
}) + "\n");
