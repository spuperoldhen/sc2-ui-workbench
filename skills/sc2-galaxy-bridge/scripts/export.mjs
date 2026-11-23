import { mkdir, readFile, realpath, stat, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { extname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const usage = "node export.mjs --workbench index.html --project project.json --out NEW_DIR [--components SOURCE_DIR] [--browser msedge|chrome|CHROMIUM_PATH]";

async function main() {
  const { values } = parseArgs({ options: {
    workbench: { type: "string" }, project: { type: "string" },
    out: { type: "string" }, components: { type: "string" },
    browser: { type: "string" }, help: { type: "boolean" },
  } });
  if (values.help) {
    console.log(usage);
    return;
  }
  if (!values.workbench || !values.project || !values.out) throw new Error(usage);
  const workbench = await realpath(values.workbench);
  if (extname(workbench).toLowerCase() !== ".html") throw new Error("--workbench must be a local HTML file");
  if ((await stat(values.project)).size > 24 * 1024 ** 2) throw new Error("Project JSON exceeds 24 MiB");
  const project = JSON.parse((await readFile(values.project, "utf8")).replace(/^\uFEFF/, ""));
  const components = values.components && await realpath(values.components);
  if (components && !(await stat(components)).isDirectory()) throw new Error("--components must be a directory");
  const require = createRequire(join(process.cwd(), "package.json"));
  const { chromium } = require("playwright");
  const out = resolve(values.out);
  await mkdir(out);
  const localUrl = pathToFileURL(workbench);
  localUrl.searchParams.set("localAgent", "1");
  const launch = ["msedge", "chrome"].includes(values.browser)
    ? { channel: values.browser }
    : values.browser ? { executablePath: await realpath(values.browser) } : {};
  const browser = await chromium.launch(launch);
  try {
    const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: "block" });
    await context.route(/^https?:\/\//, (route) => route.abort());
    const page = await context.newPage();
    await page.goto(localUrl.href);
    const api = await page.evaluate(() => ({
      apiVersion: window.SC2WorkbenchAutomation?.apiVersion,
      version: window.SC2WorkbenchAutomation?.version,
    }));
    if (api.apiVersion !== 1) throw new Error("Use Workbench v1.0.2 or a later compatible release");
    if (components) {
      await page.evaluate(() => {
        const input = document.createElement("input");
        input.type = "file";
        input.webkitdirectory = true;
        input.id = "localAgentComponents";
        input.hidden = true;
        document.body.append(input);
      });
      await page.locator("#localAgentComponents").setInputFiles(components);
    }
    const diagnostics = await page.evaluate(async (source) => {
      const files = Array.from(document.querySelector("#localAgentComponents")?.files ?? []);
      const result = await window.SC2WorkbenchAutomation.exportProject(source, files);
      window.localAgentArchive = result.archive;
      return result.diagnostics;
    }, project);
    await writeFile(join(out, "export-diagnostics.json"), JSON.stringify({ ...api, ...diagnostics }, null, 2) + "\n");
    if (!diagnostics.ready) throw new Error("Export blocked. Review export-diagnostics.json");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.evaluate(() => window.SC2WorkbenchAutomation.downloadArchive(window.localAgentArchive)),
    ]);
    const archive = join(out, "sc2-ui-return.zip");
    await download.saveAs(archive);
    console.log(archive);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
