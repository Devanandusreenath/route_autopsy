/**
 * Browser end-to-end checks of the REAL UI against the REAL backend (and the demo build separately).
 *
 *   scripts/stack.sh start stub        # from repo root: backend + local stub provider + UI on :5180 (backend) / :5181 (demo)
 *   cd frontend/e2e && npm install && npm test
 *
 * Env: UI_URL (default http://127.0.0.1:5180), DEMO_URL (5181), API_URL (8000), CHROME_PATH (use a system Chrome instead of the bundled one),
 *      SHOTS (screenshot dir). The vision provider is the LOCAL STUB (labelled [STUB]) unless a real Meta credential is configured.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const here = path.dirname(fileURLToPath(import.meta.url));
const UI = process.env.UI_URL ?? "http://127.0.0.1:5180";
const DEMO = process.env.DEMO_URL ?? "http://127.0.0.1:5181";
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const SHOTS = process.env.SHOTS ?? path.join(here, "screenshots");
fs.mkdirSync(SHOTS, { recursive: true });

async function launch() {
  const args = ["--no-sandbox", "--disable-gpu", "--window-size=1366,1000"];
  if (process.env.CHROME_PATH) return puppeteer.launch({ executablePath: process.env.CHROME_PATH, args, headless: true });
  const { default: chromium } = await import("@sparticuz/chromium");
  return puppeteer.launch({ args: [...chromium.args, ...args], executablePath: await chromium.executablePath(), headless: "shell" });
}

const results = [];
async function test(name, fn) {
  const t = Date.now();
  try { await fn(); results.push({ name, ok: true, ms: Date.now() - t }); console.log(`  PASS  ${name} (${Date.now() - t} ms)`); }
  catch (e) { results.push({ name, ok: false, err: e }); console.log(`  FAIL  ${name}\n        ${String(e.message).split("\n").join("\n        ")}`); }
}
const assert = (c, m) => { if (!c) throw new Error(m); };
const eq = (a, b, m) => assert(a === b, `${m}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
const api = async (p, body) => (await fetch(API + p, body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : undefined)).json();

const browser = await launch();
const consoleErrors = [];
/** A copy of the fixture with unique trailing bytes (after the JPEG end marker) => unique SHA-256 => never a duplicate by accident. */
function uniqueImage(tag) {
  const p = path.join(here, "fixtures", `road-${tag}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.jpg`);
  fs.writeFileSync(p, Buffer.concat([fs.readFileSync(path.join(here, "fixtures", "road.jpg")), Buffer.from(`\nunique:${Math.random()}`)]));
  return p;
}
async function newPage(url, { width = 1366, height = 1000, expectErrors = false } = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width, height });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() !== "error" || expectErrors) return;
    const t = m.text();
    if (/tile\.openstreetmap|ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED|ERR_CONNECTION|Failed to load resource.*(tile|favicon)/i.test(t)) return; // sandbox has no internet for map tiles
    consoleErrors.push(`console.error: ${t}`);
  });
  await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
  return page;
}
const text = (page, sel) => page.$eval(sel, (e) => e.textContent ?? "");
const clickButton = async (page, label) => {
  const ok = await page.evaluate((l) => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent?.trim().startsWith(l) && !x.disabled); if (b) { b.click(); return true; } return false; }, label);
  assert(ok, `no enabled button starting with "${label}"`);
};
const waitText = (page, re, timeout = 30000) => page.waitForFunction((s, f) => new RegExp(s, f).test(document.body.innerText), { timeout }, re.source, re.flags);
async function pick(page, sel, value) { await page.waitForSelector(`${sel} option[value="${value}"]`, { timeout: 20000 }); await page.select(sel, value); }
const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
const count = (page, sel) => page.$$eval(sel, (e) => e.length);

console.log(`\nUI (backend mode): ${UI}   API: ${API}   Demo UI: ${DEMO}\n`);

