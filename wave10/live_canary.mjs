import { promises as fs } from "node:fs";
import crypto from "node:crypto";

process.env.PLAYWRIGHT_BROWSERS_PATH = "/ms-playwright";
process.env.DEBUG = "pw:browser";
const { chromium } = await import("playwright");

const workspace = "/tmp/od3b-workspace";
const outDir = workspace + "/out";
const result = {
  schema: "panam-ci-lab.wave10.od3b-live-computer.v1",
  provider: "openshell-playwright",
  playwright_version: "1.63.0",
  privacy_class: "SYNTHETIC",
  shell_capability: false,
  shell_tool_exposed: false,
  command_input_accepted: false,
  credentials_available: false,
  production_mounts_available: false,
  concurrency: 1,
  allowed_origin: "https://example.com",
  browser_navigation_succeeded: false,
  unlisted_origin_denied: false,
  ephemeral_file_written: false,
  screenshot_written: false,
  post_stop_action_denied: false,
  workspace_reset: false,
  browser_closed: false,
  control_plane_invoked: false,
  memory_written: false,
  merge_performed: false,
  deploy_performed: false,
};

const forbiddenEnv = [
  "GITHUB_TOKEN",
  "GH_TOKEN",
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "NVIDIA_API_KEY",
  "GOOGLE_APPLICATION_CREDENTIALS",
];
for (const key of forbiddenEnv) {
  if (process.env[key]) throw new Error("credential environment unexpectedly present: " + key);
}

let stopped = false;
let browser;

function requireActive() {
  if (stopped) throw new Error("computer_stopped");
}

async function stopComputer() {
  if (browser) {
    await browser.close();
    browser = undefined;
    result.browser_closed = true;
  }
  stopped = true;
  await fs.rm(workspace, { recursive: true, force: true });
  try {
    await fs.access(workspace);
    throw new Error("workspace_not_reset");
  } catch (error) {
    if (error && error.code !== "ENOENT") throw error;
  }
  result.workspace_reset = true;
}

try {
  const sourceText = await fs.readFile("/opt/od3b/live_canary.mjs", "utf8");
  result.canary_source_sha256 = crypto.createHash("sha256").update(sourceText).digest("hex");

  await fs.rm(workspace, { recursive: true, force: true });
  await fs.mkdir(outDir, { recursive: true });

  requireActive();
  browser = await chromium.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--no-zygote",
      "--single-process",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-domain-reliability",
      "--disable-sync",
      "--metrics-recording-only",
      "--no-first-run",
      "--disable-default-apps",
      "--disable-client-side-phishing-detection",
      "--disable-breakpad",
      "--disable-features=AutofillServerCommunication,CertificateTransparencyComponentUpdater,OptimizationHints,MediaRouter,Translate",
    ],
  });

  const context = await browser.newContext({ acceptDownloads: false });
  const page = await context.newPage();

  requireActive();
  await page.goto("https://example.com/", {
    waitUntil: "domcontentloaded",
    timeout: 15000,
  });
  const title = await page.title();
  const body = await page.locator("body").innerText();
  if (!title.includes("Example Domain") || !body.includes("Example Domain")) {
    throw new Error("unexpected_allowed_page_content");
  }
  result.browser_navigation_succeeded = true;

  requireActive();
  const screenshotPath = outDir + "/example.png";
  await page.screenshot({ path: screenshotPath, fullPage: false });
  const screenshotStat = await fs.stat(screenshotPath);
  if (screenshotStat.size <= 0) throw new Error("empty_screenshot");
  result.screenshot_written = true;
  result.screenshot_bytes = screenshotStat.size;

  requireActive();
  const summaryPath = outDir + "/summary.txt";
  const summary = "OD-3B public canary: " + title + "\n";
  await fs.writeFile(summaryPath, summary, { encoding: "utf8", flag: "wx" });
  const readBack = await fs.readFile(summaryPath, "utf8");
  if (readBack !== summary) throw new Error("ephemeral_file_roundtrip_mismatch");
  result.ephemeral_file_written = true;
  result.summary_sha256 = crypto.createHash("sha256").update(readBack).digest("hex");

  requireActive();
  try {
    await page.goto("https://www.iana.org/", {
      waitUntil: "domcontentloaded",
      timeout: 8000,
    });
    throw new Error("unlisted_origin_unexpectedly_succeeded");
  } catch (error) {
    if (String(error?.message || error).includes("unlisted_origin_unexpectedly_succeeded")) {
      throw error;
    }
    result.unlisted_origin_denied = true;
  }

  await context.close();
  await stopComputer();

  try {
    requireActive();
  } catch (error) {
    if (String(error?.message || error).includes("computer_stopped")) {
      result.post_stop_action_denied = true;
    } else {
      throw error;
    }
  }

  const required = [
    "browser_navigation_succeeded",
    "unlisted_origin_denied",
    "ephemeral_file_written",
    "screenshot_written",
    "post_stop_action_denied",
    "workspace_reset",
    "browser_closed",
  ];
  for (const key of required) {
    if (result[key] !== true) throw new Error("required_check_failed:" + key);
  }

  process.stdout.write(JSON.stringify(result) + "\n");
} finally {
  if (browser) {
    try { await browser.close(); } catch {}
  }
  await fs.rm(workspace, { recursive: true, force: true });
}