// ------------------------------------------------------------------------------------------------ mode labelling
await test("backend mode is clearly labelled and never says demo", async () => {
  const page = await newPage(UI);
  const body = await page.evaluate(() => document.body.innerText);
  assert(body.includes(`BACKEND · ${API}`), "mode indicator should show the backend URL");
  assert(!/DEMO MODE|synthetic data/i.test(body), "backend mode must not show demo labels");
  await page.close();
});

await test("demo mode is a separate, clearly labelled mode and makes NO backend calls", async () => {
  const page = await browser.newPage();
  const hits = [];
  page.on("request", (r) => { if (r.url().startsWith(API)) hits.push(r.url()); });
  await page.setViewport({ width: 1366, height: 1000 });
  await page.goto(DEMO + "/", { waitUntil: "networkidle2", timeout: 60000 });
  assert(/DEMO MODE · synthetic data/.test(await page.evaluate(() => document.body.innerText)), "demo banner missing");
  await pick(page, "#origin", "N1"); await pick(page, "#dest", "N3");
  await clickButton(page, "Investigate route");
  await waitText(page, /Synthetic example/);
  assert(/synthetic/i.test(await page.evaluate(() => document.body.innerText)), "result should be labelled synthetic");
  await shot(page, "07-demo-mode");
  eq(hits.length, 0, "demo mode must not call the backend");
  await page.close();
});

// ------------------------------------------------------------------------------------------------ route page + map
await test("route investigation: map, alternatives, defect + restriction markers, rejection reasons", async () => {
  const page = await newPage(UI);
  await pick(page, "#origin", "FKC"); await pick(page, "#dest", "ALV"); await pick(page, "#veh", "veh-ecomet");
  await page.waitForSelector('[data-testid="restriction-panel"]', { timeout: 20000 });
  await clickButton(page, "Investigate route");
  await page.waitForSelector('[data-testid="route-map"][data-ready="true"]', { timeout: 20000 });
  await waitText(page, /alternatives shown/i);
  const expected = await api("/routes/investigate", { origin: "FKC", destination: "ALV", vehicleId: "veh-ecomet" });
  await page.waitForFunction((n) => document.querySelectorAll("path.route-line").length >= n, { timeout: 15000 }, expected.alternatives.length);
  const lines = await count(page, "path.route-line");
  eq(lines, expected.alternatives.length, "one polyline per alternative on the map");
  eq(await count(page, "path.route-recommended"), 1, "exactly one recommended line");
  assert((await count(page, "path.route-rejected")) >= 1, "rejected (unsuitable) routes are drawn");
  const defects = (await api("/defects")).filter((d) => d.maintenanceStatus !== "resolved").length;
  eq(await count(page, "path.marker-defect"), defects, "defect markers = unresolved defects from the API");
  eq(await count(page, "path.marker-restriction"), (await api("/restrictions")).length, "restriction markers = restrictions from the API");
  const body = await page.evaluate(() => document.body.innerText);
  assert(body.includes(expected.explanation.slice(0, 40)), "recommendation explanation from the API is shown");
  assert(/Weight limit|Height limit/.test(body), "a rejection reason is visible");
  assert(/Basemap tiles unavailable/.test(body), "offline sandbox: tile-failure notice should appear");
  await shot(page, "01-route-investigation");
  // selecting a non-recommended alternative highlights it
  const altBtn = await page.evaluateHandle(() => [...document.querySelectorAll("button[aria-pressed]")].find((b) => b.getAttribute("aria-pressed") === "false"));
  await altBtn.asElement().click();
  await page.waitForFunction(() => document.querySelectorAll("path.route-revised").length === 1, { timeout: 5000 });
  await page.close();
});

await test("route page: no usable route is shown as NOT recommended", async () => {
  const page = await newPage(UI, { expectErrors: true });
  await page.setRequestInterception(true);
  page.on("request", async (r) => {
    if (r.url().endsWith("/routes/investigate")) {
      const real = await (await fetch(r.url(), { method: "POST", headers: { "content-type": "application/json" }, body: r.postData() })).json();
      // transform the REAL response into the documented 'no usable route' state to check the UI branch
      real.recommended = false; real.recommendationStatus = "no_usable_route"; real.alternatives.forEach((a) => (a.recommended = false));
      return r.respond({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(real) });
    }
    r.continue();
  });
  await pick(page, "#origin", "FKC"); await pick(page, "#dest", "ALV");
  await clickButton(page, "Investigate route");
  await waitText(page, /not recommended/);
  await page.close();
});

// ------------------------------------------------------------------------------------------------ autopsy flow
await test("autopsy: full flow — baseline, sensitivity matches the API, comparison, explanation", async () => {
  const page = await newPage(UI + "/autopsy");
  await pick(page, "#origin", "VYT"); await pick(page, "#dest", "KKD"); await pick(page, "#veh", "veh-ecomet");
  await clickButton(page, "Run autopsy");
  await page.waitForSelector('[data-testid="sensitivity-score"]', { timeout: 30000 });
  const api1 = await api("/autopsy/analyze", { origin: "VYT", destination: "KKD", vehicleId: "veh-ecomet", includeDefaultSuite: true });
  eq(await text(page, '[data-testid="sensitivity-score"]'), api1.sensitivity.sensitivityScore.toFixed(2), "sensitivity score shown = API score");
  const body = await page.evaluate(() => document.body.innerText);
  assert(body.includes(`${api1.sensitivity.scenariosChanged} of ${api1.sensitivity.scenariosTested}`), "changed/tested counts shown");
  assert(/not an accident probability/i.test(body), "the score's meaning/limits are stated on screen");
  assert(body.includes("route S6 → S13") || body.includes("S6 → S13"), "baseline route shown");
  await page.waitForSelector('[data-testid="route-comparison"]', { timeout: 10000 });
  // the first changed scenario is auto-selected: baseline (dashed) and revised (cyan) lines are on the map
  eq(await count(page, "path.route-baseline"), 1, "baseline line drawn");
  eq(await count(page, "path.route-revised"), 1, "revised line drawn");
  const sc = api1.scenarios.find((s) => s.changed);
  const expl = await text(page, '[data-testid="scenario-explanation"]');
  eq(expl, sc.explanation, "explanation text is the backend's explanation verbatim");
  const cmpText = await page.$eval('[data-testid="route-comparison"]', (e) => e.innerText);
  assert(cmpText.includes(String(sc.comparison.durationMinBefore)) && cmpText.includes(String(sc.comparison.durationMinAfter)), "before/after durations shown");
  for (const v of sc.changedVariables) assert(cmpText.includes(v.variable), `changed variable ${v.variable} listed`);
  await shot(page, "02-autopsy-changed-scenario");
  // a stable scenario explains why it stayed stable
  await page.evaluate(() => [...document.querySelectorAll('[role="tab"]')].find((t) => t.textContent.startsWith("stable")).click());
  await page.evaluate(() => document.querySelector('ul[aria-label="Scenarios"] button').click());
  await page.waitForFunction(() => /stayed stable/i.test(document.querySelector('[data-testid="scenario-detail"]')?.innerText ?? ""), { timeout: 5000 });
  await shot(page, "03-autopsy-stable-scenario");
  await page.close();
});

await test("autopsy: what-if builder uses real data pickers and adds a scenario to the list", async () => {
  const page = await newPage(UI + "/autopsy");
  await pick(page, "#origin", "VYT"); await pick(page, "#dest", "KKD"); await pick(page, "#veh", "veh-ecomet");
  await clickButton(page, "Run autopsy");
  await page.waitForSelector('[data-testid="sensitivity-score"]', { timeout: 30000 });
  await page.select("#kind", "close_segment");
  await page.waitForSelector('select[aria-label="Close a road segment"] option[value="S13"]');
  await page.select('select[aria-label="Close a road segment"]', "S13");
  await clickButton(page, "Run what-if");
  await page.waitForFunction(() => /your what-if/i.test(document.body.innerText), { timeout: 20000 });
  const detail = await text(page, '[data-testid="scenario-detail"]');
  assert(/S13/.test(detail), "new what-if is selected and compared");
  await shot(page, "04-autopsy-whatif");
  await page.close();
});

await test("autopsy: nothing is persisted by running it", async () => {
  const before = JSON.stringify(await api("/defects")) + JSON.stringify(await api("/restrictions"));
  const page = await newPage(UI + "/autopsy");
  await pick(page, "#origin", "VYT"); await pick(page, "#dest", "KKD"); await pick(page, "#veh", "veh-ecomet");
  await clickButton(page, "Run autopsy");
  await page.waitForSelector('[data-testid="sensitivity-score"]', { timeout: 30000 });
  await page.close();
  eq(JSON.stringify(await api("/defects")) + JSON.stringify(await api("/restrictions")), before, "stored defects/restrictions unchanged");
});

// ------------------------------------------------------------------------------------------------ evidence lab
await test("evidence: upload → original image + AI candidates → location/severity → confirm → stored report", async () => {
  const page = await newPage(UI);
  await waitText(page, /Evidence Lab|Route Investigation/);
  await page.goto(UI + "/evidence", { waitUntil: "networkidle2" });
  await waitText(page, /Image analysis is configured/);
  const img = uniqueImage("main");
  await (await page.$("#file")).uploadFile(img);
  await clickButton(page, "Analyze photo");
  await page.waitForSelector('[data-testid="evidence-preview"]', { timeout: 30000 });
  const imgOk = await page.$eval('[data-testid="evidence-preview"]', (i) => i.complete && i.naturalWidth === 320);
  assert(imgOk, "the user's original image is displayed");
  const body = await page.evaluate(() => document.body.innerText);
  assert(/AI candidates — not verified facts/i.test(body), "AI candidates are labelled as not verified");
  assert((body.match(/AI candidate · unverified/gi) ?? []).length === 3, "all three observations badged as unverified AI candidates");
  assert(/\[STUB/.test(body) && /stub-not-meta-model/.test(body), "the stub provider output is labelled as such");
  // restriction candidate cannot be selected
  const sign = await page.$('[data-testid="obs-obs-3"] input[type=checkbox]');
  assert(await sign.evaluate((c) => c.disabled), "restriction candidate checkbox is disabled");
  assert(/never changes routing/i.test(await page.$eval('[data-testid="obs-obs-3"]', (e) => e.innerText)), "explains why it can't be confirmed");
  await shot(page, "05-evidence-candidates");
  // select the pothole: confirm is blocked until location is set
  await page.click('[data-testid="obs-obs-1"] input[type=checkbox]');
  await waitText(page, /Set a location/);
  assert(await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.startsWith("Confirm 1"))?.disabled), "confirm disabled without location");
  // click the map to set the location (Fort Kochi area)
  const box = await (await page.$('[data-testid="route-map"]')).boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction(() => document.querySelector("#lat")?.value !== "", { timeout: 5000 });
  const lat = await page.$eval("#lat", (e) => e.value);
  assert(/^-?\d+\.\d{5}$/.test(lat), `latitude set by the map click (${lat})`);
  await page.waitForFunction(() => !/Set a location/.test(document.body.innerText), { timeout: 5000 });
  assert(/set by you on the map/.test(await text(page, '[data-testid="location-line"]')), "location line reflects the map click");
  await clickButton(page, "Confirm 1 observation");
  await page.waitForSelector('[data-testid="report-card"]', { timeout: 20000 });
  const card = await text(page, '[data-testid="report-card"]');
  const id = card.match(/U-[0-9A-F]{8}/)?.[0];
  assert(id, `report ID shown (${card})`);
  const stored = await api(`/defects/${id}`);
  eq(stored.verificationStatus, "unverified", "stored report is unverified");
  assert(/unverified/.test(card), "UI shows verification status 'unverified'");
  eq(stored.userConfirmedObservation, true, "provenance flag stored");
  eq((await api("/restrictions")).length, 7, "no restriction was created from an AI observation");
  await shot(page, "06-evidence-confirmed");
  await page.close();
  fs.unlinkSync(img);
});

await test("evidence: the same image twice is flagged and does not create a second report", async () => {
  const page = await newPage(UI + "/evidence");
  await waitText(page, /Image analysis is configured/);
  const img = uniqueImage("dup");
  const defectsBefore = (await api("/defects")).length;
  const run = async (withLocation) => {
    await (await page.$("#file")).uploadFile(img);
    if (withLocation) { await page.type("#lat", "9.9667"); await page.type("#lon", "76.2424"); }
    await clickButton(page, "Analyze photo");
    await page.waitForSelector('[data-testid="obs-obs-1"]', { timeout: 30000 });
    await page.click('[data-testid="obs-obs-1"] input[type=checkbox]');
    await clickButton(page, "Confirm 1 observation");
    await page.waitForSelector('[data-testid="confirm-results"]', { timeout: 20000 });
  };
  await run(true);
  eq((await api("/defects")).length, defectsBefore + 1, "first confirmation creates one report");
  await page.reload({ waitUntil: "networkidle2" });
  await waitText(page, /Image analysis is configured/);
  await run(true); // after the reload nothing is remembered, so supply the location again
  await waitText(page, /already analyzed/i);
  await waitText(page, /duplicate image not counted/i);
  assert(!/text-success/.test(await page.$eval('[data-testid="confirm-results"] p', (e) => e.className)), "'no defects created' is not styled as success");
  eq((await api("/defects")).length, defectsBefore + 1, "duplicate did not create a second report");
  await page.close();
  fs.unlinkSync(img);
});

await test("evidence: severity is required when the model gives none", async () => {
  const page = await newPage(UI + "/evidence");
  await waitText(page, /Image analysis is configured/);
  const img2 = uniqueImage("sev");
  await (await page.$("#file")).uploadFile(img2);
  await page.type("#lat", "9.9667"); await page.type("#lon", "76.2424");
  await clickButton(page, "Analyze photo");
  await page.waitForSelector('[data-testid="obs-obs-2"]', { timeout: 30000 });
  await page.click('[data-testid="obs-obs-2"] input[type=checkbox]'); // standing water: no severity suggested by the stub
  await waitText(page, /Choose a severity/);
  assert(await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.startsWith("Confirm 1"))?.disabled), "confirm disabled until severity chosen");
  await page.select("#sev-obs-2", "2");
  await page.waitForFunction(() => !/Choose a severity/.test(document.body.innerText));
  await clickButton(page, "Confirm 1 observation");
  await page.waitForSelector('[data-testid="report-card"]', { timeout: 20000 });
  assert(/pothole|standing|waterlogging/i.test(await text(page, '[data-testid="report-card"]')), "report created with the chosen severity");
  await page.close();
  fs.unlinkSync(img2);
});

await test("evidence: unsupported file is rejected before upload", async () => {
  const page = await newPage(UI + "/evidence");
  const tmp = path.join(here, "fixtures", "notes.txt"); fs.writeFileSync(tmp, "not an image");
  let posted = false; page.on("request", (r) => { if (r.url().includes("/evidence/analyze")) posted = true; });
  await page.evaluate(() => { document.querySelector("#file").removeAttribute("accept"); });
  await (await page.$("#file")).uploadFile(tmp);
  await waitText(page, /Unsupported file type/);
  eq(posted, false, "no network request for an invalid file");
  fs.unlinkSync(tmp);
  await page.close();
});

// ------------------------------------------------------------------------------------------------ vehicles
await test("vehicles: restriction check from the backend and unknown specs highlighted", async () => {
  const page = await newPage(UI + "/vehicles");
  await page.waitForSelector('[data-testid="vehicle-veh-ecomet"]', { timeout: 20000 });
  assert(/Unknown: height/i.test(await page.$eval('[data-testid="vehicle-veh-bus"]', (e) => e.innerText)), "bus: unknown height shown");
  await page.evaluate(() => [...document.querySelectorAll('[data-testid="vehicle-veh-ecomet"] button')].find((b) => b.textContent.includes("Check restrictions")).click());
  await page.waitForSelector('[data-testid="vehicle-veh-ecomet"] [data-testid="restriction-panel"] table', { timeout: 20000 });
  const panel = await page.$eval('[data-testid="vehicle-veh-ecomet"] [data-testid="restriction-panel"]', (e) => e.innerText);
  assert(/3 blocks \(verified\)/i.test(panel), "3 verified blockers for the Ecomet");
  assert(/R2/.test(panel) && /Height/i.test(panel) || /height/.test(panel), "restriction rows shown");
  await page.evaluate(() => [...document.querySelectorAll('[data-testid="vehicle-cat-traveller"] button')].find((b) => b.textContent.includes("Check restrictions")).click());
  await page.waitForSelector('[data-testid="vehicle-cat-traveller"] [data-testid="restriction-panel"]', { timeout: 20000 });
  assert(/cannot confirm — spec unknown/i.test(await page.$eval('[data-testid="vehicle-cat-traveller"] [data-testid="restriction-panel"]', (e) => e.innerText)), "unknown spec → 'cannot confirm', never 'fits'");
  await shot(page, "08-vehicles");
  await page.close();
});

// ------------------------------------------------------------------------------------------------ failure states
await test("backend unreachable: clear error + retry, and NO demo data appears", async () => {
  const page = await browser.newPage(); // not routed through newPage(): connection errors are the point of this test
  await page.setViewport({ width: 1366, height: 1000 });
  await page.setRequestInterception(true);
  page.on("request", (r) => (r.url().startsWith(API) ? r.abort("connectionrefused") : r.continue()));
  await page.goto(UI + "/vehicles", { waitUntil: "networkidle2", timeout: 60000 });
  await waitText(page, /Try again|Retry|couldn't reach|unreachable|network/i);
  const body = await page.evaluate(() => document.body.innerText);
  assert(!/Demo Van|Demo Truck|synthetic/i.test(body), "no demo/synthetic data may appear in backend mode");
  await shot(page, "09-error-state");
  await page.close();
});

await test("backend 5xx on autopsy shows an error state with retry", async () => {
  const page = await newPage(UI + "/autopsy", { expectErrors: true });
  await page.setRequestInterception(true);
  page.on("request", (r) => (r.url().endsWith("/autopsy/analyze") ? r.respond({ status: 500, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: '{"detail":"boom"}' }) : r.continue()));
  await pick(page, "#origin", "VYT"); await pick(page, "#dest", "KKD");
  await clickButton(page, "Run autopsy");
  await waitText(page, /Try again|Retry/i);
  await page.close();
});

await test("responsive: pages render without horizontal overflow at 390px", async () => {
  for (const p of ["/", "/autopsy", "/evidence", "/vehicles"]) {
    const page = await newPage(UI + p, { width: 390, height: 844 });
    await new Promise((r) => setTimeout(r, 800));
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert(over <= 2, `${p} overflows horizontally by ${over}px`);
    if (p === "/") await shot(page, "10-mobile-home");
    await page.close();
  }
});

await test("no unexpected console errors or page errors across all tests", async () => {
  assert(consoleErrors.length === 0, `unexpected errors:\n${consoleErrors.slice(0, 5).join("\n")}`);
});

await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} browser tests passed. Screenshots: ${SHOTS}`);
process.exit(failed.length ? 1 : 0);
